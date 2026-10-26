# tests/conftest.py
import hashlib
import os
import tempfile

# Settings are read at import time, so configure a throwaway environment first
_tmp = tempfile.mkdtemp(prefix="ca-test-")
os.environ.update({
    "SECRET_KEY": "test-secret-key-that-is-long-enough-for-hs256-signing",
    "ENCRYPTION_KEY": "ZmDfcTF7_60GrrY167zsiPd67pEvs0aGOv2oasOM1Pg=",
    "DATABASE_URL": f"sqlite:///{_tmp}/test.db",
    "DATA_DIR": _tmp,
    "PINECONE_API_KEY": "",
    "GITHUB_TOKEN": "",
    "GITHUB_CLIENT_ID": "",
    "GITHUB_CLIENT_SECRET": "",
    "ADMIN_EMAILS": "admin@example.com",
    "MAX_COMMITS": "100",
    "MAX_REPOS_PER_USER": "2",
    "MAX_INGESTS_PER_DAY": "3",
})

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app import llm  # noqa: E402
from app.db import Base, engine, stamp_head  # noqa: E402
from app.deps import auth_limiter  # noqa: E402
from app.llm.base import ModelInfo, ProviderError  # noqa: E402
from app.main import app  # noqa: E402
from app.services import github as github_service  # noqa: E402
from storage import vector_store  # noqa: E402


def _fake_embed(text: str) -> list[float]:
    # Deterministic bag-of-words hashing; normalised like the real model
    vec = [0.0] * vector_store.EMBEDDING_DIM
    for word in text.lower().split():
        vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % len(vec)] += 1.0
    norm = sum(v * v for v in vec) ** 0.5 or 1.0
    return [v / norm for v in vec]


class FakeProvider:
    """Stands in for a real LLM provider. Key 'good-key-1234' is the only valid one."""
    id, name = "anthropic", "Anthropic"
    key_url = docs_url = "https://example.com"
    calls: list = []

    def list_models(self, api_key):
        if api_key != "good-key-1234":
            raise ProviderError("auth", "invalid x-api-key")
        return [ModelInfo(id="claude-test-1", name="Claude Test 1", context_window=1000, max_output=500)]

    def generate(self, api_key, model, system, prompt):
        self.calls.append({"model": model.id, "system": system, "prompt": prompt})
        return f"Answer from {model.id}: see `abc1234`."


@pytest.fixture(autouse=True)
def _isolate(monkeypatch):
    Base.metadata.drop_all(engine)
    with engine.begin() as c:
        c.exec_driver_sql("DROP TABLE IF EXISTS alembic_version")
    Base.metadata.create_all(engine)
    stamp_head()
    auth_limiter.hits.clear()
    llm._model_cache.clear()
    FakeProvider.calls = []
    monkeypatch.setitem(llm.PROVIDERS, "anthropic", FakeProvider())
    # No test may reach GitHub; tests that care about visibility override this
    monkeypatch.setattr(github_service, "repo_visibility", lambda full_name, token: "public")
    monkeypatch.setattr(vector_store, "_embed_query", _fake_embed)
    monkeypatch.setattr(vector_store, "_embed_docs", lambda texts: [_fake_embed(t) for t in texts])
    yield


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def register(client, email="dev@example.com", password="correct-horse-battery"):
    r = client.post("/api/auth/register", json={"email": email, "password": password, "name": "Dev"})
    assert r.status_code == 201, r.text
    return r.json()


@pytest.fixture
def user_client(client):
    register(client)
    return client
