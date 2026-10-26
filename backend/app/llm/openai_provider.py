# app/llm/openai_provider.py
"""OpenAI — Responses API (OpenAI's recommended API for its reasoning models).

Docs: https://developers.openai.com/api/docs/models
- GET /v1/models only returns id/created/owned_by/shutdown_date, so non-text model
  families listed in the docs (image, realtime/live voice, transcription, TTS,
  embeddings, moderation) are filtered out by ID.
- No temperature: current flagship models are reasoning models.
"""
from datetime import date

import openai

from app.llm.base import (REQUEST_TIMEOUT, ModelInfo, ProviderError, kind_from_status,
                          max_output_for, require_text)

_TEXT_PREFIXES = ("gpt-", "chatgpt-", "o1", "o3", "o4")
_NON_TEXT = ("image", "realtime", "live", "audio", "tts", "transcribe", "whisper",
             "embedding", "moderation", "dall-e", "sora", "search", "instruct")


def is_text_model(model_id: str, shutdown_date: str | None = None) -> bool:
    mid = model_id.lower()
    if not mid.startswith(_TEXT_PREFIXES) or any(t in mid for t in _NON_TEXT):
        return False
    if shutdown_date:
        try:
            return date.fromisoformat(shutdown_date[:10]) > date.today()
        except ValueError:
            pass
    return True


class OpenAIProvider:
    id = "openai"
    name = "OpenAI"
    key_url = "https://platform.openai.com/api-keys"
    docs_url = "https://developers.openai.com/api/docs/models"

    def _client(self, api_key: str) -> openai.OpenAI:
        return openai.OpenAI(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=2)

    def list_models(self, api_key: str) -> list[ModelInfo]:
        try:
            models = list(self._client(api_key).models.list())
        except openai.APIStatusError as e:
            raise ProviderError(kind_from_status(e.status_code), _message(e)) from e
        except openai.APIConnectionError as e:
            raise ProviderError("unavailable", "Couldn't reach the OpenAI API.") from e
        models.sort(key=lambda m: m.created or 0, reverse=True)
        return [ModelInfo(id=m.id, name=m.id) for m in models
                if is_text_model(m.id, m.shutdown_date)]

    def generate(self, api_key: str, model: ModelInfo, system: str, prompt: str) -> str:
        try:
            resp = self._client(api_key).responses.create(
                model=model.id,
                instructions=system,
                input=prompt,
                max_output_tokens=max_output_for(model),
                store=False,
            )
        except openai.APIStatusError as e:
            raise ProviderError(kind_from_status(e.status_code), _message(e)) from e
        except openai.APIConnectionError as e:
            raise ProviderError("unavailable", "Couldn't reach the OpenAI API.") from e
        return require_text(resp.output_text, model)


def _message(e: openai.APIStatusError) -> str:
    body = e.body if isinstance(e.body, dict) else {}
    err = body.get("error", body)
    return (err.get("message") if isinstance(err, dict) else None) or e.message
