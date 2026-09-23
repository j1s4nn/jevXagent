"""Transparent proxy behavior: preservation, auth, errors, telemetry."""

import json

import httpx
import pytest

from conftest import CLIENT_KEY, CLAUDE_API_KEY, FakeClaudeTransport


async def test_non_stream_passthrough_preserves_payload(client, fake_claude):
    payload = {
        "model": "claude-sonnet-5",
        "max_tokens": 100,
        "system": "you are helpful",
        "tools": [{"name": "read", "description": "read file", "input_schema": {"type": "object"}}],
        "messages": [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "read", "input": {"path": "a.txt"}}]},
            {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "data"}]},
        ],
    }
    response = await client.post(
        "/v1/messages", json=payload, headers={"x-api-key": CLIENT_KEY}
    )
    assert response.status_code == 200
    echo = response.json()["echo"]
    assert echo["model"] == "claude-sonnet-5"
    assert echo["system"] == "you are helpful"
    assert echo["tools"][0]["name"] == "read"
    assert echo["messages"][2]["content"][0]["type"] == "tool_result"
    assert response.json()["usage"]["input_tokens"] == 10


async def test_anthropic_version_header_sent(client, fake_claude):
    response = await client.post(
        "/v1/messages",
        json={"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
        headers={"x-api-key": CLIENT_KEY, "anthropic-version": "2023-06-01"},
    )
    assert response.status_code == 200
    assert fake_claude.seen[0].headers["anthropic-version"] == "2023-06-01"


async def test_auth_override_config_key_wins(client, fake_claude):
    response = await client.post(
        "/v1/messages",
        json={"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
        headers={"x-api-key": CLIENT_KEY},
    )
    assert response.status_code == 200
    assert fake_claude.seen[0].headers["x-api-key"] == CLAUDE_API_KEY


async def test_auth_forward_client_key_when_no_config_key(client, settings, store, fake_claude, fake_jev):
    from jevxagent.server import create_app

    settings.claude_api_key = ""
    app = create_app(settings, store=store, claude_client=httpx.AsyncClient(transport=fake_claude, base_url="https://upstream.test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.post(
            "/v1/messages",
            json={"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
            headers={"x-api-key": CLIENT_KEY},
        )
    assert response.status_code == 200
    assert fake_claude.seen[0].headers["x-api-key"] == CLIENT_KEY


async def test_missing_api_key_401_when_no_keys(client, settings, store, fake_claude, fake_jev):
    from jevxagent.server import create_app

    settings.claude_api_key = ""
    app = create_app(settings, store=store, claude_client=httpx.AsyncClient(transport=fake_claude, base_url="https://upstream.test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.post(
            "/v1/messages",
            json={"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
        )
    assert response.status_code == 401
    assert response.json()["type"] == "error"
    assert response.json()["error"]["type"] == "authentication_error"


async def test_invalid_json_body(client):
    response = await client.post(
        "/v1/messages", content=b"not json", headers={"content-type": "application/json"}
    )
    assert response.status_code == 400
    assert response.json()["type"] == "error"


async def test_missing_messages_field(client):
    response = await client.post("/v1/messages", json={"model": "m"}, headers={"x-api-key": CLIENT_KEY})
    assert response.status_code == 400
    assert response.json()["error"]["type"] == "invalid_request_error"


async def test_upstream_error_relayed(client, settings, store, fake_jev):
    from jevxagent.server import create_app

    error_upstream = FakeClaudeTransport(
        status_override=429,
        error_body={"type": "error", "error": {"type": "rate_limit_error", "message": "slow down"}},
    )
    app = create_app(
        settings, store=store, claude_client=httpx.AsyncClient(transport=error_upstream, base_url="https://upstream.test")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.post(
            "/v1/messages",
            json={"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
            headers={"x-api-key": CLIENT_KEY},
        )
    assert response.status_code == 429
    assert response.json()["error"]["type"] == "rate_limit_error"
    rows = store.fetch_requests()
    assert rows[-1]["status"] == 429
    assert "slow down" in rows[-1]["error"]


async def test_telemetry_records_usage(client, store):
    await client.post(
        "/v1/messages",
        json={"model": "claude-sonnet-5", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
        headers={"x-api-key": CLIENT_KEY},
    )
    rows = store.fetch_requests()
    assert len(rows) == 1
    row = rows[0]
    assert row["route"] == "claude"
    assert row["operation"] == "messages"
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 5
    assert row["cache_read_input_tokens"] == 2
    assert row["cache_creation_input_tokens"] == 1
    assert row["status"] == 200
    assert row["model"] == "claude-sonnet-5"
    assert "api" not in row["summary"]


async def test_healthz(client):
    response = await client.get("/healthz")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["jev_enabled"] is False


async def test_models_passthrough(client, fake_claude):
    response = await client.get("/v1/models", headers={"x-api-key": CLIENT_KEY})
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_stream_passthrough_preserves_sse(client, fake_claude, store):
    from conftest import SSE_BODY

    response = await client.post(
        "/v1/messages",
        json={
            "model": "claude-sonnet-5",
            "max_tokens": 5,
            "stream": True,
            "messages": [{"role": "user", "content": "hi"}],
        },
        headers={"x-api-key": CLIENT_KEY},
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    text = response.text
    assert "event: message_start" in text
    assert "event: content_block_delta" in text
    assert "event: message_delta" in text
    assert "event: message_stop" in text
    for line in SSE_BODY.splitlines():
        if line and not line.startswith("event:"):
            assert line in text
    rows = store.fetch_requests()
    row = rows[-1]
    assert row["stream"] == 1
    assert row["input_tokens"] == 10
    assert row["output_tokens"] == 5


async def test_stream_upstream_error_returns_json(client, settings, store, fake_jev):
    from jevxagent.server import create_app

    error_upstream = FakeClaudeTransport(status_override=401)
    app = create_app(
        settings, store=store, claude_client=httpx.AsyncClient(transport=error_upstream, base_url="https://upstream.test")
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.post(
            "/v1/messages",
            json={
                "model": "m",
                "max_tokens": 5,
                "stream": True,
                "messages": [{"role": "user", "content": "hi"}],
            },
            headers={"x-api-key": CLIENT_KEY},
        )
    assert response.status_code == 401
    assert response.json()["type"] == "error"


async def test_upstream_connection_error_502(client, settings, store, fake_jev):
    from jevxagent.server import create_app

    class BoomTransport(httpx.MockTransport):
        def __init__(self):
            super().__init__(lambda request: (_ for _ in ()).throw(httpx.ConnectTimeout("no route")))

    app = create_app(settings, store=store, claude_client=httpx.AsyncClient(transport=BoomTransport(), base_url="https://upstream.test"))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as c:
        response = await c.post(
            "/v1/messages",
            json={"model": "m", "max_tokens": 5, "messages": [{"role": "user", "content": "hi"}]},
            headers={"x-api-key": CLIENT_KEY},
        )
    assert response.status_code == 502
    assert response.json()["type"] == "error"
