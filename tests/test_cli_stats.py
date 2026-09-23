"""CLI statistics: dashboard rendering, export, reset, time windows."""

import argparse
import json
import time

import pytest

from jevxagent.cli.statistics import _time_window, render_dashboard, run
from jevxagent.telemetry.events import DecisionRecord, RequestRecord


def _empty_stats():
    return {
        "requests": [],
        "decisions": [],
        "routing": {
            "total_decisions": 0, "jev_handled": 0, "claude_handled": 0,
            "jev_fallback": 0, "jev_failed": 0, "jev_rate": None,
            "jev_avg_ms_measured": None, "claude_avg_ms_measured": None,
            "fallback_reasons": {},
        },
        "breakdown": {},
        "series": [],
        "tokens": {"claude_input": 0, "claude_output": 0, "claude_cache_read": 0,
                   "claude_cache_creation": 0, "jev_input": 0, "jev_output": 0},
        "savings": {"jev_decisions_evaluated": 0, "est_claude_tokens_avoided": None,
                    "est_claude_latency_avoided_ms": None, "est_cost_avoided": None,
                    "baseline_tokens_method": "unavailable", "baseline_latency_method": "unavailable"},
        "evidence": {"provider_calls": "unavailable", "latency": "unavailable",
                     "token_usage": "unavailable", "token_savings": "unavailable",
                     "cost_savings": "unavailable", "latency_savings": "unavailable",
                     "baseline": "unavailable"},
        "generated": "2026-01-01 00:00:00",
    }


def test_dashboard_empty_shows_no_fake_numbers():
    text = render_dashboard(_empty_stats())
    assert "Total decision events" in text
    assert "n/a" in text
    assert "0" in text
    assert "estimated" in text.lower()


def test_time_window_all():
    args = argparse.Namespace(today=False, **{"7d": False, "30d": False})
    assert _time_window(args) == (None, None)


def test_time_window_7d():
    now = time.time()
    args = argparse.Namespace(today=False, **{"7d": True, "30d": False})
    since, until = _time_window(args)
    assert since is not None and abs((now - since) - 7 * 86400) < 10
    assert until is None


def test_time_window_today():
    args = argparse.Namespace(today=True, **{"7d": False, "30d": False})
    since, _ = _time_window(args)
    assert since is not None
    assert time.strftime("%Y-%m-%d", time.localtime(since)) == time.strftime("%Y-%m-%d")


def _make_env(tmp_path, monkeypatch):
    for key in ("DATA_DIR", "CLAUDE_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    env = tmp_path / "envfile"
    env.write_text(f"DATA_DIR={tmp_path / 'data'}\nCLAUDE_API_KEY=x\n", encoding="utf-8")
    monkeypatch.setenv("JEVAXAGENT_ENV_FILE", str(env))
    return tmp_path / "data"


def test_run_export_json(tmp_path, monkeypatch):
    from jevxagent.config import Settings
    from jevxagent.telemetry.storage import TelemetryStore

    data_dir = _make_env(tmp_path, monkeypatch)
    settings = Settings.from_env()
    store = TelemetryStore(settings)
    store.record_decision(
        DecisionRecord(request_id="r1", decision_type="binary_decision", route="jev",
                       status="success", jev_ms=25.0, confidence=0.99)
    )
    store.record_request(RequestRecord(request_id="r1", operation="decision", route="jev"))
    store.close()

    args = argparse.Namespace(
        today=False, **{"7d": False, "30d": False, "all": True},
        report=False, save=None, export="json", export_path=str(tmp_path / "out"),
        reset=False, yes=False,
    )
    assert run(args) == 0
    out_dir = tmp_path / "out"
    files = list(out_dir.glob("statistics_*.json"))
    assert len(files) == 1
    payload = json.loads(files[0].read_text(encoding="utf-8"))
    assert payload["routing"]["jev_handled"] == 1
    assert payload["decisions"][0]["route"] == "jev"


def test_run_reset_requires_confirmation_without_yes(tmp_path, monkeypatch, capsys):
    from jevxagent.config import Settings
    from jevxagent.telemetry.storage import TelemetryStore

    data_dir = _make_env(tmp_path, monkeypatch)
    settings = Settings.from_env()
    store = TelemetryStore(settings)
    store.record_decision(DecisionRecord(request_id="r1", route="claude"))
    store.close()

    args = argparse.Namespace(
        today=False, **{"7d": False, "30d": False, "all": True},
        report=False, save=None, export=None, export_path=None,
        reset=True, yes=False,
    )
    assert run(args) == 1

    store2 = TelemetryStore(settings)
    assert len(store2.fetch_decisions()) == 1
    store2.close()


def test_run_reset_with_yes(tmp_path, monkeypatch):
    from jevxagent.config import Settings
    from jevxagent.telemetry.storage import TelemetryStore

    data_dir = _make_env(tmp_path, monkeypatch)
    settings = Settings.from_env()
    store = TelemetryStore(settings)
    store.record_decision(DecisionRecord(request_id="r1", route="claude"))
    store.close()

    args = argparse.Namespace(
        today=False, **{"7d": False, "30d": False, "all": True},
        report=False, save=None, export=None, export_path=None,
        reset=True, yes=True,
    )
    assert run(args) == 0

    store2 = TelemetryStore(settings)
    assert store2.fetch_decisions() == []
    store2.close()
