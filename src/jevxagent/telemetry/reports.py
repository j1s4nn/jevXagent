"""Full report generation with a mandatory measurement-methodology section."""

from __future__ import annotations

import time

from ..config import Settings
from . import metrics


def build_stats(store, since_ts: float | None, until_ts: float | None, settings: Settings) -> dict:
    requests = store.fetch_requests(since_ts, until_ts)
    decisions = store.fetch_decisions(since_ts, until_ts)
    routing = metrics.routing_stats(decisions)
    breakdown = metrics.category_breakdown(decisions)
    agreement = metrics.agreement_stats(decisions)
    series = metrics.daily_series(decisions, requests)
    tokens = metrics.token_totals(requests, decisions)
    savings = metrics.estimate_savings(decisions, settings)
    evidence = metrics.evidence(decisions, requests, savings, tokens)
    return {
        "requests": requests,
        "decisions": decisions,
        "routing": routing,
        "breakdown": breakdown,
        "agreement": agreement,
        "series": series,
        "tokens": tokens,
        "savings": savings,
        "evidence": evidence,
        "generated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }


def render_report(stats: dict, settings: Settings) -> str:
    routing = stats["routing"]
    tokens = stats["tokens"]
    savings = stats["savings"]
    evidence = stats["evidence"]
    agreement = stats.get("agreement", {})
    lines = [
        "=" * 70,
        "                      jevXagent Report",
        "                 When JEV Meets LLM Agent",
        f"                 generated: {stats['generated']}",
        "=" * 70,
        "",
        "1. Usage summary",
        "----------------",
        f"   Messages requests relayed : {sum(1 for r in stats['requests'] if r.get('operation') == 'messages')}",
        f"   Decision events           : {routing['total_decisions']}",
        f"   JEV handled               : {routing['jev_handled']}",
        f"   Claude handled            : {routing['claude_handled']}",
        f"   JEV fallback              : {routing['jev_fallback']}",
        "",
        "2. Routing summary",
        "------------------",
        f"   JEV routing rate          : {routing['jev_rate'] if routing['jev_rate'] is not None else 'n/a'}",
    ]
    for reason, count in sorted(routing["fallback_reasons"].items(), key=lambda kv: -kv[1]):
        lines.append(f"     fallback [{reason}]      : {count}")

    lines += [
        "",
        "3. Verification (JEV vs Claude agreement)",
        "-----------------------------------------",
        f"   Compared decisions        : {agreement['compared']}",
        f"   Agree                     : {agreement['agree']}",
        f"   Disagree                  : {agreement['disagree']}",
        f"   JEV unavailable (fallback): {agreement['unavailable']}",
        f"   Agreement rate            : {agreement['agreement_rate'] if agreement['agreement_rate'] is not None else 'n/a'}",
        "",
        "4. Latency (measured)",
        "---------------------",
        f"   JEV average               : {_fmt(routing.get('jev_avg_ms_measured'), 'ms')}",
        f"   Claude average            : {_fmt(routing.get('claude_avg_ms_measured'), 'ms')}",
        "",
        "5. Token usage (measured, API-reported where available)",
        "--------------------------------------------------------",
        f"   Claude input              : {_fmt(tokens['claude_input'], 'tokens')}",
        f"   Claude output             : {_fmt(tokens['claude_output'], 'tokens')}",
        f"   Claude cache read         : {_fmt(tokens['claude_cache_read'], 'tokens')}",
        f"   JEV input                 : {_fmt(tokens['jev_input'], 'tokens')}",
        f"   JEV output                : {_fmt(tokens['jev_output'], 'tokens')}",
        "",
        "6. Estimated savings (clearly labelled estimates)",
        "--------------------------------------------------",
        f"   Estimated Claude tokens avoided  : {_fmt(savings.get('est_claude_tokens_avoided'), 'tokens')}",
        f"   Estimated latency avoided        : {_fmt(savings.get('est_claude_latency_avoided_ms'), 'ms')}",
        f"   Estimated cost avoided           : {_fmt(savings.get('est_cost_avoided'), 'USD')}",
        "",
        "7. Decision categories",
        "-----------------------",
    ]
    for name, entry in sorted(stats["breakdown"].items(), key=lambda kv: -kv[1]["total"]):
        lines.append(f"   {name:<24} total={entry['total']:<6} JEV={entry['jev']:<6} Claude={entry['claude']}")
    lines += [
        "",
        "8. Fallback / errors",
        "--------------------",
        f"   Fallbacks: {routing['jev_fallback']}  JEV failures: {routing['jev_failed']}",
        "",
        "9. Measurement methodology",
        "--------------------------",
    ]
    for label, value in evidence.items():
        lines.append(f"   {label:<18} : {value}")
    lines += [
        "",
        "Measured values come only from recorded provider calls.",
        "Estimated values are projections from historical baselines of the same",
        "decision category or from configured defaults (CLAUDE_EST_* / price",
        "settings). They are NOT measurements. Unavailable values are shown as n/a.",
        "=" * 70,
    ]
    return "\n".join(lines)


def _fmt(value, unit: str) -> str:
    if value is None:
        return "n/a"
    return f"{value} {unit}" if unit else str(value)
