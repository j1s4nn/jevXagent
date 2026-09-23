"""CLI entry point.

    jevXagent             start the local proxy (default)
    jevXagent serve       start the local proxy
    jevXagent statistics  statistics dashboard (alias: stats)
    jevXagent benchmark   controlled Claude-only vs JEV-routed comparison
    jevXagent version
"""

from __future__ import annotations

import argparse
import sys

from . import __version__
from .cli.benchmark import add_parser as add_benchmark_parser
from .cli.statistics import add_parser as add_statistics_parser


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]

    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError):
            pass

    parser = argparse.ArgumentParser(
        prog="jevXagent",
        description="When JEV Meets LLM Agent — a local LLM proxy with decision routing.",
    )
    sub = parser.add_subparsers(dest="command")

    serve = sub.add_parser("serve", help="start the local proxy server")
    serve.add_argument("--host", help="bind host (default: PROXY_HOST / 127.0.0.1)")
    serve.add_argument("--port", type=int, help="bind port (default: PROXY_PORT / 8787)")
    serve.add_argument("--log-level", help="logging level (default: LOG_LEVEL / INFO)")

    add_statistics_parser(sub)
    add_benchmark_parser(sub)
    sub.add_parser("version", help="print version")

    args = parser.parse_args(argv)
    if args.command in ("statistics", "stats"):
        return args.func(args)
    if args.command == "benchmark":
        return args.func(args)
    if args.command == "version":
        print(f"jevXagent {__version__}")
        return 0
    if args.command in (None, "serve"):
        return _serve(args)

    parser.print_help()
    return 1


def _serve(args: argparse.Namespace) -> int:
    from .config import Settings
    from .logging_setup import setup_logging
    from .server import create_app

    settings = Settings.from_env()
    setup_logging(getattr(args, "log_level", None) or settings.log_level)
    app = create_app(settings)

    import uvicorn

    host = getattr(args, "host", None) or settings.proxy_host
    port = getattr(args, "port", None) or settings.proxy_port
    print(f"jevXagent {__version__} listening on http://{host}:{port}")
    print(f"  upstream Claude API : {settings.claude_base_url}")
    print(f"  JEV enabled         : {settings.jev_enabled}")
    print(f"  routing enabled     : {settings.routing_enabled}")
    print(f"  telemetry db        : {settings.db_path()}")
    uvicorn.run(app, host=host, port=port, log_level="warning", access_log=False)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
