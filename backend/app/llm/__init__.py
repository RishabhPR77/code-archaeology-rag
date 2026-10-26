# app/llm/__init__.py
import hashlib
import threading
import time

from app.llm.anthropic_provider import AnthropicProvider
from app.llm.base import LLMProvider, ModelInfo, ProviderError
from app.llm.gemini_provider import GeminiProvider
from app.llm.openai_compatible import GroqProvider, OpenRouterProvider
from app.llm.openai_provider import OpenAIProvider

PROVIDERS: dict[str, LLMProvider] = {
    p.id: p for p in (AnthropicProvider(), OpenAIProvider(), GeminiProvider(),
                      GroqProvider(), OpenRouterProvider())
}

_MODEL_CACHE_TTL = 600  # seconds
_model_cache: dict[tuple[str, str], tuple[float, list[ModelInfo]]] = {}
_cache_lock = threading.Lock()


def get_provider(provider_id: str) -> LLMProvider:
    try:
        return PROVIDERS[provider_id]
    except KeyError:
        raise ProviderError("not_found", f"Unknown provider '{provider_id}'.") from None


def list_models(provider_id: str, api_key: str, refresh: bool = False) -> list[ModelInfo]:
    """Live model list from the provider, cached briefly per key."""
    cache_key = (provider_id, hashlib.sha256(api_key.encode()).hexdigest())
    with _cache_lock:
        hit = _model_cache.get(cache_key)
    if hit and not refresh and time.monotonic() - hit[0] < _MODEL_CACHE_TTL:
        return hit[1]
    models = get_provider(provider_id).list_models(api_key)
    with _cache_lock:
        _model_cache[cache_key] = (time.monotonic(), models)
    return models


def find_model(provider_id: str, api_key: str, model_id: str) -> ModelInfo:
    for refresh in (False, True):
        for m in list_models(provider_id, api_key, refresh=refresh):
            if m.id == model_id:
                return m
    raise ProviderError("not_found",
                        f"Model '{model_id}' is no longer offered by this provider. Pick another in Settings.")


def generate(provider_id: str, api_key: str, model_id: str, system: str, prompt: str) -> str:
    model = find_model(provider_id, api_key, model_id)
    return get_provider(provider_id).generate(api_key, model, system, prompt)
