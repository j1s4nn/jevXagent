"""Decision routing endpoint: JEV routing, fallback, policy gates."""

import pytest

from conftest import CLIENT_KEY, FakeJevTransport


async def _routing_settings(settings):
    settings.jev_enabled = True
    settings.routing_enabled = True
    return settings


async def test_decision_routes_to_jev(client, settings, fake_jev):
    await _routing_settings(settings)
    response = await client.post(
        "/v1/decision",
        json={
            "question": "Is this a GitHub repository URL?",
            "context": "https://github.com/j1s4nn/jevXagent",
        },
        headers={"x-api-key": CLIENT_KEY},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["provider"] == "jev"
    assert body["decision"] == "YES"
    assert body["confidence"] == 0.98
    assert body["fallback"] is False
    assert body["routing_status"] == "routed_jev"
    assert body["decision_type"] == "url_classification"


async def test_decision_multiple_choice_jev(client, settings):
    await _routing_settings(settings)
    response = await client.post(
        "/v1/decision",
        json={
            "question": "Which category?",
            "options": ["api", "database", "css"],
        },
        headers={"x-api-key": CLIENT_KEY},
    )
    body = response.json()
    assert body["provider"] == "jev"
    assert body["decision_type"] == "multiple_choice"


async def test_jev_low_confidence_falls_back_to_claude(client, settings, store, fake_jev, fake_claude):
    from jevxagent.server import create_app
    import httpx

    await _routing_settings(settings)
    fake_jev.content = '{"decision": "YES", "confidence": 0.4}'
    app = create_app(settings, store=store, claude_client=httpx.AsyncClient(transport=fake_claude, base_url="https://upstream.test"),
                     jev_client=httpx.AsyncClient(transport=fake_jev, base_url="https://upstream.test"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            "/v1/decision",
            json={"question": "Is this a GitHub URL?", "context": "https://github.com/a/b"},
            headers={"x-api-key": CLIENT_KEY},
        )
    body = response.json()
    assert body["provider"] == "claude"
    assert body["fallback"] is True
    assert body["routing_status"] == "fallback_claude"
    rows = store.fetch_decisions()
    assert len(rows) == 1
    assert rows[0]["fallback"] == 1
    assert "confidence" in rows[0]["error"]


async def test_jev_malformed_output_falls_back(client, settings, store, fake_jev, fake_claude):
    from jevxagent.server import create_app
    import httpx

    await _routing_settings(settings)
    fake_jev.content = "I think the answer might be yes, probably"
    app = create_app(settings, store=store, claude_client=httpx.AsyncClient(transport=fake_claude, base_url="https://upstream.test"),
                     jev_client=httpx.AsyncClient(transport=fake_jev, base_url="https://upstream.test"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            "/v1/decision",
            json={"question": "Is this valid?", "context": "x"},
            headers={"x-api-key": CLIENT_KEY},
        )
    assert response.json()["fallback"] is True
    assert response.json()["provider"] == "claude"


async def test_jev_timeout_falls_back(client, settings, store, fake_jev, fake_claude):
    from jevxagent.server import create_app
    import httpx

    await _routing_settings(settings)
    fake_jev.raise_error = httpx.ConnectTimeout("slow")
    app = create_app(settings, store=store, claude_client=httpx.AsyncClient(transport=fake_claude, base_url="https://upstream.test"),
                     jev_client=httpx.AsyncClient(transport=fake_jev, base_url="https://upstream.test"))
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as c:
        response = await c.post(
            "/v1/decision",
            json={"question": "Is this valid?", "context": "x"},
            headers={"x-api-key": CLIENT_KEY},
        )
    assert response.json()["fallback"] is True
    assert response.json()["provider"] == "claude"
    assert "jev_provider_error" in store.fetch_decisions()[0]["error"]


async def test_jev_disabled_uses_claude(client, settings):
    settings.jev_enabled = False
    settings.routing_enabled = True
    response = await client.post(
        "/v1/decision",
        json={"question": "Is this a GitHub URL?", "context": "https://github.com/a/b"},
        headers={"x-api-key": CLIENT_KEY},
    )
    body = response.json()
    assert body["provider"] == "claude"
    assert body["fallback"] is False
    assert body["routing_status"] == "routed_claude"


async def test_complex_question_never_routed_to_jev(client, settings):
    await _routing_settings(settings)
    response = await client.post(
        "/v1/decision",
        json={
            "question": "Design a system architecture for a distributed crawler and explain the tradeoffs.",
            "context": "Large project with many constraints",
        },
        headers={"x-api-key": CLIENT_KEY},
    )
    body = response.json()
    assert body["provider"] == "claude"
    assert body["routing_status"] == "routed_claude"


async def test_unroutable_type_goes_to_claude(client, settings):
    await _routing_settings(settings)
    settings.jev_routable_types = ["binary_decision"]
    response = await client.post(
        "/v1/decision",
        json={"question": "Which category?", "options": ["a", "b", "c"]},
        headers={"x-api-key": CLIENT_KEY},
    )
    assert response.json()["provider"] == "claude"


async def test_decision_missing_question_400(client, settings):
    response = await client.post("/v1/decision", json={"context": "x"})
    assert response.status_code == 400


async def test_decision_records_request_telemetry(client, settings, store):
    await _routing_settings(settings)
    await client.post(
        "/v1/decision",
        json={"question": "Is this a GitHub URL?", "context": "https://github.com/a/b"},
        headers={"x-api-key": CLIENT_KEY},
    )
    rows = store.fetch_requests()
    decision_requests = [r for r in rows if r["operation"] == "decision"]
    assert len(decision_requests) == 1
    assert decision_requests[0]["route"] == "jev"


async def test_jev_context_is_trimmed(client, settings, fake_jev):
    import json as jsonlib

    await _routing_settings(settings)
    settings.jev_max_context_chars = 200
    long_context = "word " * 500
    await client.post(
        "/v1/decision",
        json={"question": "Is this valid?", "context": long_context},
        headers={"x-api-key": CLIENT_KEY},
    )
    sent = jsonlib.loads(fake_jev.seen[0].content.decode())
    user_content = sent["messages"][1]["content"]
    assert len(user_content) < 1500
    assert "[context truncated]" in user_content
