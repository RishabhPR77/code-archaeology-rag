# app/llm/gemini_provider.py
"""Google Gemini — official google-genai SDK (generateContent).

Docs: https://ai.google.dev/api/models
- models.list reports supportedGenerationMethods and input/output token limits;
  only models that support generateContent are offered.
- The models page also lists generateContent-capable media/agent models
  (image, TTS, live, transcription, robotics, research agents), filtered by ID.
- Thinking tokens count toward max_output_tokens.
"""
from google import genai
from google.genai import errors, types

from app.llm.base import (REQUEST_TIMEOUT, ModelInfo, ProviderError, kind_from_status,
                          max_output_for, require_text)

_NON_TEXT = ("image", "tts", "live", "audio", "embedding", "transcribe", "robotics",
             "research", "antigravity", "lyria", "omni", "veo", "imagen", "banana",
             "computer-use", "aqa")


def is_text_model(model_id: str, actions: list[str] | None) -> bool:
    mid = model_id.lower()
    return "generateContent" in (actions or []) and not any(t in mid for t in _NON_TEXT)


class GeminiProvider:
    id = "gemini"
    name = "Google Gemini"
    key_url = "https://aistudio.google.com/app/apikey"
    docs_url = "https://ai.google.dev/gemini-api/docs/models"

    def _client(self, api_key: str) -> genai.Client:
        return genai.Client(api_key=api_key,
                            http_options=types.HttpOptions(timeout=int(REQUEST_TIMEOUT * 1000)))

    def list_models(self, api_key: str) -> list[ModelInfo]:
        try:
            out = []
            for m in self._client(api_key).models.list(config={"page_size": 1000}):
                mid = (m.name or "").removeprefix("models/")
                if mid and is_text_model(mid, m.supported_actions):
                    out.append(ModelInfo(id=mid, name=m.display_name or mid,
                                         context_window=m.input_token_limit,
                                         max_output=m.output_token_limit,
                                         description=m.description))
            return out
        except errors.APIError as e:
            raise _error(e) from e

    def generate(self, api_key: str, model: ModelInfo, system: str, prompt: str) -> str:
        try:
            resp = self._client(api_key).models.generate_content(
                model=model.id,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system,
                    max_output_tokens=max_output_for(model),
                ),
            )
        except errors.APIError as e:
            raise _error(e) from e
        return require_text(resp.text, model)


def _error(e: errors.APIError) -> ProviderError:
    message = e.message or str(e)
    # An invalid key comes back as 400 INVALID_ARGUMENT, not 401
    if "api key" in message.lower():
        return ProviderError("auth", message)
    return ProviderError(kind_from_status(e.code), message)
