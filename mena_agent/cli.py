from __future__ import annotations

import argparse
import json
import logging
import time

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

logger = logging.getLogger(__name__)


def _run_once(args: argparse.Namespace) -> None:
    from mena_agent.pipeline import run_pipeline

    result = run_pipeline(send_telegram=args.send_telegram, dry_run_override=args.dry_run)
    print(json.dumps({k: v for k, v in result.items() if k != "report_markdown"}, indent=2, ensure_ascii=False))


def _run_loop(args: argparse.Namespace) -> None:
    from mena_agent.pipeline import run_pipeline

    logger.info("Starting scheduled loop: every %s seconds", args.interval)
    while True:
        try:
            run_pipeline(send_telegram=args.send_telegram, dry_run_override=args.dry_run)
        except Exception:
            logger.exception("Pipeline run failed")
        time.sleep(args.interval)


def _serve(args: argparse.Namespace) -> None:
    import uvicorn

    uvicorn.run("mena_agent.server:app", host="0.0.0.0", port=args.port)


def main() -> None:
    parser = argparse.ArgumentParser(prog="mena-agent")
    sub = parser.add_subparsers(dest="command")

    once = sub.add_parser("once", help="Run the pipeline a single time")
    once.add_argument("--send-telegram", action="store_true", default=None)
    once.add_argument("--dry-run", action="store_true", default=None)
    once.set_defaults(func=_run_once)

    loop = sub.add_parser("loop", help="Run the pipeline repeatedly on an interval")
    loop.add_argument("--interval", type=int, default=3600, help="Seconds between runs")
    loop.add_argument("--send-telegram", action="store_true", default=None)
    loop.add_argument("--dry-run", action="store_true", default=None)
    loop.set_defaults(func=_run_loop)

    serve = sub.add_parser("serve", help="Run the HTTP API + dashboard")
    serve.add_argument("--port", type=int, default=None)
    serve.set_defaults(func=_serve)

    args = parser.parse_args()

    if args.command is None:
        # Default to serving the HTTP API — this is what Cloud Run expects.
        import os

        args.port = int(os.getenv("PORT", "8080"))
        _serve(args)
        return

    if args.command == "serve" and args.port is None:
        import os

        args.port = int(os.getenv("PORT", "8080"))

    args.func(args)


if __name__ == "__main__":
    main()
