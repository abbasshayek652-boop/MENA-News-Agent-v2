"""Centralized application settings, loaded once from environment variables.

Keeping all env var reads in one place means:
  - a single source of truth for what configuration the app needs
  - startup-time validation with clear warnings instead of scattered
    os.getenv() calls that fail silently deep in the pipeline
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _bool_env(name: str, default: bool) -> bool:
    val = os.getenv(name)
    if val is None:
        return default
    return val.strip().lower() in {"1", "true", "yes", "y", "on"}


@dataclass(frozen=True)
class Settings:
    # LLM backend
    llm_provider: str = field(default_factory=lambda: os.getenv("LLM_PROVIDER", "anthropic"))
    anthropic_api_key: str = field(default_factory=lambda: os.getenv("ANTHROPIC_API_KEY", ""))
    anthropic_model: str = field(default_factory=lambda: os.getenv("ANTHROPIC_MODEL", "claude-sonnet-4-6"))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", ""))
    ollama_model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "llama3"))

    # Telegram
    telegram_bot_token: str = field(
        default_factory=lambda: os.getenv("TELEGRAM_BOT_TOKEN") or os.getenv("TELEGRAM_TOKEN", "")
    )
    telegram_chat_id: str = field(default_factory=lambda: os.getenv("TELEGRAM_CHAT_ID", ""))
    send_telegram_default: bool = field(default_factory=lambda: _bool_env("SEND_TELEGRAM", False))

    # Pipeline behavior
    dry_run_default: bool = field(default_factory=lambda: _bool_env("DRY_RUN", True))
    source_config_path: str = field(default_factory=lambda: os.getenv("SOURCE_CONFIG", "config/sources.yaml"))
    per_source_item_limit: int = field(default_factory=lambda: int(os.getenv("PER_SOURCE_ITEM_LIMIT", "8")))
    max_total_items: int = field(default_factory=lambda: int(os.getenv("MAX_TOTAL_ITEMS", "120")))
    fetch_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("FETCH_TIMEOUT", "20")))

    # Storage
    data_dir: str = field(default_factory=lambda: os.getenv("DATA_DIR", "/tmp/mena-agent"))
    storage_backend: str = field(default_factory=lambda: os.getenv("STORAGE_BACKEND", "local"))
    gcs_bucket: str = field(default_factory=lambda: os.getenv("GCS_BUCKET", ""))

    # Server
    api_secret_token: str = field(default_factory=lambda: os.getenv("API_SECRET_TOKEN", ""))
    port: int = field(default_factory=lambda: int(os.getenv("PORT", "8080")))

    def validate(self) -> list[str]:
        """Return a list of human-readable warnings about missing/inconsistent
        configuration. Does not raise — the app should still start and report
        its own health via /healthz rather than crash on boot."""
        warnings: list[str] = []

        if self.llm_provider == "anthropic" and not self.anthropic_api_key:
            warnings.append(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set — "
                "reports will fall back to the placeholder template."
            )
        if self.llm_provider == "ollama" and not self.ollama_base_url:
            warnings.append(
                "LLM_PROVIDER=ollama but OLLAMA_BASE_URL is not set — "
                "reports will fall back to the placeholder template."
            )
        if not self.telegram_bot_token or not self.telegram_chat_id:
            warnings.append(
                "TELEGRAM_BOT_TOKEN/TELEGRAM_CHAT_ID not fully configured — "
                "Telegram delivery will be skipped even if requested."
            )
        if self.storage_backend == "gcs" and not self.gcs_bucket:
            warnings.append("STORAGE_BACKEND=gcs but GCS_BUCKET is not set — falling back to local storage.")

        return warnings


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
