"""Persists run history (metadata + report) so the dashboard can list and
display past runs.

Two backends:
  - "local" (default): writes to DATA_DIR on the local filesystem. Zero
    setup, but on Cloud Run this is ephemeral — history resets whenever a
    new revision deploys or the instance is recycled.
  - "gcs": writes to a Google Cloud Storage bucket, so history survives
    deploys and is shared across instances. Requires GCS_BUCKET and a
    service account with Storage Object Admin on that bucket.
"""

from __future__ import annotations

import json
import logging
from dataclasses import asdict, dataclass
from typing import Any

from mena_agent.paths import runs_dir
from mena_agent.settings import get_settings

logger = logging.getLogger(__name__)


@dataclass
class RunRecord:
    run_id: str
    timestamp: str
    sources_configured: int
    sources_with_items: int
    raw_items: int
    processed_items: int
    final_items: int
    is_real_analysis: bool
    used_seed_data: bool
    telegram_sent: bool
    report_markdown: str


class LocalStore:
    def save(self, record: RunRecord) -> None:
        run_dir = runs_dir() / record.run_id
        run_dir.mkdir(parents=True, exist_ok=True)
        meta = asdict(record)
        report = meta.pop("report_markdown")
        (run_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
        (run_dir / "report.md").write_text(report, encoding="utf-8")

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        base = runs_dir()
        run_dirs = sorted((d for d in base.iterdir() if d.is_dir()), key=lambda d: d.name, reverse=True)
        results = []
        for d in run_dirs[:limit]:
            meta_path = d / "meta.json"
            if meta_path.exists():
                try:
                    results.append(json.loads(meta_path.read_text(encoding="utf-8")))
                except json.JSONDecodeError:
                    continue
        return results

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        run_dir = runs_dir() / run_id
        meta_path = run_dir / "meta.json"
        report_path = run_dir / "report.md"
        if not meta_path.exists():
            return None
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        meta["report_markdown"] = report_path.read_text(encoding="utf-8") if report_path.exists() else ""
        return meta


class GCSStore:
    def __init__(self, bucket_name: str):
        from google.cloud import storage  # imported lazily; optional dependency path

        self._client = storage.Client()
        self._bucket = self._client.bucket(bucket_name)

    def save(self, record: RunRecord) -> None:
        meta = asdict(record)
        report = meta.pop("report_markdown")
        self._bucket.blob(f"runs/{record.run_id}/meta.json").upload_from_string(
            json.dumps(meta, ensure_ascii=False, indent=2), content_type="application/json"
        )
        self._bucket.blob(f"runs/{record.run_id}/report.md").upload_from_string(
            report, content_type="text/markdown"
        )

    def list_runs(self, limit: int = 50) -> list[dict[str, Any]]:
        blobs = self._client.list_blobs(self._bucket, prefix="runs/")
        run_ids = sorted(
            {b.name.split("/")[1] for b in blobs if b.name.endswith("meta.json")},
            reverse=True,
        )
        results = []
        for run_id in run_ids[:limit]:
            blob = self._bucket.blob(f"runs/{run_id}/meta.json")
            if blob.exists():
                results.append(json.loads(blob.download_as_text()))
        return results

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        meta_blob = self._bucket.blob(f"runs/{run_id}/meta.json")
        if not meta_blob.exists():
            return None
        meta = json.loads(meta_blob.download_as_text())
        report_blob = self._bucket.blob(f"runs/{run_id}/report.md")
        meta["report_markdown"] = report_blob.download_as_text() if report_blob.exists() else ""
        return meta


def get_store():
    settings = get_settings()
    if settings.storage_backend == "gcs" and settings.gcs_bucket:
        try:
            return GCSStore(settings.gcs_bucket)
        except Exception as exc:
            logger.warning("Failed to initialize GCS store, falling back to local: %s", exc)
    return LocalStore()
