"""CLI: jevXagent statistics — the evidence layer.

Every number displayed comes from the telemetry store. Measured values are
shown as-is; estimated values are marked with an asterisk (*) and explained
in the methodology section.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

from ..config import Settings
from ..telemetry import metrics
from ..telemetry.charts import categories_chart, latency_chart, routing_chart, save_charts
from ..telemetry.reports import build_stats, render_report
from ..telemetry.storage import TelemetryStore

_DAY = 86400.0


def add_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "statistics",
        aliases=["stats"],
        help="show the jevXagent statistics dashboard",
        description="Statistics dashboard built from recorded telemetry.",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--today", action="store_true", help="calendar day")
    group.add_argument("--7d", action="store_true", help="last 7 days")
    group.add_argument("--30d", action="store_true", help="last 30 days")
    group.add_argument("--all", action="store_true", help="all recorded history (default)")
    parser.add_argument("--report", action="store_true", help="print the full report instead")
    parser.add_argument("--save", nargs="?", const="stats", metavar="PATH",
                        help="save charts + raw data to PATH (default: ./stats)")
    parser.add_argument("--export", choices=["csv", "json"],
                        help="export raw recorded events (csv|json)")
    parser.add_argument("--export-path", metavar="PATH", help="directory for --export files")
    parser.add_argument("--reset", action="store_true", help="delete all telemetry data")
    parser.add_argument("--yes", action="store_true", help="confirm --reset without prompting")
    parser.set_defaults(func=run)


def _time_window(args: argparse.Namespace) -> tuple[float | None, float | None]:
    now = time.time()
    if args.today:
        start = time.mktime(time.strptime(time.strftime("%Y-%m-%d"), "%Y-%m-%d"))
        return start, None
    if getattr(args, "7d"):
        return now - 7 * _DAY, None
    if getattr(args, "30d"):
        return now - 30 * _DAY, None
    return None, None


def _confirm_reset(settings: Settings, args: argparse.Namespace) -> bool:
    if args.yes:
        return True
    if sys.stdin.isatty():
        answer = input("Delete ALL recorded telemetry data? Type 'yes' to confirm: ")
        return answer.strip().lower() == "yes"
    print("Reset requires confirmation: run `jevXagent statistics --reset --yes`", file=sys.stderr)
    return False


def run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()
    store = TelemetryStore(settings)

    if args.reset:
        if not _confirm_reset(settings, args):
            return 1
        removed = store.reset()
        print(f"Telemetry reset: {removed} records deleted from {settings.db_path()}")
        return 0

    since_ts, until_ts = _time_window(args)
    stats = build_stats(store, since_ts, until_ts, settings)

    if args.report:
        print(render_report(stats, settings))
    else:
        print(render_dashboard(stats))

    if args.save:
        outdir = Path(args.save)
        files = save_charts(
            outdir, stats["routing"], stats["breakdown"], stats["series"],
            stats["requests"], stats["decisions"],
        )
        print("\nStatistics saved:")
        for path in files:
            print(f"  {path}")

    if args.export:
        outdir = Path(args.export_path or "stats")
        outdir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")
        payload = {
            "generated": stats["generated"],
            "routing": stats["routing"],
            "breakdown": stats["breakdown"],
            "agreement": stats.get("agreement", {}),
            "series": stats["series"],
            "tokens": stats["tokens"],
            "savings": stats["savings"],
            "evidence": stats["evidence"],
            "requests": stats["requests"],
            "decisions": stats["decisions"],
        }
        if args.export == "json":
            path = outdir / f"statistics_{stamp}.json"
            path.write_text(json.dumps(payload, indent=2, default=str), encoding="utf-8")
        else:
            path = outdir / f"statistics_{stamp}.csv"
            rows = [
                {k: v for k, v in d.items() if not isinstance(v, (dict, list))}
                for d in stats["decisions"]
            ]
            if rows:
                import csv

                with path.open("w", newline="", encoding="utf-8") as handle:
                    writer = csv.DictWriter(handle, fieldnames=sorted(rows[0].keys()))
                    writer.writeheader()
                    writer.writerows(rows)
        print(f"\nRaw data exported: {path}")

    store.close()
    return 0


def render_dashboard(stats: dict) -> str:
    routing = stats["routing"]
    tokens = stats["tokens"]
    savings = stats["savings"]
    evidence = stats["evidence"]
    agreement = stats.get("agreement", {})
    total = routing["total_decisions"]

    def rate(num: int) -> str:
        return f"{num / total * 100:.1f}%" if total else "n/a"

    def row(label: str, value: str) -> str:
        return f"║ {label:<35}{value:>14} ║"

    messages_proxied = sum(1 for r in stats["requests"] if r.get("operation") == "messages")

    lines = [
        "╔═══════════════════════════════════════════════════════╗",
        "║                  jevXagent Statistics                 ║",
        "║            When JEV Meets LLM Agent                   ║",
        "╠═══════════════════════════════════════════════════════╣",
        row("Total decision events", f"{total}"),
        row("JEV handled", f"{routing['jev_handled']}"),
        row("Claude handled", f"{routing['claude_handled']}"),
        row("JEV fallback", f"{routing['jev_fallback']}"),
        row("JEV routing rate", rate(routing["jev_handled"])),
        "╠═══════════════════════════════════════════════════════╣",
        row("Verification: compared", f"{agreement.get('compared', 0)}"),
        row("  JEV agrees with Claude", f"{agreement.get('agree', 0)}"),
        row("  JEV disagrees", f"{agreement.get('disagree', 0)}"),
        row("  JEV unavailable", f"{agreement.get('unavailable', 0)}"),
        row("Agreement rate", _cell(agreement.get('agreement_rate'), "%")),
        "╠═══════════════════════════════════════════════════════╣",
        row("Messages proxied (via Claude)", f"{messages_proxied}"),
        "╠═══════════════════════════════════════════════════════╣",
        row("JEV latency (measured)", _cell(routing.get("jev_avg_ms_measured"), "ms")),
        row("Claude latency (measured)", _cell(routing.get("claude_avg_ms_measured"), "ms")),
        "╠═══════════════════════════════════════════════════════╣",
        row("Claude input tokens (measured)", _cell(tokens["claude_input"], "")),
        row("Claude output tokens (measured)", _cell(tokens["claude_output"], "")),
        row("JEV input tokens (measured)", _cell(tokens["jev_input"], "")),
        row("JEV output tokens (measured)", _cell(tokens["jev_output"], "")),
        "╠═══════════════════════════════════════════════════════╣",
        row("Estimated Claude tokens avoided*", _cell(savings.get("est_claude_tokens_avoided"), "")),
        row("Estimated latency avoided*", _cell(savings.get("est_claude_latency_avoided_ms"), "ms")),
        row("Estimated cost avoided*", _cell(savings.get("est_cost_avoided"), "USD")),
        "╚═══════════════════════════════════════════════════════╝",
        "",
        "* estimated — see methodology below",
        "",
        "════════ Decision categories ════════",
        categories_chart(routing_category_breakdown(stats)),
        "",
        "════════ Latency comparison ═════════",
        latency_chart(routing),
        "",
        "════════ Evidence ════════",
    ]
    for label, value in evidence.items():
        lines.append(f"  {'✓' if value != 'unavailable' else '~'} {label:<18}: {value}")
    lines += [
        "  ✓ = measured     ~ = estimated     n/a = unavailable (never invented)",
        "═══════════════════════════════════════",
        f"Data store: {stats.get('generated', '')}",
    ]
    if stats["series"] and len(stats["series"]) > 1:
        lines += ["", "════════ Daily series ════════",
                  "Date        JEV    Claude   Fallback   Messages"]
        for day in stats["series"]:
            lines.append(
                f"{day['date']}   {day['jev']:<6} {day['claude']:<8} {day['fallback']:<9} {day['messages']}"
            )
    return "\n".join(lines)


def routing_category_breakdown(stats: dict) -> dict:
    return stats["breakdown"]


def _cell(value, unit: str) -> str:
    if value is None:
        return "n/a"
    if isinstance(value, float) and value != int(value):
        text = f"{value:,.1f}"
    else:
        text = f"{int(value):,}" if isinstance(value, float) else f"{value:,}"
    return f"{text} {unit}" if unit else text
