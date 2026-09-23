"""Shared fixtures: in-memory fake upstreams (no network in tests)."""

from __future__ import annotations

import json

import httpx
import pytest

from jevxagent.config import Settings
from jevxagent.server import create_app
from jevxagent.telemetry.storage import TelemetryStore

CLAUDE_API_KEY = "test-claude-key"
CLIENT_KEY = "test-client-key"

SSE_BODY = (
    "event: message_start\n"
    'data: {"type":"message_start","message":{"id":"msg_1","type":"message","role":"assistant",'
    '"usage":{"input_tokens":10,"cache_read_input_tokens":2}}}\n'
    "\n"
    "event: content_block_delta\n"
    'data: {"type":"content_block_delta","index":0,"delta":{"type":"text_delta","text":"Hi"}}\n'
    "\n"
    "event: message_delta\n"
    'data: {"type":"message_delta","delta":{"stop_reason":"end_turn"},"usage":{"output_tokens":5}}\n'
    "\n"
    "event: message_stop\n"
    'data: {"type":"message_stop"}\n'
)

DECISION_JSON_ANSWER = '{"decision": "YES", "confidence": 0.9}'


def message_response(payload: dict) -> dict:
    return {
        "type": "message",
        "id": "msg_test",
        "role": "assistant",
        "echo": payload,
        "content": [{"type": "text", "text": "hello"}],
        "stop_reason": "end_turn",
        "usage": {
            "input_tokens": 10,
            "output_tokens": 5,
            "cache_read_input_tokens": 2,
            "cache_creation_input_tokens": 1,
        },
    }


class FakeClaudeTransport(httpx.MockTransport):
    """Records requests and emulates an Anthropic-compatible upstream."""

    def __init__(self, status_override: int | None = None, error_body: dict | None = None):
        self.seen: list[httpx.Request] = []
        self.status_override = status_override
        self.error_body = error_body
        super().__init__(self._handler)

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if self.status_override is not None:
            return httpx.Response(
                self.status_override,
                json=self.error_body
                or {"type": "error", "error": {"type": "api_error", "message": "boom"}},
            )
        path = request.url.path
        if path == "/v1/models":
            return httpx.Response(200, json={"data": [], "has_more": False})
        if path != "/v1/messages":
            return httpx.Response(
                404,
                json={"type": "error", "error": {"type": "not_found_error", "message": "no such path"}},
            )
        payload = json.loads(request.content)
        if payload.get("stream"):
            return httpx.Response(
                200,
                content=SSE_BODY.encode(),
                headers={"content-type": "text/event-stream"},
            )
        if payload.get("messages"):
            content = payload["messages"][0].get("content", "")
            if isinstance(content, str) and "Answer ONLY with a JSON object" in content:
                return httpx.Response(
                    200,
                    json={
                        "type": "message",
                        "id": "msg_decision",
                        "role": "assistant",
                        "content": [{"type": "text", "text": DECISION_JSON_ANSWER}],
                        "stop_reason": "end_turn",
                        "usage": {"input_tokens": 40, "output_tokens": 8},
                    },
                )
        return httpx.Response(200, json=message_response(payload))


class FakeJevTransport(httpx.MockTransport):
    def __init__(
        self,
        content: str = '{"decision": "YES", "confidence": 0.98}',
        status: int = 200,
        raise_error: Exception | None = None,
    ):
        self.seen: list[httpx.Request] = []
        self.content = content
        self.status = status
        self.raise_error = raise_error
        super().__init__(self._handler)

    def _handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        if self.raise_error is not None:
            raise self.raise_error
        return httpx.Response(
            self.status,
            json={
                "choices": [{"message": {"content": self.content}}],
                "usage": {"prompt_tokens": 20, "completion_tokens": 5},
            },
        )


@pytest.fixture
def settings(tmp_path) -> Settings:
    return Settings(
        claude_api_key=CLAUDE_API_KEY,
        claude_base_url="https://upstream.test",
        jev_api_key="test-jev-key",
        jev_base_url="https://jev.test",
        jev_model="jev-fast",
        data_dir=tmp_path / "data",
    )


@pytest.fixture
def fake_claude() -> FakeClaudeTransport:
    return FakeClaudeTransport()


@pytest.fixture
def fake_jev() -> FakeJevTransport:
    return FakeJevTransport()


@pytest.fixture
def claude_client(fake_claude) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=fake_claude, base_url="https://upstream.test")


@pytest.fixture
def jev_client(fake_jev) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=fake_jev, base_url="https://jev.test")


@pytest.fixture
def store(settings) -> TelemetryStore:
    return TelemetryStore(settings, path=settings.data_dir / "telemetry.db")


@pytest.fixture
def app(settings, store, claude_client, jev_client):
    return create_app(
        settings, store=store, claude_client=claude_client, jev_client=jev_client
    )


@pytest.fixture
async def client(app) -> httpx.AsyncClient:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as c:
        yield c
