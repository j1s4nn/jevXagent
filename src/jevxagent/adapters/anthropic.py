"""Anthropic-compatible adapter.

This module owns the Anthropic Messages API protocol knowledge:
- POST {base}/v1/messages
- headers: x-api-key, anthropic-version, anthropic-beta?
- JSON body: model / max_tokens / messages / system? / tools? / stream?
- SSE streaming frames and usage extraction
- Anthropic-style error envelopes

The proxy is transparent: request bodies are forwarded verbatim, response
bodies/streams are relayed verbatim. Other adapters (e.g. OpenAI-compatible)
can be added alongside this one later.
"""

from __future__ import annotations

import json
from typing import Optional

import httpx

from ..providers.claude import parse_usage_from_sse
from ..telemetry.events import now_ts

ANTHROPIC_VERSION = "2023-06-01"

_FORWARD_REQUEST_HEADERS = {
    "anthropic-version",
    "anthropic-beta",
    "anthropic-dangerous-direct-browser-access",
}

_HOP_BY_HOP = {
    "connection",
    "keep-alive",
    "transfer-encoding",
    "content-length",
    "content-encoding",
    "trailer",
    "upgrade",
    "proxy-authenticate",
    "proxy-authorization",
}


def validate_payload(payload: dict) -> Optional[str]:
    """Return an error message if the payload is not a valid Messages request."""
    if not isinstance(payload, dict):
        return "Request body must be a JSON object"
    if "messages" not in payload or not isinstance(payload["messages"], list):
        return "Field 'messages' is required and must be an array"
    if "max_tokens" not in payload and "thinking" not in payload:
        return "Field 'max_tokens' is required"
    return None


def extract_meta(payload: dict) -> dict:
    messages = payload.get("messages") or []
    summary_parts = [f"messages={len(messages)}"]
    tools = payload.get("tools")
    if isinstance(tools, list):
        summary_parts.append(f"tools={len(tools)}")
    system = payload.get("system")
    if system:
        summary_parts.append("has_system=1")
    return {"summary": " ".join(summary_parts), "model": str(payload.get("model") or "")}


def build_upstream_headers(client_headers: dict, api_key: str, anthropic_version: str | None = None) -> dict:
    headers = {"content-type": "application/json"}
    if api_key:
        headers["x-api-key"] = api_key
    headers["anthropic-version"] = anthropic_version or ANTHROPIC_VERSION
    for name in _FORWARD_REQUEST_HEADERS:
        value = client_headers.get(name)
        if value:
            headers[name] = value
    return headers


def filter_response_headers(headers: dict) -> dict:
    return {
        name: value
        for name, value in headers.items()
        if name.lower() not in _HOP_BY_HOP
    }


def anthropic_error(status: int, message: str, error_type: str = "api_error") -> dict:
    return {
        "type": "error",
        "error": {"type": error_type, "message": message},
    }


class SseUsageCollector:
    """Collects usage numbers from an SSE stream while it is relayed."""

    def __init__(self) -> None:
        self.usage: dict[str, int] = {}
        self.frames_seen: list[str] = []

    def on_line(self, line: str) -> None:
        if line.startswith("data:"):
            self.frames_seen.append(line.split(":", 1)[1].strip()[:40])
            usage = parse_usage_from_sse(line.split(":", 1)[1].strip())
            for key, value in usage.items():
                self.usage[key] = value


class SseToolCollector:
    """Collects tool-selection signals from an SSE stream, without buffering
    the full conversation.

    After the stream ends, this exposes the tools Claude selected (from
    ``content_block_start`` frames) and the ``stop_reason`` (from
    ``message_delta``). Used only for observable decision-event detection.
    """

    def __init__(self) -> None:
        self.tool_names: list[str] = []
        self.stop_reason: str | None = None

    def on_line(self, line: str) -> None:
        if not line.startswith("data:"):
            return
        try:
            frame = json.loads(line.split(":", 1)[1].strip())
        except json.JSONDecodeError:
            return
        if not isinstance(frame, dict):
            return
        if frame.get("type") == "content_block_start":
            block = frame.get("content_block")
            if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
                self.tool_names.append(str(block["name"]))
        elif frame.get("type") == "message_delta":
            delta = frame.get("delta")
            if isinstance(delta, dict) and delta.get("stop_reason"):
                self.stop_reason = str(delta["stop_reason"])


def parse_content_types(payload: dict) -> str:
    """Sanitized description of content block types (no content stored)."""
    counts: dict[str, int] = {}
    for message in payload.get("messages") or []:
        content = message.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    kind = block.get("type", "unknown")
                    counts[kind] = counts.get(kind, 0) + 1
        elif isinstance(content, str):
            counts["text"] = counts.get("text", 0) + 1
    return ", ".join(f"{k}={v}" for k, v in sorted(counts.items()))


def is_stream_request(payload: dict) -> bool:
    return bool(payload.get("stream", False))
