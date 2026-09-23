"""Telemetry store + metrics aggregation (measured vs estimated separation)."""

import time

import pytest

from jevxagent.config import Settings
from jevxagent.telemetry import metrics
from jevxagent.telemetry.events import DecisionRecord, RequestRecord
from jevxagent.telemetry.storage import TelemetryStore


def _request(**overrides):
    base = dict(
        request_id="r1", model="m", operation="messages", stream=False, route="claude",
        status=200, total_ms=100.0, claude_ms=90.0, input_tokens=10, output_tokens=5,
    )
    base.update(overrides)
    return RequestRecord(**base)


def _decision(**overrides):
    base = dict(
        request_id="r1", decision_type="binary_decision", route="jev",
        routing_status="routed_jev", fallback=False, confidence=0.95, status="success",
        jev_ms=30.0, jev_input_tokens=20, jev_output_tokens=5,
    )
    base.update(overrides)
    return DecisionRecord(**base)


def test_store_roundtrip(store):
    store.record_request(_request())
    store.record_decision(_decision())
    requests = store.fetch_requests()
    decisions = store.fetch_decisions()
    assert len(requests) == 1
    assert requests[0]["input_tokens"] == 10
    assert decisions[0]["route"] == "jev"
    assert decisions[0]["confidence"] == 0.95


def test_store_time_filter(store):
    now = time.time()
    store.record_request(_request(ts=now - 10 * 86400))
    store.record_request(_request(request_id="r2", ts=now - 60))
    assert len(store.fetch_requests(since_ts=now - 86400)) == 1


def test_store_reset(store):
    store.record_request(_request())
    store.record_decision(_decision())
    removed = store.reset()
    assert removed == 2
    assert store.fetch_requests() == []
    assert store.fetch_decisions() == []


def test_routing_stats():
    decisions = [
        _decision().to_row(),
        _decision(request_id="r2", jev_ms=50.0).to_row(),
        _decision(request_id="r3", route="claude", routing_status="routed_claude",
                  jev_ms=0.0, claude_ms=600.0, confidence=None).to_row(),
        _decision(request_id="r4", route="claude", routing_status="fallback_claude",
                  fallback=True, claude_ms=700.0, error="jev_provider_error: timeout").to_row(),
    ]
    stats = metrics.routing_stats(decisions)
    assert stats["total_decisions"] == 4
    assert stats["jev_handled"] == 2
    assert stats["claude_handled"] == 2
    assert stats["jev_fallback"] == 1
    assert stats["jev_rate"] == 50.0
    assert stats["jev_avg_ms_measured"] == 40.0
    assert stats["claude_avg_ms_measured"] == 650.0
    assert "jev_provider_error" in stats["fallback_reasons"]


def test_category_breakdown():
    decisions = [
        _decision().to_row(),
        _decision(request_id="r2", decision_type="verification").to_row(),
        _decision(request_id="r3", decision_type="verification", route="claude",
                  fallback=True).to_row(),
    ]
    breakdown = metrics.category_breakdown(decisions)
    assert breakdown["binary_decision"]["total"] == 1
    assert breakdown["verification"]["total"] == 2
    assert breakdown["verification"]["jev"] == 1
    assert breakdown["verification"]["fallback"] == 1


def test_token_totals_separates_providers():
    requests = [_request().to_row(), _request(request_id="r2", input_tokens=30, output_tokens=7).to_row()]
    decisions = [_decision().to_row(), _decision(request_id="r2", route="claude",
                                                 claude_input_tokens=40, claude_output_tokens=8).to_row()]
    tokens = metrics.token_totals(requests, decisions)
    assert tokens["claude_input"] == 40 + 40
    assert tokens["claude_output"] == 5 + 7 + 8
    assert tokens["jev_input"] == 20
    assert tokens["jev_output"] == 5


def test_estimate_savings_historical_baseline(settings):
    decisions = [
        _decision().to_row(),  # jev: 20 in / 5 out tokens, 30 ms
        _decision(request_id="r2", route="claude", routing_status="routed_claude",
                  fallback=False, claude_ms=600.0, jev_ms=0.0,
                  claude_input_tokens=50, claude_output_tokens=10,
                  jev_input_tokens=None, jev_output_tokens=None).to_row(),
    ]
    savings = metrics.estimate_savings(decisions, settings)
    assert savings["jev_decisions_evaluated"] == 1
    assert savings["est_claude_tokens_avoided"] == 35  # (50+10) - (20+5)
    assert savings["est_claude_latency_avoided_ms"] == 570.0
    assert savings["est_cost_avoided"] is None  # no prices configured
    assert savings["baseline_tokens_method"] == "historical"


def test_estimate_savings_unavailable_without_baseline(settings):
    decisions = [_decision().to_row()]
    savings = metrics.estimate_savings(decisions, settings)
    assert savings["est_claude_tokens_avoided"] is None
    assert savings["est_claude_latency_avoided_ms"] is None


def test_estimate_savings_configured_fallback(settings):
    settings.claude_est_ms_per_decision = 500.0
    settings.claude_est_input_tokens_per_decision = 60.0
    settings.claude_est_output_tokens_per_decision = 10.0
    settings.claude_input_price_per_mtok = 3.0
    settings.claude_output_price_per_mtok = 15.0
    settings.jev_input_price_per_mtok = 0.1
    settings.jev_output_price_per_mtok = 0.3
    decisions = [_decision().to_row()]
    savings = metrics.estimate_savings(decisions, settings)
    assert savings["est_claude_tokens_avoided"] == 45  # 70 - 25
    assert savings["est_claude_latency_avoided_ms"] == 470.0
    assert savings["est_cost_avoided"] is not None
    assert savings["est_cost_avoided"] > 0
    assert savings["baseline_latency_method"] == "configured"


def test_daily_series():
    now = time.time()
    day1 = now - 2 * 86400
    day2 = now - 60
    decisions = [_decision(ts=day1).to_row(), _decision(request_id="r2", ts=day2).to_row()]
    requests = [_request(ts=day2).to_row()]
    series = metrics.daily_series(decisions, requests)
    assert len(series) == 2
    assert series[0]["jev"] == 1
    assert series[1]["jev"] == 1
    assert series[1]["messages"] == 1


def test_evidence_flags(settings):
    decisions = [_decision().to_row()]
    requests = [_request().to_row()]
    savings = metrics.estimate_savings(decisions, settings)
    tokens = metrics.token_totals(requests, decisions)
    evidence = metrics.evidence(decisions, requests, savings, tokens)
    assert evidence["provider_calls"] == "measured"
    assert evidence["token_usage"] == "measured (API-reported)"
    assert evidence["token_savings"] == "unavailable"
