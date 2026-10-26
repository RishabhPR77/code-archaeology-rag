# app/llm/base.py
"""Common shape for every LLM provider.

Model lists always come live from the provider's official list-models endpoint,
called with the user's own key — nothing about model names is hardcoded here.
"""
from dataclasses import dataclass, field
from typing import Literal, Protocol

# Room for the answer plus any reasoning/thinking tokens, which most current
# providers count against the same output limit.
DEFAULT_MAX_OUTPUT = 16_000
REQUEST_TIMEOUT = 120.0


@dataclass
class ModelInfo:
    id:             str
    name:           str
    context_window: int | None = None
    max_output:     int | None = None
    description:    str | None = None
    # Provider-specific hints used when calling the model (never sent to the browser)
    extra:          dict = field(default_factory=dict, repr=False)

    def public(self) -> dict:
        return {"id": self.id, "name": self.name, "context_window": self.context_window,
                "max_output": self.max_output, "description": self.description}


ErrorKind = Literal["auth", "rate_limit", "not_found", "bad_request", "unavailable"]


class ProviderError(Exception):
    """A provider call failed in a way the user can act on."""

    def __init__(self, kind: ErrorKind, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message


class LLMProvider(Protocol):
    id: str
    name: str
    key_url: str      # where users create a key
    docs_url: str     # official model docs

    def list_models(self, api_key: str) -> list[ModelInfo]: ...

    def generate(self, api_key: str, model: ModelInfo, system: str, prompt: str) -> str: ...


def kind_from_status(status: int | None) -> ErrorKind:
    if status in (401, 403):
        return "auth"
    if status == 429:
        return "rate_limit"
    if status == 404:
        return "not_found"
    if status is not None and 400 <= status < 500:
        return "bad_request"
    return "unavailable"


def max_output_for(model: ModelInfo) -> int:
    return min(DEFAULT_MAX_OUTPUT, model.max_output) if model.max_output else DEFAULT_MAX_OUTPUT


def require_text(text: str | None, model: ModelInfo) -> str:
    if not text or not text.strip():
        raise ProviderError("bad_request",
                            f"{model.name} returned no text — it may have used its whole output "
                            "budget on reasoning. Try again or pick another model.")
    return text.strip()
