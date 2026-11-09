"""Run the real provider SDKs against a mocked HTTP transport.

Response bodies follow the shapes in each provider's official API reference, so these
tests pin down what we send and how we parse — without network access or real keys.
"""
import json

import anthropic
import httpx
import httpx2
import openai
import pytest
from google import genai
from google.genai import types

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import ModelInfo, ProviderError
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_compatible import GroqProvider, OpenRouterProvider
from app.llm.openai_provider import OpenAIProvider


class Recorder:
    def __init__(self, routes, lib=httpx):
        # The Anthropic SDK is built on httpx2, the others on httpx; both share this API
        self.routes, self.requests, self.lib = routes, [], lib

    def __call__(self, request):
        self.requests.append(request)
        for (method, fragment), (status, body) in self.routes.items():
            if request.method == method and fragment in str(request.url):
                if isinstance(body, str):   # a server-sent event stream
                    return self.lib.Response(status, text=body, headers={"content-type": "text/event-stream"})
                return self.lib.Response(status, json=body)
        return self.lib.Response(404, json={"error": {"message": f"unmocked {request.url}"}})

    def body(self, i=-1) -> dict:
        return json.loads(self.requests[i].content)

    def http(self, **kw):
        return self.lib.Client(transport=self.lib.MockTransport(self), **kw)


def _model(**kw) -> ModelInfo:
    return ModelInfo(**{"id": "m-1", "name": "M 1", **kw})


# ── Anthropic ──────────────────────────────────────────────────────
def test_anthropic_lists_active_models_and_generates_without_temperature(monkeypatch):
    rec = Recorder({
        ("GET", "/v1/models"): (200, {"data": [
            {"type": "model", "id": "claude-opus-5-5", "display_name": "Claude Opus 5.5",
             "created_at": "2026-09-21T00:00:00Z", "lifecycle": "active",
             "max_input_tokens": 1000000, "max_tokens": 128000}],
            "has_more": False, "first_id": "claude-opus-5-5", "last_id": "claude-opus-5-5"}),
        ("POST", "/v1/messages"): (200, {
            "id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
            "content": [{"type": "thinking", "thinking": "hmm", "signature": "sig"},
                        {"type": "text", "text": "Because of `abc1234`."}],
            "stop_reason": "end_turn", "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 5}}),
    }, lib=httpx2)
    p = AnthropicProvider()
    monkeypatch.setattr(p, "_client", lambda key: anthropic.Anthropic(api_key=key, http_client=rec.http()))

    models = p.list_models("sk-ant-test")
    assert [(m.id, m.name, m.context_window, m.max_output) for m in models] == \
        [("claude-opus-5-5", "Claude Opus 5.5", 1000000, 128000)]
    params = dict(rec.requests[0].url.params.multi_items())
    assert params.get("lifecycle[]", params.get("lifecycle")) == "active"
    assert rec.requests[0].headers["authorization"] == "Bearer sk-ant-test"

    text = p.generate("sk-ant-test", models[0], "SYS", "PROMPT")
    assert text == "Because of `abc1234`."   # thinking blocks are dropped
    body = rec.body()
    assert body["system"] == "SYS" and body["messages"] == [{"role": "user", "content": "PROMPT"}]
    assert body["max_tokens"] == 16000 and "temperature" not in body


def test_anthropic_bad_key_maps_to_auth(monkeypatch):
    rec = Recorder({("GET", "/v1/models"): (401, {"type": "error", "error": {
        "type": "authentication_error", "message": "invalid x-api-key"}})}, lib=httpx2)
    p = AnthropicProvider()
    monkeypatch.setattr(p, "_client", lambda key: anthropic.Anthropic(
        api_key=key, http_client=rec.http(), max_retries=0))
    with pytest.raises(ProviderError) as e:
        p.list_models("bad")
    assert e.value.kind == "auth" and e.value.message == "invalid x-api-key"


# ── OpenAI ─────────────────────────────────────────────────────────
def test_openai_filters_models_and_uses_responses_api(monkeypatch):
    rec = Recorder({
        ("GET", "/v1/models"): (200, {"object": "list", "data": [
            {"id": "gpt-6.1-sol", "object": "model", "created": 2, "owned_by": "openai"},
            {"id": "gpt-6-luna", "object": "model", "created": 3, "owned_by": "openai"},
            {"id": "gpt-image-2.5-flare", "object": "model", "created": 4, "owned_by": "openai"},
            {"id": "text-embedding-3-small", "object": "model", "created": 1, "owned_by": "openai"},
            {"id": "gpt-retired", "object": "model", "created": 1, "owned_by": "openai",
             "shutdown_date": "2020-01-01"}]}),
        ("POST", "/v1/responses"): (200, {
            "id": "resp_1", "object": "response", "created_at": 1, "status": "completed",
            "model": "gpt-6.1-sol", "parallel_tool_calls": True, "tool_choice": "auto", "tools": [],
            "output": [
                {"type": "reasoning", "id": "rs_1", "summary": []},
                {"type": "message", "id": "msg_1", "status": "completed", "role": "assistant",
                 "content": [{"type": "output_text", "text": "OpenAI answer", "annotations": []}]}]}),
    })
    p = OpenAIProvider()
    monkeypatch.setattr(p, "_client", lambda key: openai.OpenAI(api_key=key, http_client=rec.http()))

    assert [m.id for m in p.list_models("sk-test")] == ["gpt-6-luna", "gpt-6.1-sol"]   # newest first
    assert p.generate("sk-test", _model(id="gpt-6.1-sol"), "SYS", "PROMPT") == "OpenAI answer"
    body = rec.body()
    assert body["instructions"] == "SYS" and body["input"] == "PROMPT"
    assert body["max_output_tokens"] == 16000 and body["store"] is False
    assert "temperature" not in body


# ── Gemini ─────────────────────────────────────────────────────────
def _gemini_client(rec):
    return lambda key: genai.Client(api_key=key, http_options=types.HttpOptions(httpx_client=rec.http()))


def test_gemini_lists_generate_content_models_and_generates(monkeypatch):
    rec = Recorder({
        ("GET", "/models"): (200, {"models": [
            {"name": "models/gemini-3.8-flash", "displayName": "Gemini 3.8 Flash", "version": "3.8",
             "inputTokenLimit": 1048576, "outputTokenLimit": 65536,
             "supportedGenerationMethods": ["generateContent", "countTokens"]},
            {"name": "models/gemini-embedding-001", "version": "1",
             "supportedGenerationMethods": ["embedContent"]},
            {"name": "models/gemini-3.8-flash-tts", "version": "3.8",
             "supportedGenerationMethods": ["generateContent"]}]}),
        ("POST", "gemini-3.8-flash:generateContent"): (200, {"candidates": [
            {"content": {"role": "model", "parts": [{"text": "Gemini answer"}]}, "finishReason": "STOP"}]}),
    })
    p = GeminiProvider()
    monkeypatch.setattr(p, "_client", _gemini_client(rec))

    models = p.list_models("AIza-test")
    assert [(m.id, m.context_window, m.max_output) for m in models] == [("gemini-3.8-flash", 1048576, 65536)]

    assert p.generate("AIza-test", models[0], "SYS", "PROMPT") == "Gemini answer"
    body = rec.body()
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["generationConfig"]["maxOutputTokens"] == 16000


def test_gemini_invalid_key_is_auth_error(monkeypatch):
    rec = Recorder({("GET", "/models"): (400, {"error": {
        "code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}})})
    p = GeminiProvider()
    monkeypatch.setattr(p, "_client", _gemini_client(rec))
    with pytest.raises(ProviderError) as e:
        p.list_models("bad")
    assert e.value.kind == "auth"


# ── Groq ───────────────────────────────────────────────────────────
def test_groq_filters_inactive_and_audio_models(monkeypatch):
    rec = Recorder({
        ("GET", "/openai/v1/models"): (200, {"object": "list", "data": [
            {"id": "openai/gpt-oss-20b", "object": "model", "created": 1, "owned_by": "OpenAI",
             "active": True, "context_window": 131072},
            {"id": "whisper-large-v3", "object": "model", "created": 1, "owned_by": "OpenAI",
             "active": True, "context_window": 448},
            {"id": "meta-llama/llama-prompt-guard-2-22m", "object": "model", "created": 1,
             "owned_by": "Meta", "active": True, "context_window": 512},
            {"id": "old-model", "object": "model", "created": 1, "owned_by": "x", "active": False}]}),
        ("POST", "/chat/completions"): (200, {
            "id": "c1", "object": "chat.completion", "created": 1, "model": "openai/gpt-oss-20b",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "Groq answer"}}]}),
    })
    p = GroqProvider()
    monkeypatch.setattr(p, "_client", lambda key: openai.OpenAI(
        api_key=key, base_url=p.base_url, http_client=rec.http()))

    models = p.list_models("gsk_test")
    assert [(m.id, m.context_window) for m in models] == [("openai/gpt-oss-20b", 131072)]
    assert p.generate("gsk_test", models[0], "SYS", "PROMPT") == "Groq answer"
    body = rec.body()
    assert body["max_completion_tokens"] == 16000 and "max_tokens" not in body
    assert body["messages"][0] == {"role": "system", "content": "SYS"}


# ── OpenRouter ─────────────────────────────────────────────────────
def test_openrouter_validates_key_then_lists_text_models(monkeypatch):
    rec = Recorder({
        ("GET", "/api/v1/key"): (200, {"data": {"label": "test", "usage": 0}}),
        ("GET", "/api/v1/models"): (200, {"data": [
            {"id": "anthropic/claude-sonnet-5.5", "name": "Claude Sonnet 5.5", "context_length": 1000000,
             "architecture": {"input_modalities": ["text"], "output_modalities": ["text"]},
             "top_provider": {"max_completion_tokens": 128000, "is_moderated": False},
             "supported_parameters": ["max_tokens", "reasoning"]},
            {"id": "x/image-gen", "name": "Img", "context_length": 1000,
             "architecture": {"output_modalities": ["image"]}, "top_provider": {}},
            {"id": "meta/llama-x", "name": "Llama X", "context_length": 8000,
             "architecture": {"output_modalities": ["text"]},
             "top_provider": {"max_completion_tokens": 4000}, "supported_parameters": ["temperature"]}]}),
        ("POST", "/chat/completions"): (200, {
            "id": "c1", "object": "chat.completion", "created": 1, "model": "m",
            "choices": [{"index": 0, "finish_reason": "stop",
                         "message": {"role": "assistant", "content": "Router answer"}}]}),
    })
    p = OpenRouterProvider()
    monkeypatch.setattr(p, "_http", lambda: rec.http(base_url=p.base_url))
    monkeypatch.setattr(p, "_client", lambda key: openai.OpenAI(
        api_key=key, base_url=p.base_url, http_client=rec.http()))

    models = p.list_models("sk-or-test")
    assert [m.id for m in models] == ["anthropic/claude-sonnet-5.5", "meta/llama-x"]
    assert rec.requests[0].url.path == "/api/v1/key"
    assert rec.requests[0].headers["authorization"] == "Bearer sk-or-test"
    assert "output_modalities=text" in str(rec.requests[1].url)

    # No temperature for a model that doesn't list it; capped output for one with a small limit
    assert p.generate("sk-or-test", models[0], "SYS", "PROMPT") == "Router answer"
    assert "temperature" not in rec.body() and rec.body()["max_tokens"] == 16000
    assert rec.requests[-1].headers["x-openrouter-title"] == "Code Archaeologist"
    p.generate("sk-or-test", models[1], "SYS", "PROMPT")
    assert rec.body()["temperature"] == 0.2 and rec.body()["max_tokens"] == 4000


def test_openrouter_bad_key(monkeypatch):
    rec = Recorder({("GET", "/api/v1/key"): (401, {"error": {"code": 401, "message": "User not found."}})})
    p = OpenRouterProvider()
    monkeypatch.setattr(p, "_http", lambda: rec.http(base_url=p.base_url))
    with pytest.raises(ProviderError) as e:
        p.list_models("bad")
    assert e.value.kind == "auth" and e.value.message == "User not found."


# ── Streaming ──────────────────────────────────────────────────────
# Event streams follow each provider's documented streaming format.
def _sse(*events) -> str:
    """Server-sent events from (event name or None, data) pairs; data may be a dict or a raw string."""
    out = []
    for name, data in events:
        line = data if isinstance(data, str) else json.dumps(data)
        out.append((f"event: {name}\n" if name else "") + f"data: {line}\n\n")
    return "".join(out)


def _anthropic_stream(*text_events):
    message = {"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5", "content": [],
               "stop_reason": None, "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 1}}
    return _sse(
        ("message_start", {"type": "message_start", "message": message}),
        ("content_block_start", {"type": "content_block_start", "index": 0,
                                 "content_block": {"type": "thinking", "thinking": "", "signature": ""}}),
        ("content_block_delta", {"type": "content_block_delta", "index": 0,
                                 "delta": {"type": "thinking_delta", "thinking": "hmm"}}),
        ("content_block_stop", {"type": "content_block_stop", "index": 0}),
        ("content_block_start", {"type": "content_block_start", "index": 1,
                                 "content_block": {"type": "text", "text": ""}}),
        *text_events,
    )


def _anthropic_text(text):
    return ("content_block_delta", {"type": "content_block_delta", "index": 1,
                                    "delta": {"type": "text_delta", "text": text}})


def test_anthropic_streams_text_without_thinking(monkeypatch):
    rec = Recorder({("POST", "/v1/messages"): (200, _anthropic_stream(
        _anthropic_text("Because of "), _anthropic_text("`abc1234`."),
        ("content_block_stop", {"type": "content_block_stop", "index": 1}),
        ("message_delta", {"type": "message_delta", "delta": {"stop_reason": "end_turn", "stop_sequence": None},
                           "usage": {"output_tokens": 15}}),
        ("message_stop", {"type": "message_stop"})))}, lib=httpx2)
    p = AnthropicProvider()
    monkeypatch.setattr(p, "_client", lambda key: anthropic.Anthropic(api_key=key, http_client=rec.http()))

    assert list(p.stream("sk-ant-test", _model(), "SYS", "PROMPT")) == ["Because of ", "`abc1234`."]
    body = rec.body()
    assert body["stream"] is True and body["system"] == "SYS" and "temperature" not in body


def test_anthropic_error_in_the_middle_of_a_stream(monkeypatch):
    rec = Recorder({("POST", "/v1/messages"): (200, _anthropic_stream(
        _anthropic_text("Because "),
        ("error", {"type": "error", "error": {"type": "overloaded_error", "message": "Overloaded"}})))}, lib=httpx2)
    p = AnthropicProvider()
    monkeypatch.setattr(p, "_client", lambda key: anthropic.Anthropic(api_key=key, http_client=rec.http(),
                                                                       max_retries=0))
    pieces = p.stream("sk-ant-test", _model(), "SYS", "PROMPT")
    assert next(pieces) == "Because "
    with pytest.raises(ProviderError) as e:
        next(pieces)
    assert e.value.message == "Overloaded"


def _openai_response(status):
    return {"id": "resp_1", "object": "response", "created_at": 1, "status": status, "model": "gpt-6.1-sol",
            "output": [], "parallel_tool_calls": True, "tool_choice": "auto", "tools": [], "error": None}


def _openai_delta(n, text):
    return ("response.output_text.delta", {"type": "response.output_text.delta", "sequence_number": n,
                                           "item_id": "msg_1", "output_index": 1, "content_index": 0,
                                           "delta": text, "logprobs": []})


def test_openai_streams_output_text_deltas(monkeypatch):
    rec = Recorder({("POST", "/v1/responses"): (200, _sse(
        ("response.created", {"type": "response.created", "sequence_number": 0,
                              "response": _openai_response("in_progress")}),
        _openai_delta(1, "OpenAI "), _openai_delta(2, "answer"),
        ("response.completed", {"type": "response.completed", "sequence_number": 3,
                                "response": _openai_response("completed")})))})
    p = OpenAIProvider()
    monkeypatch.setattr(p, "_client", lambda key: openai.OpenAI(api_key=key, http_client=rec.http()))

    assert list(p.stream("sk-test", _model(id="gpt-6.1-sol"), "SYS", "PROMPT")) == ["OpenAI ", "answer"]
    body = rec.body()
    assert body["stream"] is True and body["instructions"] == "SYS" and body["store"] is False


def test_openai_failed_response_mid_stream(monkeypatch):
    failed = {**_openai_response("failed"), "error": {"code": "server_error", "message": "The model crashed"}}
    rec = Recorder({("POST", "/v1/responses"): (200, _sse(
        _openai_delta(1, "Partial "),
        ("response.failed", {"type": "response.failed", "sequence_number": 2, "response": failed})))})
    p = OpenAIProvider()
    monkeypatch.setattr(p, "_client", lambda key: openai.OpenAI(api_key=key, http_client=rec.http()))
    pieces = p.stream("sk-test", _model(), "SYS", "PROMPT")
    assert next(pieces) == "Partial "
    with pytest.raises(ProviderError) as e:
        next(pieces)
    assert e.value.message == "The model crashed"


def test_gemini_streams_and_skips_chunks_without_text(monkeypatch):
    rec = Recorder({("POST", "gemini-3.8-flash:streamGenerateContent"): (200, _sse(
        (None, {"candidates": [{"content": {"role": "model", "parts": [{"text": "thinking", "thought": True}]}}]}),
        (None, {"candidates": [{"content": {"role": "model", "parts": [{"text": "Gemini "}]}}]}),
        (None, {"candidates": [{"content": {"role": "model", "parts": [{"text": "answer"}]},
                                "finishReason": "STOP"}]})))})
    p = GeminiProvider()
    monkeypatch.setattr(p, "_client", _gemini_client(rec))

    assert list(p.stream("AIza-test", _model(id="gemini-3.8-flash"), "SYS", "PROMPT")) == ["Gemini ", "answer"]
    body = rec.body()
    assert body["systemInstruction"]["parts"][0]["text"] == "SYS"
    assert body["generationConfig"]["maxOutputTokens"] == 16000


def _chunk(content, finish=None, **extra):
    return (None, {"id": "c1", "object": "chat.completion.chunk", "created": 1, "model": "m-1",
                   "choices": [{"index": 0, "delta": {"content": content}, "finish_reason": finish}], **extra})


def test_groq_streams_chat_completion_chunks(monkeypatch):
    rec = Recorder({("POST", "/chat/completions"): (200, _sse(
        _chunk(""), _chunk("Groq "), _chunk("answer", "stop"), (None, "[DONE]")))})
    p = GroqProvider()
    monkeypatch.setattr(p, "_client", lambda key: openai.OpenAI(api_key=key, base_url=p.base_url,
                                                                 http_client=rec.http()))
    assert list(p.stream("gsk-test", _model(), "SYS", "PROMPT")) == ["Groq ", "answer"]
    body = rec.body()
    assert body["stream"] is True and body["temperature"] == 0.2 and body["max_completion_tokens"] == 16000


def test_openrouter_upstream_error_mid_stream(monkeypatch):
    # OpenRouter reports a failing upstream provider as an error chunk after some text
    rec = Recorder({("POST", "/chat/completions"): (200, ": OPENROUTER PROCESSING\n\n" + _sse(
        _chunk("Open"),
        _chunk("", "error", error={"code": 502, "message": "Provider returned error"}),
        (None, "[DONE]")))})
    p = OpenRouterProvider()
    monkeypatch.setattr(p, "_client", lambda key: openai.OpenAI(api_key=key, base_url=p.base_url,
                                                                 http_client=rec.http()))
    pieces = p.stream("sk-or-test", _model(), "SYS", "PROMPT")
    assert next(pieces) == "Open"
    with pytest.raises(ProviderError) as e:
        next(pieces)
    assert e.value.message == "Provider returned error"
    assert rec.requests[0].headers["x-openrouter-title"]


def test_a_stream_with_no_text_is_an_error(monkeypatch):
    from app import llm

    class Silent:
        def stream(self, api_key, model, system, prompt):
            yield from ("", "")
    monkeypatch.setitem(llm.PROVIDERS, "silent", Silent())
    with pytest.raises(ProviderError) as e:
        list(llm.stream("silent", _model(), "key", "SYS", "PROMPT"))
    assert e.value.kind == "bad_request" and "returned no text" in e.value.message
