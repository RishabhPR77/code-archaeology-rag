# app/llm/anthropic_provider.py
"""Anthropic — Messages API.

Docs: https://platform.claude.com/docs/en/api/models/list
- The Models API reports lifecycle, display_name, max_input_tokens and max_tokens.
- No temperature: several current models always think, so effort/defaults govern output.
"""
import anthropic

from app.llm.base import (REQUEST_TIMEOUT, ModelInfo, ProviderError, kind_from_status,
                          max_output_for, require_text)


class AnthropicProvider:
    id = "anthropic"
    name = "Anthropic"
    key_url = "https://platform.claude.com/settings/keys"
    docs_url = "https://platform.claude.com/docs/en/about-claude/models/overview"

    def _client(self, api_key: str) -> anthropic.Anthropic:
        return anthropic.Anthropic(api_key=api_key, timeout=REQUEST_TIMEOUT, max_retries=2)

    def list_models(self, api_key: str) -> list[ModelInfo]:
        try:
            # Deprecated models are closed to new adopters, so only offer active ones
            page = self._client(api_key).models.list(lifecycle=["active"], limit=1000)
            return [
                ModelInfo(id=m.id, name=m.display_name or m.id,
                          context_window=m.max_input_tokens, max_output=m.max_tokens)
                for m in page
            ]
        except anthropic.APIStatusError as e:
            raise ProviderError(kind_from_status(e.status_code), _message(e)) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("unavailable", "Couldn't reach the Anthropic API.") from e

    def generate(self, api_key: str, model: ModelInfo, system: str, prompt: str) -> str:
        try:
            resp = self._client(api_key).messages.create(
                model=model.id,
                max_tokens=max_output_for(model),
                system=system,
                messages=[{"role": "user", "content": prompt}],
            )
        except anthropic.APIStatusError as e:
            raise ProviderError(kind_from_status(e.status_code), _message(e)) from e
        except anthropic.APIConnectionError as e:
            raise ProviderError("unavailable", "Couldn't reach the Anthropic API.") from e
        text = "".join(b.text for b in resp.content if b.type == "text")
        return require_text(text, model)


def _message(e: anthropic.APIStatusError) -> str:
    body = e.body if isinstance(e.body, dict) else {}
    return body.get("error", {}).get("message") or str(e.message)
