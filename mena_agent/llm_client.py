"""Pluggable LLM backend for the analysis step.

Two backends are supported:
  - "anthropic" (default): calls the Claude API directly. Reliable, hosted,
    nothing to run yourself.
  - "ollama": calls a self-hosted Ollama server you point at via
    OLLAMA_BASE_URL. Useful if you're running your own model server.

Both raise LLMError on failure so the caller (report_writer.py) can fall
back to the placeholder template gracefully instead of crashing the whole
pipeline run.
"""

from __future__ import annotations

import logging

import requests

from mena_agent.settings import get_settings

logger = logging.getLogger(__name__)


class LLMError(Exception):
    """Raised when the configured LLM backend fails to produce a response."""


class LLMClient:
    def generate(self, system_prompt: str, user_prompt: str) -> str:
        raise NotImplementedError


class AnthropicLLMClient(LLMClient):
    def __init__(self, api_key: str, model: str):
        if not api_key:
            raise LLMError("ANTHROPIC_API_KEY is not set")
        self._api_key = api_key
        self._model = model

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        try:
            import anthropic
        except ImportError as exc:
            raise LLMError("The 'anthropic' package is not installed") from exc

        try:
            client = anthropic.Anthropic(api_key=self._api_key)
            response = client.messages.create(
                model=self._model,
                max_tokens=4000,
                system=system_prompt,
                messages=[{"role": "user", "content": user_prompt}],
            )
            parts = [block.text for block in response.content if getattr(block, "type", "") == "text"]
            text = "\n".join(parts).strip()
            if not text:
                raise LLMError("Claude API returned an empty response")
            return text
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Claude API call failed: {exc}") from exc


class OllamaLLMClient(LLMClient):
    def __init__(self, base_url: str, model: str):
        if not base_url:
            raise LLMError("OLLAMA_BASE_URL is not set")
        self._base_url = base_url.rstrip("/")
        self._model = model

    def generate(self, system_prompt: str, user_prompt: str) -> str:
        url = f"{self._base_url}/api/chat"
        payload = {
            "model": self._model,
            "stream": False,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        }
        try:
            response = requests.post(url, json=payload, timeout=120)
            response.raise_for_status()
            data = response.json()
            text = (data.get("message") or {}).get("content", "").strip()
            if not text:
                raise LLMError("Ollama returned an empty response")
            return text
        except LLMError:
            raise
        except Exception as exc:
            raise LLMError(f"Ollama call failed: {exc}") from exc


def get_llm_client() -> LLMClient:
    """Build the configured LLM client. Raises LLMError if misconfigured —
    callers should catch this and fall back to the placeholder report."""
    settings = get_settings()

    if settings.llm_provider == "ollama":
        return OllamaLLMClient(settings.ollama_base_url, settings.ollama_model)

    # Default: anthropic
    return AnthropicLLMClient(settings.anthropic_api_key, settings.anthropic_model)
