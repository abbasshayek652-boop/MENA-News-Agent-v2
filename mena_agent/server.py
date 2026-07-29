"""FastAPI HTTP server.

Endpoints:
  GET  /healthz            - health check (used by Cloud Run / uptime checks)
  GET  /readyz              - readiness check
  POST /run                 - trigger a pipeline run, returns JSON
  GET  /dashboard            - lists past runs
  GET  /dashboard/runs/{id}  - view a single run's report

Auth: if API_SECRET_TOKEN is set, /run requires it via
`Authorization: Bearer <token>` or `X-API-KEY: <token>`. The dashboard
accepts the same token as a `?token=` query param (for easy browser access)
if API_SECRET_TOKEN is set; if it's not set, the dashboard is open — set it
in production if these reports shouldn't be publicly visible.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import markdown as md
from fastapi import FastAPI, Header, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from mena_agent.pipeline import run_pipeline
from mena_agent.settings import get_settings
from mena_agent.store import get_store

logger = logging.getLogger(__name__)

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

app = FastAPI(title="MENA News Agent")


def _check_auth(authorization: str | None, x_api_key: str | None) -> bool:
    secret = get_settings().api_secret_token
    if not secret:
        return True
    if authorization and authorization.startswith("Bearer ") and authorization.split("Bearer ", 1)[1].strip() == secret:
        return True
    if x_api_key == secret:
        return True
    return False


def _check_dashboard_auth(token: str | None) -> bool:
    secret = get_settings().api_secret_token
    if not secret:
        return True
    return token == secret


@app.get("/", response_class=JSONResponse)
async def root() -> dict[str, Any]:
    return {"ok": True, "service": "mena-news-agent"}


@app.get("/healthz", response_class=JSONResponse)
async def healthz() -> dict[str, Any]:
    warnings = get_settings().validate()
    return {"ok": True, "service": "mena-news-agent", "warnings": warnings}


@app.get("/readyz", response_class=JSONResponse)
async def readyz() -> dict[str, Any]:
    return {"ok": True}


@app.post("/run", response_class=JSONResponse)
async def trigger_run(
    send_telegram: bool = Query(default=False),
    dry_run: bool = Query(default=True),
    authorization: str | None = Header(default=None),
    x_api_key: str | None = Header(default=None, alias="X-API-KEY"),
) -> dict[str, Any]:
    if not _check_auth(authorization, x_api_key):
        raise HTTPException(status_code=401, detail="unauthorized")

    try:
        result = run_pipeline(send_telegram=send_telegram, dry_run_override=dry_run)
    except Exception as exc:
        logger.exception("Pipeline run failed: %s", exc)
        raise HTTPException(status_code=500, detail=str(exc)) from exc

    return {"ok": True, "result": result}


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard(request: Request, token: str | None = Query(default=None)) -> HTMLResponse:
    if not _check_dashboard_auth(token):
        raise HTTPException(status_code=401, detail="unauthorized — pass ?token=<API_SECRET_TOKEN>")

    store = get_store()
    runs = store.list_runs(limit=50)
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {"runs": runs, "token": token or ""},
    )


@app.get("/dashboard/runs/{run_id}", response_class=HTMLResponse)
async def dashboard_run(request: Request, run_id: str, token: str | None = Query(default=None)) -> HTMLResponse:
    if not _check_dashboard_auth(token):
        raise HTTPException(status_code=401, detail="unauthorized — pass ?token=<API_SECRET_TOKEN>")

    store = get_store()
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    report_html = md.markdown(run.get("report_markdown", ""), extensions=["extra", "sane_lists"])
    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {"run": run, "report_html": report_html, "token": token or ""},
    )
