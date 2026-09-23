"""CLI: jevXagent benchmark.

Controlled comparison of Claude-only vs JEV-routed decision handling.
Benchmark data is stored in a SEPARATE database (benchmark.db) and is never
mixed with normal production statistics.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

from ..config import Settings
from ..providers.claude import ClaudeProvider
from ..providers.jev import JevProvider
from ..router.classifier import estimate_complexity, infer_decision_type
from ..router.decision import DecisionEvent
from ..router.executor import DecisionExecutor
from ..telemetry.events import new_id
from ..telemetry.storage import TelemetryStore

SAMPLE_SET = Path(__file__).resolve().parents[3] / "examples" / "benchmark_sample.jsonl"


def add_parser(sub: argparse._SubParsersAction) -> None:
    parser = sub.add_parser(
        "benchmark",
        help="compare Claude-only vs JEV-routed decisions on a test set",
        description="Controlled benchmark. Requires a configured Claude API and (for routed mode) JEV.",
    )
    parser.add_argument(
        "--set", metavar="JSONL",
        help=f"test set file (JSONL). Default: {SAMPLE_SET}",
        default=str(SAMPLE_SET),
    )
    parser.add_argument("--mode", choices=["both", "claude-only", "jev-routed"], default="both")
    parser.add_argument("--limit", type=int, default=0, help="limit number of items")
    parser.set_defaults(func=run)


def load_items(path: Path, limit: int) -> list[dict]:
    if not path.is_file():
        print(f"Benchmark set not found: {path}", file=sys.stderr)
        print("Create a JSONL file with lines like:", file=sys.stderr)
        print(
            '  {"question": "Is this a GitHub URL?", "context": "https://github.com/example/example", '
            '"options": [], "expected": "YES"}',
            file=sys.stderr,
        )
        raise SystemExit(2)
    items = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        items.append(json.loads(line))
    return items[:limit] if limit else items


def make_event(item: dict, request_id: str) -> DecisionEvent:
    question = str(item.get("question") or "").strip()
    options = [str(o) for o in (item.get("options") or [])]
    context = str(item.get("context") or "")
    event = DecisionEvent(
        request_id=request_id,
        context=context,
        current_operation=question,
        options=options,
        answer_format="yesno" if not options else "choice",
    )
    try:
        from ..telemetry.events import DecisionType

        event.decision_type = DecisionType(str(item.get("decision_type") or "")) \
            if item.get("decision_type") else infer_decision_type(question, options, context)
    except ValueError:
        event.decision_type = infer_decision_type(question, options, context)
    event.complexity = estimate_complexity(question, options, context)
    return event


def _norm(text: str | None) -> str:
    return (text or "").strip().lower()


async def _async_run(args: argparse.Namespace) -> int:
    settings = Settings.from_env()

    if not settings.claude_api_key:
        print("CLAUDE_API_KEY is not set. Add it to .env first.", file=sys.stderr)
        return 2
    if args.mode != "claude-only":
        jev = JevProvider(settings)
        if not jev.is_configured():
            print(
                "JEV is not configured (JEV_API_KEY / JEV_BASE_URL). "
                "Use --mode claude-only, or configure JEV in .env.",
                file=sys.stderr,
            )
            return 2

    settings.ensure_data_dir()
    bench_store = TelemetryStore(settings, path=settings.data_dir / "benchmark.db")
    claude = ClaudeProvider(settings)
    jev = JevProvider(settings)
    routed_executor = DecisionExecutor(settings, bench_store, claude, jev)
    claude_only_executor = DecisionExecutor(
        replace(settings, jev_enabled=False, routing_enabled=False), bench_store, claude, jev
    )

    items = load_items(Path(args.set), args.limit)
    if not items:
        print("Benchmark set is empty.", file=sys.stderr)
        return 2

    run_id = new_id()
    run_ts = time.time()
    rows = []
    print(f"Benchmark set: {args.set} ({len(items)} items)")
    for index, item in enumerate(items, 1):
        claude_result = None
        routed_result = None

        if args.mode in ("both", "claude-only"):
            event = make_event(item, f"{run_id}-{index}-claude")
            claude_result = await claude_only_executor.execute(event)
            _record_bench(bench_store, run_id, run_ts, "claude-only", item, claude_result)

        if args.mode in ("both", "jev-routed"):
            event = make_event(item, f"{run_id}-{index}-routed")
            routed_result = await routed_executor.execute(event)
            _record_bench(bench_store, run_id, run_ts, "jev-routed", item, routed_result)

        rows.append((item, claude_result, routed_result))
        print(f"  [{index}/{len(items)}] {item.get('question', '')[:60]}")

    await claude.aclose()
    await jev.aclose()

    print("\nMetric                 Claude-only       JEV-routed")
    print("-" * 58)
    for item, claude_result, routed_result in rows:
        question = item.get("question", "")[:34]
        if claude_result and routed_result:
            agree = "yes" if _norm(claude_result["decision"]) == _norm(routed_result["decision"]) else "NO"
            expected = item.get("expected")
            if expected is not None:
                agree += " (vs expected: " + ("match" if _norm(str(expected)) == _norm(routed_result["decision"]) else "MISMATCH") + ")"
            print(f"{question:<24} {claude_result['latency_ms']:>8} ms  {routed_result['latency_ms']:>8} ms  "
                  f"route={routed_result['provider']:<6} agree={agree}")
        elif claude_result:
            print(f"{question:<24} {claude_result['latency_ms']:>8} ms  {'n/a':>8} ms")
        else:
            print(f"{question:<24} {'n/a':>8} ms  {routed_result['latency_ms']:>8} ms  route={routed_result['provider']}")

    bench_store.close()
    print(f"\nBenchmark data stored in: {settings.data_dir / 'benchmark.db'} "
          "(separate from production statistics)")
    return 0


def _record_bench(store: TelemetryStore, run_id: str, run_ts: float, mode: str, item: dict, result: dict) -> None:
    store.record_benchmark(
        {
            "run_id": new_id(),
            "ts": run_ts,
            "mode": mode,
            "item": str(item.get("question", ""))[:200],
            "decision_type": result.get("decision_type", ""),
            "route": result.get("provider", ""),
            "latency_ms": result.get("latency_ms"),
            "input_tokens": None,
            "output_tokens": None,
            "fallback": int(bool(result.get("fallback"))),
            "decision": str(result.get("decision", ""))[:200],
            "reference": str(item.get("expected", ""))[:200],
            "agreement": None,
            "status": "success",
            "error": "",
        }
    )


def run(args: argparse.Namespace) -> int:
    try:
        return asyncio.run(_async_run(args))
    except KeyboardInterrupt:
        return 130
