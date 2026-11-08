import pytest

from storage.vector_store import RRF_K, VectorStore, fuse, keyword_tokens


def test_keyword_tokens_split_code_and_skip_common_words():
    tokens = keyword_tokens("Why does click.echo(msg) call ensure_object on the HTTPServer?")
    for word in ["click", "echo", "msg", "call", "ensure_object", "ensure", "object", "httpserver", "http", "server"]:
        assert word in tokens
    assert not {"why", "does", "on", "the"} & set(tokens)
    assert keyword_tokens("a I x") == []          # one-letter words and stopwords only


def test_fuse_merges_rankings_by_position():
    # Meaning ranks 0, 1, 2; only position 2 matches the keywords
    ranked = fuse(3, [0.0, 0.0, 5.0])
    assert [i for _, i in ranked] == [2, 0, 1]
    assert ranked[0][0] == pytest.approx((1 / (RRF_K + 3) + 1 / (RRF_K + 1)) / (2 / (RRF_K + 1)))
    # First in both rankings scores exactly 1
    assert fuse(2, [9.0, 1.0])[0] == (pytest.approx(1.0), 0)
    # Without keywords the meaning order stands, ties included
    assert [i for _, i in fuse(3, [0.0, 0.0, 0.0])] == [0, 1, 2]
    assert [i for _, i in fuse(3, [0.0, 0.0, 5.0], keyword_weight=0)] == [0, 1, 2]


def _chunk(sha, text):
    return {"id": sha * 6, "text": text, "metadata": {
        "sha": sha, "author": "dev", "timestamp": "2026-01-01T00:00:00", "files": "app.py",
        "has_pr": False, "pr_number": 0}}


def test_keywords_find_a_commit_the_embedding_missed():
    # The test embedding splits on spaces only, so it can't see the words inside `ctx.ensure_object(dict)`
    store = VectorStore("test_search_fusion")
    store.ingest([
        _chunk("aaaaaaa", "COMMIT: tidy the readme wording"),
        _chunk("bbbbbbb", "COMMIT: bump the version number"),
        _chunk("ccccccc", "COMMIT: set up the context early\n\nDIFF:\n+ ctx.ensure_object(dict)"),
    ])
    question = "where is ensure object called"
    assert store.search(question, top_k=3, keyword_weight=0)[0]["metadata"]["sha"] != "ccccccc"
    hits = store.search(question, top_k=3)
    assert hits[0]["metadata"]["sha"] == "ccccccc"
    assert 0 < hits[-1]["score"] < hits[0]["score"] <= 1
    store.delete_namespace()
