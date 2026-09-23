"""Claude provider: request building, responses, SSE parsing."""

import json

import httpx
import pytest

from jevxagent.config import Settings
from jevxagent.providers.base import ProviderError
from jevxagent.providers.claude import (
    ClaudeProvider,
    parse_usage_from_body,
    parse_usage_from_sse,
)


def make_settings() -> Settings:
    return Settings(claude_api_key="k", claude_base_url="https://upstream.test")


@pytest.fixture
def seen():
    return []


def _client(seen, response_factory):
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response_factory(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://upstream.test")


async def test_post_sends_headers_and_body():
    seen = []

    def responder(request):
        return httpx.Response(200, json={"type": "message", "usage": {"input_tokens": 3}})

    provider = ClaudeProvider(make_settings(), client=_client(seen, responder))
    result = await provider.post({"model": "m", "max_tokens": 5, "messages": []})
    assert result.status_code == 200
    assert seen[0].headers["x-api-key"] == "k"
    assert seen[0].headers["anthropic-version"] == "2023-06-01"
    assert json.loads(seen[0].content)["model"] == "m"
    assert result.latency_ms >= 0


async def test_post_timeout_raises_provider_error():
    def responder(request):
        raise httpx.ConnectTimeout("timeout")

    provider = ClaudeProvider(make_settings(), client=_client([], responder))
    with pytest.raises(ProviderError):
        await provider.post({"model": "m", "max_tokens": 5, "messages": []})


async def test_missing_key_raises():
    provider = ClaudeProvider(Settings(claude_api_key=""), client=None)
    with pytest.raises(ProviderError):
        provider.build_headers(None)


async def test_post_rewrites_model_via_map():
    seen = []

    def responder(request):
        return httpx.Response(200, json={"type": "message", "usage": {}})

    settings = Settings(
        claude_api_key="k",
        claude_base_url="https://upstream.test",
        claude_model_map={"claude-opus-5-5": "claude-sonnet-5"},
    )
    provider = ClaudeProvider(settings, client=_client(seen, responder))
    await provider.post({"model": "claude-opus-5-5", "max_tokens": 5, "messages": []})
    assert json.loads(seen[0].content)["model"] == "claude-sonnet-5"


async def test_stream_rewrites_model_via_map():
    seen = []

    def responder(request):
        return httpx.Response(200, content=b"", headers={"content-type": "text/event-stream"})

    settings = Settings(
        claude_api_key="k",
        claude_base_url="https://upstream.test",
        claude_model_map={"claude-opus-5-5": "claude-sonnet-5"},
    )
    provider = ClaudeProvider(settings, client=_client(seen, responder))
    result = await provider.stream({"model": "claude-opus-5-5", "max_tokens": 5, "stream": True, "messages": []})
    async for _ in result.lines:
        pass
    assert json.loads(seen[0].content)["model"] == "claude-sonnet-5"


async def test_post_no_model_map_is_transparent():
    seen = []

    def responder(request):
        return httpx.Response(200, json={"type": "message", "usage": {}})

    provider = ClaudeProvider(make_settings(), client=_client(seen, responder))
    await provider.post({"model": "claude-opus-5-5", "max_tokens": 5, "messages": []})
    assert json.loads(seen[0].content)["model"] == "claude-opus-5-5"


async def test_stream_lines():
    seen = []
    body = "event: ping\ndata: {\"type\":\"ping\"}\n\n"

    def responder(request):
        return httpx.Response(200, content=body.encode(), headers={"content-type": "text/event-stream"})

    provider = ClaudeProvider(make_settings(), client=_client(seen, responder))
    result = await provider.stream({"model": "m", "max_tokens": 5, "stream": True, "messages": []})
    lines = [line async for line in result.lines]
    assert lines == ["event: ping", 'data: {"type":"ping"}', ""]


def test_parse_usage_from_body():
    body = json.dumps({"type": "message", "usage": {"input_tokens": 11, "output_tokens": 4}}).encode()
    usage = parse_usage_from_body(body)
    assert usage == {"input_tokens": 11, "output_tokens": 4}


def test_parse_usage_from_body_invalid():
    assert parse_usage_from_body(b"not json") == {}
    assert parse_usage_from_body(b"{}") == {}


def test_parse_usage_from_sse():
    usage = parse_usage_from_sse('{"type":"message_start","usage":{"input_tokens":9,"cache_read_input_tokens":3}}')
    assert usage == {"input_tokens": 9, "cache_read_input_tokens": 3}


def test_parse_usage_from_sse_message_delta():
    usage = parse_usage_from_sse('{"type":"message_delta","usage":{"output_tokens":6}}')
    assert usage == {"output_tokens": 6}


def test_parse_usage_from_sse_invalid():
    assert parse_usage_from_sse("not json") == {}
