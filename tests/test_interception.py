"""Workflow interception: observable decision events in /v1/messages traffic.

Covers both the pure detection helpers (router/interceptor.py) and the
end-to-end wiring in the proxy (detection → DecisionExecutor → JEV), plus
fallback, loop/order, session isolation and streaming preservation.
"""

import asyncio
import json

import httpx
import pytest

from conftest import CLIENT_KEY
from jevxagent.router import interceptor
from jevxagent.telemetry.events import DecisionType

TOOLS = [{"name": "Read"}, {"name": "Bash"}, {"name": "Edit"}]


def _payload(**overrides) -> dict:
    base = {
        "model": "claude-sonnet-5",
        "max_tokens": 100,
        "messages": [{"role": "user", "content": "do the task"}],
        "tools": TOOLS,
    }
    base.update(overrides)
    return base


async def _drain(app) -> None:
    while app.state.background_tasks:
        await asyncio.gather(*list(app.state.background_tasks), return_exceptions=True)


# ---- pure detection helpers ----


def test_extract_candidate_tools():
    assert interceptor.extract_candidate_tools(_payload()) == ["Read", "Bash", "Edit"]
    assert interceptor.extract_candidate_tools({"messages": []}) == []
    assert interceptor.extract_candidate_tools({"tools": "nope"}) == []


def test_extract_tool_use_names():
    content = [{"type": "tool_use", "name": "Bash"}, {"type": "text", "text": "hi"}]
    assert interceptor.extract_tool_use_names(content) == ["Bash"]
    assert interceptor.extract_tool_use_names([{"type": "text", "text": "hi"}]) == []
    assert interceptor.extract_tool_use_names("not a list") == []


def test_detect_tool_selection_requires_both_sides():
    # no tool selected -> None
    assert interceptor.detect_tool_selection(_payload(), []) is None
    # tool selected but no declared candidates -> None
    assert interceptor.detect_tool_selection({"messages": []}, ["Bash"]) is None


def test_detect_tool_selection_builds_choice_event():
    event = interceptor.detect_tool_selection(_payload(), ["Bash"], request_id="r1", context="ctx")
    assert event is not None
    assert event.decision_type == DecisionType.TOOL_SELECTION
    assert event.answer_format == "choice"
    assert event.options == ["Read", "Bash", "Edit"]
    assert event.candidate_action == "Bash"
    assert event.source == "intercept"
    assert event.request_id == "r1"
    assert event.context == "ctx"
    assert event.complexity == 0.0


def test_conversation_fingerprint_stable_and_distinct():
    a1 = interceptor.conversation_fingerprint({"messages": [{"role": "user", "content": "task A"}]})
    a2 = interceptor.conversation_fingerprint(
        {"messages": [{"role": "user", "content": "task A"}, {"role": "assistant", "content": "x"}]}
    )
    b = interceptor.conversation_fingerprint({"messages": [{"role": "user", "content": "task B"}]})
    assert a1 == a2  # same first user message -> same fingerprint
    assert a1 != b


def test_build_intercept_context_trims():
    ctx = interceptor.build_intercept_context(
        {"messages": [{"role": "user", "content": "word " * 5000}]}, max_chars=200
    )
    assert len(ctx) < 400
    assert "[context truncated]" in ctx


# ---- end-to-end workflow ----


def _enable(settings):
    settings.jev_enabled = True
    settings.routing_enabled = True
    settings.intercept_enabled = True
    return settings


async def test_normal_generation_does_not_invoke_jev(app, client, settings, store, fake_jev):
    _enable(settings)
    response = await client.post(
        "/v1/messages",
        json=_payload(tools=[]),
        headers={"x-api-key": CLIENT_KEY},
    )
    assert response.status_code == 200
    await _drain(app)
    assert store.fetch_decisions() == []
    assert fake_jev.seen == []


async def test_tool_selection_routes_to_jev(app, client, settings, store, fake_jev, fake_claude):
    _enable(settings)
    fake_claude.tool_use_queue = ["Bash"]  # Claude selects "Bash"
    fake_jev.answers = {
        "decision": {
            "type": "choice",
            "choice": "Read",
            "probabilities": {"Read": 0.9, "Bash": 0.06, "Edit": 0.04},
            "confidence": 0.9,
        }
    }
    response = await client.post(
        "/v1/messages",
        json=_payload(),
        headers={"x-api-key": CLIENT_KEY, "x-request-id": "req-1"},
    )
    assert response.status_code == 200
    await _drain(app)

    decisions = store.fetch_decisions()
    assert len(decisions) == 1
    d = decisions[0]
    assert d["decision_type"] == "tool_selection"
    assert d["route"] == "jev"
    assert d["fallback"] == 0
    assert d["meta"]["source"] == "intercept"
    assert d["meta"]["candidate_action"] == "Bash"  # Claude's observed choice
    # verification: JEV chose "Read", Claude chose "Bash" -> disagreement
    assert d["meta"]["jev_choice"] == "Read"
    assert d["meta"]["verdict"] == "disagree"
    assert d["meta"]["agreement"] is False

    sent = json.loads(fake_jev.seen[0].content)
    question = sent["questions"]["decision"]
    assert question["type"] == "choice"
    assert set(question["criteria"].keys()) == {"Read", "Bash", "Edit"}


async def test_tool_selection_agree_records_verdict(app, client, settings, store, fake_jev, fake_claude):
    _enable(settings)
    fake_claude.tool_use_queue = ["Read"]
    fake_jev.answers = {
        "decision": {
            "type": "choice",
            "choice": "Read",
            "probabilities": {"Read": 0.9, "Bash": 0.06, "Edit": 0.04},
            "confidence": 0.9,
        }
    }
    response = await client.post(
        "/v1/messages", json=_payload(), headers={"x-api-key": CLIENT_KEY}
    )
    assert response.status_code == 200
    await _drain(app)
    d = store.fetch_decisions()[0]
    assert d["route"] == "jev"
    assert d["meta"]["verdict"] == "agree"
    assert d["meta"]["agreement"] is True
    assert d["meta"]["jev_choice"] == "Read"


async def test_intercept_disabled_does_not_record(app, client, settings, store, fake_jev, fake_claude):
    settings.jev_enabled = True
    settings.routing_enabled = True
    settings.intercept_enabled = False
    fake_claude.tool_use_queue = ["Bash"]
    response = await client.post(
        "/v1/messages", json=_payload(), headers={"x-api-key": CLIENT_KEY}
    )
    assert response.status_code == 200
    await _drain(app)
    assert store.fetch_decisions() == []
    assert fake_jev.seen == []


async def test_multiple_tool_decisions_preserve_order(app, client, settings, store, fake_claude):
    _enable(settings)
    fake_claude.tool_use_queue = ["Bash", "Read", "Edit", None]  # 3 tool uses, then end
    for i in range(4):
        response = await client.post(
            "/v1/messages",
            json=_payload(),
            headers={"x-api-key": CLIENT_KEY, "x-request-id": f"req-{i}"},
        )
        assert response.status_code == 200
    await _drain(app)

    decisions = store.fetch_decisions()
    assert len(decisions) == 3
    ordered = sorted(decisions, key=lambda d: d["request_id"])
    assert [d["request_id"] for d in ordered] == ["req-0", "req-1", "req-2"]
    assert [d["meta"]["candidate_action"] for d in ordered] == ["Bash", "Read", "Edit"]
    # all belong to the same conversation (same first user message)
    assert len({d["meta"]["conversation_id"] for d in ordered}) == 1


async def test_jev_failure_falls_back_and_workflow_continues(app, client, settings, store, fake_jev, fake_claude):
    _enable(settings)
    fake_jev.raise_error = httpx.ConnectTimeout("slow")
    fake_claude.tool_use_queue = ["Bash"]
    response = await client.post(
        "/v1/messages", json=_payload(), headers={"x-api-key": CLIENT_KEY}
    )
    assert response.status_code == 200  # workflow is unaffected
    await _drain(app)
    decisions = store.fetch_decisions()
    assert len(decisions) == 1
    assert decisions[0]["fallback"] == 1
    assert decisions[0]["route"] == "claude"
    assert decisions[0]["meta"]["verdict"] == "jev_unavailable"


async def test_independent_conversations_do_not_share_state(app, client, settings, store, fake_claude):
    _enable(settings)
    fake_claude.tool_use_queue = ["Bash", "Read"]
    for seed in ("conversation A task", "conversation B task"):
        response = await client.post(
            "/v1/messages",
            json=_payload(messages=[{"role": "user", "content": seed}]),
            headers={"x-api-key": CLIENT_KEY},
        )
        assert response.status_code == 200
    await _drain(app)
    decisions = store.fetch_decisions()
    assert len(decisions) == 2
    assert len({d["meta"]["conversation_id"] for d in decisions}) == 2


async def test_streaming_preserved_and_detects_tool_use(app, client, settings, store, fake_claude):
    _enable(settings)
    fake_claude.stream_tool_use = True
    response = await client.post(
        "/v1/messages",
        json=_payload(stream=True),
        headers={"x-api-key": CLIENT_KEY},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert "content_block_start" in response.text  # stream relayed verbatim
    await _drain(app)
    decisions = store.fetch_decisions()
    assert len(decisions) == 1
    assert decisions[0]["decision_type"] == "tool_selection"
    assert decisions[0]["meta"]["candidate_action"] == "Bash"
