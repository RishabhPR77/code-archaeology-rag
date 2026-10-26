from types import SimpleNamespace

import pytest
from pinecone.exceptions import PineconeApiException

from app.config import Settings, get_settings
from storage import vector_store as vs

# Captured at import, before conftest's autouse fixture swaps in fake embedders
REAL_EMBED_DOCS = vs._embed_docs
REAL_EMBED_QUERY = vs._embed_query

BASE = {"secret_key": "s" * 40, "encryption_key": "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg="}


class FakeInference:
    def __init__(self):
        self.calls, self.fail_first, self.status = [], 0, 429

    def embed(self, model, inputs, parameters):
        self.calls.append({"model": model, "n": len(inputs), **parameters})
        if self.fail_first:
            self.fail_first -= 1
            raise PineconeApiException(status=self.status, reason="error")
        return [{"values": [0.1] * parameters["dimension"]} for _ in inputs]


@pytest.fixture
def hosted(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_provider", "pinecone")
    monkeypatch.setattr(vs.time, "sleep", lambda s: None)
    inference = FakeInference()
    monkeypatch.setattr(vs, "_pinecone", lambda: SimpleNamespace(inference=inference))
    return inference


def test_hosted_docs_are_batched_as_passages(hosted):
    vectors = REAL_EMBED_DOCS([f"commit {i}" for i in range(100)])
    assert len(vectors) == 100 and len(vectors[0]) == 1024
    assert [c["n"] for c in hosted.calls] == [48, 48, 4]
    assert all(c["input_type"] == "passage" and c["truncate"] == "END" and c["model"] == "llama-text-embed-v2"
               for c in hosted.calls)


def test_hosted_query_retries_rate_limits(hosted):
    hosted.fail_first = 2
    assert len(REAL_EMBED_QUERY("why was auth refactored?")) == 1024
    assert len(hosted.calls) == 3 and all(c["input_type"] == "query" for c in hosted.calls)


def test_hosted_does_not_retry_other_errors(hosted):
    hosted.fail_first, hosted.status = 1, 401
    with pytest.raises(PineconeApiException):
        REAL_EMBED_QUERY("x")
    assert len(hosted.calls) == 1


def test_local_provider_never_calls_pinecone(monkeypatch):
    monkeypatch.setattr(vs, "_pinecone", lambda: pytest.fail("Pinecone called in local mode"))
    monkeypatch.setattr(vs, "_get_model", lambda: SimpleNamespace(
        encode=lambda texts, **_: SimpleNamespace(tolist=lambda: [[0.0] * 384] * len(texts))))
    assert len(REAL_EMBED_DOCS(["a", "b"])) == 2


def test_embedding_dim_follows_provider(monkeypatch):
    assert vs.embedding_dim() == 384
    monkeypatch.setattr(get_settings(), "embedding_provider", "pinecone")
    assert vs.embedding_dim() == 1024


def test_index_dimension_mismatch_is_explained(monkeypatch):
    monkeypatch.setattr(get_settings(), "embedding_provider", "pinecone")
    fake_pc = SimpleNamespace(
        list_indexes=lambda: [SimpleNamespace(name="code-archaeologist")],
        describe_index=lambda name: SimpleNamespace(dimension=384),
    )
    monkeypatch.setattr(vs, "_pinecone", lambda: fake_pc)
    with pytest.raises(RuntimeError, match="384-dim vectors .* 1024-dim"):
        vs._PineconeBackend("code-archaeologist")


def test_pinecone_embeddings_require_a_key():
    with pytest.raises(ValueError, match="needs PINECONE_API_KEY"):
        Settings(**BASE, embedding_provider="pinecone", pinecone_api_key="", _env_file=None)


def test_frontend_url_falls_back_to_render_url():
    s = Settings(**BASE, frontend_url="", render_external_url="https://code-archaeologist.onrender.com/",
                 _env_file=None)
    assert s.frontend_url == "https://code-archaeologist.onrender.com"
    assert Settings(**BASE, frontend_url="", render_external_url="", _env_file=None).frontend_url \
        == "http://localhost:5173"
