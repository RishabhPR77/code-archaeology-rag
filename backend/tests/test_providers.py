from sqlalchemy import select

from app.db import SessionLocal
from app.llm.gemini_provider import is_text_model as gemini_text
from app.llm.openai_provider import is_text_model as openai_text
from app.models import ProviderCredential


def test_lists_all_five_providers(user_client):
    ids = [p["id"] for p in user_client.get("/api/providers").json()]
    assert ids == ["anthropic", "openai", "gemini", "groq", "openrouter"]


def test_invalid_key_rejected_without_logging_out(user_client):
    r = user_client.put("/api/providers/anthropic/key", json={"api_key": "bad-key-0000"})
    assert r.status_code == 400
    assert "invalid" in r.json()["detail"]
    assert user_client.get("/api/auth/me").status_code == 200


def test_save_key_encrypts_and_never_returns_it(user_client):
    r = user_client.put("/api/providers/anthropic/key", json={"api_key": "good-key-1234"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["models"][0]["id"] == "claude-test-1"
    assert body["provider"]["key_hint"] == "…34"
    assert "good-key-1234" not in r.text
    assert "good-key-1234" not in user_client.get("/api/providers").text
    with SessionLocal() as db:
        cred = db.scalar(select(ProviderCredential))
        assert cred.key_enc != "good-key-1234" and "good-key" not in cred.key_enc


def test_first_key_becomes_active_and_model_must_exist(user_client):
    user_client.put("/api/providers/anthropic/key", json={"api_key": "good-key-1234"})
    me = user_client.get("/api/auth/me").json()["user"]
    assert me["active_provider"] == "anthropic" and me["active_model"] is None
    assert user_client.put("/api/providers/anthropic/model", json={"model": "made-up"}).status_code == 404
    assert user_client.put("/api/providers/anthropic/model", json={"model": "claude-test-1"}).status_code == 200
    assert user_client.get("/api/auth/me").json()["user"]["active_model"] == "claude-test-1"


def test_delete_key_clears_active(user_client):
    user_client.put("/api/providers/anthropic/key", json={"api_key": "good-key-1234"})
    assert user_client.delete("/api/providers/anthropic/key").status_code == 204
    assert user_client.get("/api/auth/me").json()["user"]["active_provider"] is None


def test_unconfigured_provider_needs_key(user_client):
    assert user_client.get("/api/providers/groq/models").status_code == 409
    assert user_client.put("/api/providers/active", json={"provider": "groq"}).status_code == 409
    assert user_client.get("/api/providers/nope/models").status_code == 404


def test_users_cannot_see_each_others_keys(client):
    from tests.conftest import register
    register(client, email="one@example.com")
    client.put("/api/providers/anthropic/key", json={"api_key": "good-key-1234"})
    client.post("/api/auth/logout")
    register(client, email="two@example.com")
    providers = client.get("/api/providers").json()
    assert not any(p["configured"] for p in providers)


def test_openai_filter_keeps_text_models_only():
    assert openai_text("gpt-6.1-sol")
    assert openai_text("o4-mini")
    for mid in ("gpt-image-2.5-flare", "gpt-realtime-2.1", "gpt-live-1", "gpt-transcribe",
                "gpt-4o-mini-tts", "text-embedding-3-large", "omni-moderation-latest", "whisper-1",
                "dall-e-3", "sora-2", "gpt-3.5-turbo-instruct"):
        assert not openai_text(mid), mid
    assert not openai_text("gpt-old", shutdown_date="2020-01-01")
    assert openai_text("gpt-new", shutdown_date="2999-01-01")


def test_gemini_filter_requires_generate_content():
    assert gemini_text("gemini-3.8-flash", ["generateContent", "countTokens"])
    assert not gemini_text("gemini-embedding-001", ["embedContent"])
    for mid in ("gemini-3.8-flash-tts", "gemini-3.8-live", "gemini-3.1-flash-image",
                "deep-research-preview-04-2026", "gemini-robotics-er-2-preview", "gemini-3.5-transcribe"):
        assert not gemini_text(mid, ["generateContent"]), mid
