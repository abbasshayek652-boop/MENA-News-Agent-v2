"""Filesystem path helpers.

Cloud Run's filesystem is read-only except for /tmp (or a configured
writable mount), and anything written there does not persist across
revisions or across multiple instances. DATA_DIR should point there by
default; use STORAGE_BACKEND=gcs (see store.py) for durable, cross-instance
persistence of run history.
"""

from __future__ import annotations

from pathlib import Path

from mena_agent.settings import get_settings


def data_dir() -> Path:
    path = Path(get_settings().data_dir)
    path.mkdir(parents=True, exist_ok=True)
    return path


def runs_dir() -> Path:
    path = data_dir() / "runs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def source_config_path() -> Path:
    return Path(get_settings().source_config_path)
