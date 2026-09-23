"""Telemetry aggregation — everything here is computed from stored records.

Strict separation:
- MEASURED: values recorded from real provider calls (latency, tokens
  reported by APIs, statuses, fallbacks).
- ESTIMATED: projections (e.g. "Claude tokens avoided") computed from
  historical baselines or configured defaults. Always labelled.
- UNAVAILABLE: returned as None — never invented.
"""

from __future__ import annotations

import time
from collections import Counter, defaultdict
from typing import Optional

from ..config import Settings


def _avg(values: list[float]) -> Optional[float]:
    return round(sum(values) / len(values), 1) if values else None


def routing_stats(decisions: list[dict]) -> dict:
    total = len(decisions)
    jev = [d for d in decisions if d.get("route") == "jev"]
    claude = [d for d in decisions if d.get("route") == "claude"]
    fallback = [d for d in decisions if d.get("fallback")]
    jev_success = [d for d in jev if d.get("status") == "success"]
    jev_fail = [d for d in jev if d.get("status") != "success"]
    fallback_reasons = Counter(
        (
            (d.get("meta") or {}).get("fallback_reason")
            or d.get("error")
            or "unknown"
        ).split(":")[0]
        for d in fallback
    )
    return {
        "total_decisions": total,
        "jev_handled": len(jev_success),
        "claude_handled": len(claude),
        "jev_fallback": len(fallback),
        "jev_failed": len(jev_fail),
        "jev_rate": round(len(jev_success) / total * 100, 1) if total else None,
        "jev_avg_ms_measured": _avg([d["jev_ms"] for d in jev_success if d.get("jev_ms")]),
        "claude_avg_ms_measured": _avg([d["claude_ms"] for d in claude if d.get("claude_ms")]),
        "fallback_reasons": dict(fallback_reasons),
    }


def category_breakdown(decisions: list[dict]) -> dict:
    by_type: dict[str, dict] = {}
    for d in decisions:
        key = d.get("decision_type") or "other"
        entry = by_type.setdefault(key, {"total": 0, "jev": 0, "claude": 0, "fallback": 0})
        entry["total"] += 1
        if d.get("route") == "jev":
            entry["jev"] += 1
        else:
            entry["claude"] += 1
        if d.get("fallback"):
            entry["fallback"] += 1
    return by_type


def agreement_stats(decisions: list[dict]) -> dict:
    """JEV-vs-Claude agreement over intercepted decisions that were verified.

    Only decisions with a `verdict` of "agree" or "disagree" are comparable
    (i.e. intercepted tool selections where JEV succeeded). "jev_unavailable"
    and manual decisions are excluded from the rate.
    """
    compared = [d for d in decisions if (d.get("meta") or {}).get("verdict") in ("agree", "disagree")]
    agree = [d for d in compared if d["meta"]["verdict"] == "agree"]
    disagree = [d for d in compared if d["meta"]["verdict"] == "disagree"]
    unavailable = [d for d in decisions if (d.get("meta") or {}).get("verdict") == "jev_unavailable"]
    return {
        "compared": len(compared),
        "agree": len(agree),
        "disagree": len(disagree),
        "unavailable": len(unavailable),
        "agreement_rate": round(len(agree) / len(compared) * 100, 1) if compared else None,
    }


def _local_day(ts: float) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ts))


def daily_series(decisions: list[dict], requests: list[dict]) -> list[dict]:
    days: dict[str, dict] = defaultdict(
        lambda: {"date": "", "jev": 0, "claude": 0, "fallback": 0, "messages": 0}
    )
    for d in decisions:
        day = days[_local_day(d["ts"])]
        day["date"] = _local_day(d["ts"])
        if d.get("route") == "jev":
            day["jev"] += 1
        else:
            day["claude"] += 1
        if d.get("fallback"):
            day["fallback"] += 1
    for r in requests:
        day = days[_local_day(r["ts"])]
        day["date"] = _local_day(r["ts"])
        if r.get("operation") == "messages":
            day["messages"] += 1
    return [days[k] for k in sorted(days)]


def token_totals(requests: list[dict], decisions: list[dict]) -> dict:
    sums = {
        "claude_input": 0,
        "claude_output": 0,
        "claude_cache_read": 0,
        "claude_cache_creation": 0,
        "jev_input": 0,
        "jev_output": 0,
    }
    for r in requests:
        for key in ("input_tokens", "output_tokens"):
            value = r.get(key)
            if isinstance(value, int):
                sums["claude_" + key.replace("_tokens", "")] += value
        for key, target in (
            ("cache_read_input_tokens", "claude_cache_read"),
            ("cache_creation_input_tokens", "claude_cache_creation"),
        ):
            value = r.get(key)
            if isinstance(value, int):
                sums[target] += value
    for d in decisions:
        if d.get("route") == "jev":
            for key, target in (
                ("jev_input_tokens", "jev_input"),
                ("jev_output_tokens", "jev_output"),
            ):
                value = d.get(key)
                if isinstance(value, int):
                    sums[target] += value
        else:
            for key, target in (
                ("claude_input_tokens", "claude_input"),
                ("claude_output_tokens", "claude_output"),
            ):
                value = d.get(key)
                if isinstance(value, int):
                    sums[target] += value
    return sums


def estimate_savings(decisions: list[dict], settings: Settings) -> dict:
    """Estimated avoided Claude work for JEV-routed decisions.

    Baseline priority:
      1. measured historical Claude-routed decisions of the same type (mean)
      2. configured estimates (CLAUDE_EST_*)
      3. unavailable (None)
    """
    jev_success = [
        d for d in decisions if d.get("route") == "jev" and d.get("status") == "success"
    ]
    claude_clean = [
        d for d in decisions
        if d.get("route") == "claude" and not d.get("fallback") and d.get("status") == "success"
    ]

    claude_baseline: dict[str, dict] = {}
    for d in claude_clean:
        entry = claude_baseline.setdefault(
            d.get("decision_type") or "other", {"ms": [], "in_t": [], "out_t": []}
        )
        if d.get("claude_ms"):
            entry["ms"].append(d["claude_ms"])
        if d.get("claude_input_tokens") is not None:
            entry["in_t"].append(d["claude_input_tokens"])
        if d.get("claude_output_tokens") is not None:
            entry["out_t"].append(d["claude_output_tokens"])

    est_tokens = 0.0
    est_ms = 0.0
    est_cost = 0.0
    usable = 0
    tokens_usable = 0
    cost_usable = 0
    tokens_method = "none"
    for d in jev_success:
        key = d.get("decision_type") or "other"
        base = claude_baseline.get(key)
        base_ms = _avg(base["ms"]) if base else None
        base_in = round(sum(base["in_t"]) / len(base["in_t"]), 1) if base and base["in_t"] else None
        base_out = round(sum(base["out_t"]) / len(base["out_t"]), 1) if base and base["out_t"] else None

        if base_ms is None:
            base_ms = settings.claude_est_ms_per_decision or None
        if base_ms is not None and d.get("jev_ms"):
            est_ms += max(0.0, base_ms - d["jev_ms"])
            usable += 1
        tokens_method = "historical" if (base and base["in_t"]) else "configured"
        if base_in is None:
            base_in = settings.claude_est_input_tokens_per_decision or None
        if base_out is None:
            base_out = settings.claude_est_output_tokens_per_decision or None
        if base_in is None or base_out is None:
            continue
        tokens_usable += 1
        baseline_tokens = base_in + base_out
        jev_tokens = (d.get("jev_input_tokens") or 0) + (d.get("jev_output_tokens") or 0)
        est_tokens += max(0.0, baseline_tokens - jev_tokens)
        if settings.claude_input_price_per_mtok and settings.claude_output_price_per_mtok:
            claude_cost = (
                base_in * settings.claude_input_price_per_mtok / 1_000_000
                + base_out * settings.claude_output_price_per_mtok / 1_000_000
            )
            jev_cost = 0.0
            if settings.jev_input_price_per_mtok and settings.jev_output_price_per_mtok:
                jev_cost = (
                    (d.get("jev_input_tokens") or 0) * settings.jev_input_price_per_mtok / 1_000_000
                    + (d.get("jev_output_tokens") or 0) * settings.jev_output_price_per_mtok / 1_000_000
                )
            est_cost += max(0.0, claude_cost - jev_cost)
            cost_usable += 1

    return {
        "jev_decisions_evaluated": len(jev_success),
        "est_claude_tokens_avoided": round(est_tokens) if tokens_usable else None,
        "est_claude_latency_avoided_ms": round(est_ms, 1) if usable else None,
        "est_cost_avoided": round(est_cost, 4) if cost_usable else None,
        "baseline_tokens_method": tokens_method if tokens_usable else "unavailable",
        "baseline_latency_method": "historical" if claude_baseline else ("configured" if usable else "unavailable"),
    }


def evidence(decisions: list[dict], requests: list[dict], savings: dict, tokens: dict) -> dict:
    return {
        "provider_calls": "measured" if decisions or requests else "unavailable",
        "latency": "measured" if any(d.get("jev_ms") or d.get("claude_ms") for d in decisions) else "unavailable",
        "token_usage": (
            "measured (API-reported)"
            if any(isinstance(r.get(k), int) for r in requests for k in ("input_tokens", "output_tokens"))
            else "unavailable"
        ),
        "token_savings": "estimated" if savings.get("est_claude_tokens_avoided") is not None else "unavailable",
        "cost_savings": "estimated" if savings.get("est_cost_avoided") is not None else "unavailable",
        "latency_savings": "estimated" if savings.get("est_claude_latency_avoided_ms") is not None else "unavailable",
        "baseline": savings.get("baseline_tokens_method", "unavailable"),
    }
