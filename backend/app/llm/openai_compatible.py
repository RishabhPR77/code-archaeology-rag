# app/llm/openai_compatible.py
"""Groq and OpenRouter — both officially support the OpenAI SDK via base_url."""
import httpx
import openai

from app.config import get_settings
from app.llm.base import (REQUEST_TIMEOUT, ModelInfo, ProviderError, kind_from_status,
                          max_output_for, require_text)

GROUNDED_TEMPERATURE = 0.2


def _message(e: openai.APIStatusError) -> str:
    body = e.body if isinstance(e.body, dict) else {}
    err = body.get("error", body)
    return (err.get("message") if isinstance(err, dict) else None) or e.message


class GroqProvider:
    """Docs: https://console.groq.com/docs/models

    - GET /openai/v1/models adds `active` and `context_window` to each model.
    - Speech-to-text, TTS and guard/safety models are filtered out by ID.
    - `max_tokens` is deprecated in favour of `max_completion_tokens`.
    """
    id = "groq"
    name = "Groq"
    key_url = "https://console.groq.com/keys"
    docs_url = "https://console.groq.com/docs/models"
    base_url = "https://api.groq.com/openai/v1"
    _NON_TEXT = ("whisper", "orpheus", "tts", "playai", "guard", "safeguard")

    def _client(self, api_key: str) -> openai.OpenAI:
        return openai.OpenAI(api_key=api_key, base_url=self.base_url,
                             timeout=REQUEST_TIMEOUT, max_retries=2)

    def list_models(self, api_key: str) -> list[ModelInfo]:
        try:
            models = list(self._client(api_key).models.list())
        except openai.APIStatusError as e:
            raise ProviderError(kind_from_status(e.status_code), _message(e)) from e
        except openai.APIConnectionError as e:
            raise ProviderError("unavailable", "Couldn't reach the Groq API.") from e
        out = []
        for m in models:
            extra = m.model_extra or {}
            if extra.get("active") is False or any(t in m.id.lower() for t in self._NON_TEXT):
                continue
            out.append(ModelInfo(id=m.id, name=m.id, context_window=extra.get("context_window"),
                                 max_output=extra.get("max_completion_tokens"),
                                 description=f"by {m.owned_by}" if m.owned_by else None))
        return sorted(out, key=lambda m: m.id)

    def generate(self, api_key: str, model: ModelInfo, system: str, prompt: str) -> str:
        try:
            resp = self._client(api_key).chat.completions.create(
                model=model.id,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                max_completion_tokens=max_output_for(model),
                temperature=GROUNDED_TEMPERATURE,
            )
        except openai.APIStatusError as e:
            raise ProviderError(kind_from_status(e.status_code), _message(e)) from e
        except openai.APIConnectionError as e:
            raise ProviderError("unavailable", "Couldn't reach the Groq API.") from e
        return require_text(resp.choices[0].message.content if resp.choices else None, model)


class OpenRouterProvider:
    """Docs: https://openrouter.ai/docs/api/api-reference/models/get-models

    - GET /api/v1/models defaults to text-output models and reports context_length,
      top_provider.max_completion_tokens and supported_parameters.
    - The model list doesn't prove a key works, so keys are checked with GET /api/v1/key.
    - temperature is only sent when the model lists it in supported_parameters.
    """
    id = "openrouter"
    name = "OpenRouter"
    key_url = "https://openrouter.ai/settings/keys"
    docs_url = "https://openrouter.ai/models"
    base_url = "https://openrouter.ai/api/v1"

    def _client(self, api_key: str) -> openai.OpenAI:
        return openai.OpenAI(api_key=api_key, base_url=self.base_url,
                             timeout=REQUEST_TIMEOUT, max_retries=2)

    def _http(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=30)

    def _headers(self, api_key: str) -> dict:
        return {"Authorization": f"Bearer {api_key}"}

    def _attribution(self) -> dict:
        settings = get_settings()
        return {"HTTP-Referer": settings.frontend_url, "X-OpenRouter-Title": settings.app_name}

    def list_models(self, api_key: str) -> list[ModelInfo]:
        try:
            with self._http() as http:
                key_resp = http.get("/key", headers=self._headers(api_key))
                if key_resp.status_code != 200:
                    raise ProviderError(kind_from_status(key_resp.status_code),
                                        _http_message(key_resp, "OpenRouter rejected this API key."))
                resp = http.get("/models", headers=self._headers(api_key),
                                params={"output_modalities": "text"})
                resp.raise_for_status()
        except httpx.HTTPStatusError as e:
            raise ProviderError(kind_from_status(e.response.status_code),
                                _http_message(e.response, "Couldn't list OpenRouter models.")) from e
        except httpx.HTTPError as e:
            raise ProviderError("unavailable", "Couldn't reach the OpenRouter API.") from e

        out = []
        for m in resp.json().get("data", []):
            arch = m.get("architecture") or {}
            if "text" not in (arch.get("output_modalities") or ["text"]):
                continue
            top = m.get("top_provider") or {}
            out.append(ModelInfo(
                id=m["id"], name=m.get("name") or m["id"],
                context_window=m.get("context_length"),
                max_output=top.get("max_completion_tokens"),
                description=(m.get("description") or "")[:200] or None,
                extra={"supported_parameters": m.get("supported_parameters") or []},
            ))
        return out

    def generate(self, api_key: str, model: ModelInfo, system: str, prompt: str) -> str:
        kwargs = {}
        if "temperature" in model.extra.get("supported_parameters", []):
            kwargs["temperature"] = GROUNDED_TEMPERATURE
        try:
            resp = self._client(api_key).chat.completions.create(
                model=model.id,
                messages=[{"role": "system", "content": system},
                          {"role": "user", "content": prompt}],
                max_tokens=max_output_for(model),
                extra_headers=self._attribution(),
                **kwargs,
            )
        except openai.APIStatusError as e:
            raise ProviderError(kind_from_status(e.status_code), _message(e)) from e
        except openai.APIConnectionError as e:
            raise ProviderError("unavailable", "Couldn't reach the OpenRouter API.") from e
        return require_text(resp.choices[0].message.content if resp.choices else None, model)


def _http_message(resp: httpx.Response, fallback: str) -> str:
    try:
        err = resp.json().get("error")
        return (err.get("message") if isinstance(err, dict) else err) or fallback
    except ValueError:
        return fallback
