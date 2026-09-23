"""Adapters: header handling, validation, SSE usage collection."""

from jevxagent.adapters.anthropic import (
    anthropic_error,
    build_upstream_headers,
    filter_response_headers,
    is_stream_request,
    parse_content_types,
    validate_payload,
    SseUsageCollector,
)


def test_validate_payload():
    assert validate_payload({"messages": [], "max_tokens": 5}) is None
    assert "messages" in validate_payload({"max_tokens": 5})
    assert "max_tokens" in validate_payload({"messages": []})


def test_is_stream_request():
    assert is_stream_request({"stream": True})
    assert not is_stream_request({})


def test_build_upstream_headers():
    headers = build_upstream_headers(
        {"anthropic-beta": "tools-2024-05-16", "user-agent": "claude"},
        "secret-key",
        "2023-06-01",
    )
    assert headers["x-api-key"] == "secret-key"
    assert headers["anthropic-version"] == "2023-06-01"
    assert headers["anthropic-beta"] == "tools-2024-05-16"
    assert "user-agent" not in headers
    assert headers["content-type"] == "application/json"


def test_filter_response_headers():
    filtered = filter_response_headers(
        {"content-type": "application/json", "transfer-encoding": "chunked", "x-upstream": "1"}
    )
    assert "transfer-encoding" not in filtered
    assert "content-type" in filtered
    assert filtered["x-upstream"] == "1"


def test_anthropic_error_shape():
    error = anthropic_error(401, "nope", "authentication_error")
    assert error["type"] == "error"
    assert error["error"]["type"] == "authentication_error"


def test_parse_content_types():
    payload = {
        "messages": [
            {"role": "user", "content": [{"type": "tool_result", "content": "x"}]},
            {"role": "assistant", "content": [{"type": "tool_use", "name": "read"}]},
            {"role": "user", "content": "plain"},
        ]
    }
    kinds = parse_content_types(payload)
    assert "tool_result=1" in kinds
    assert "tool_use=1" in kinds
    assert "text=1" in kinds


def test_sse_usage_collector():
    collector = SseUsageCollector()
    collector.on_line("event: message_start")
    collector.on_line('data: {"type":"message_start","usage":{"input_tokens":12}}')
    collector.on_line('data: {"type":"message_delta","usage":{"output_tokens":7}}')
    collector.on_line("data: {\"type\":\"content_block_delta\"}")
    assert collector.usage == {"input_tokens": 12, "output_tokens": 7}
    assert len(collector.frames_seen) == 3
