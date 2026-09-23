"""Claude (Anthropic-compatible Messages API) provider.

The upstream API used by this project is Anthropic-compatible:
    POST {base_url}/v1/messages
    headers: x-api-key, anthropic-version: 2023-06-01, content-type
    body: {"model", "max_tokens", "messages", "system"?, "tools"?, "stream"?}

Streaming uses SSE: `event: <name>` / `data: <json>` frames, including
`message_start` (input usage) and `message_delta` (output usage).

This provider is a thin, transparent client: it does not rewrite payloads.
"""

from __future__ import annotations

import json
import time
from typing import AsyncIterator, Optional

import httpx

from ..config import Settings
from .base import NonStreamResponse, ProviderError, StreamResponse

DEFAULT_ANTHROPIC_VERSION = "2023-06-01"


class ClaudeProvider:
    def __init__(
        self,
        settings: Settings,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.claude_base_url,
            timeout=httpx.Timeout(settings.claude_timeout_s, connect=10.0),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def build_headers(self, client_key: str | None) -> dict[str, str]:
        """Upstream headers. CLAUDE_API_KEY from config always wins when set,
        otherwise the client's key is forwarded (transparent behavior).
        """
        api_key = self._settings.claude_api_key or (client_key or "")
        if not api_key:
            raise ProviderError("No Claude API key available (CLAUDE_API_KEY or client x-api-key)")
        return {
            "content-type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": DEFAULT_ANTHROPIC_VERSION,
        }

    async def models(self, client_key: str | None = None) -> NonStreamResponse:
        headers = self.build_headers(client_key)
        start = time.perf_counter()
        try:
            response = await self._client.get("/v1/models", headers=headers)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Claude upstream timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Claude upstream connection error: {exc}") from exc
        return NonStreamResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
            latency_ms=(time.perf_counter() - start) * 1000.0,
        )

    async def post(
        self, payload: dict, client_key: str | None = None, extra_headers: dict | None = None
    ) -> NonStreamResponse:
        headers = self.build_headers(client_key)
        if extra_headers:
            headers.update(extra_headers)
        start = time.perf_counter()
        try:
            response = await self._client.post(
                "/v1/messages", content=json.dumps(payload), headers=headers
            )
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Claude upstream timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Claude upstream connection error: {exc}") from exc
        latency_ms = (time.perf_counter() - start) * 1000.0
        return NonStreamResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            body=response.content,
            latency_ms=latency_ms,
        )

    async def stream(
        self, payload: dict, client_key: str | None = None, extra_headers: dict | None = None
    ) -> StreamResponse:
        headers = self.build_headers(client_key)
        if extra_headers:
            headers.update(extra_headers)
        start = time.perf_counter()
        try:
            request = self._client.build_request(
                "POST", "/v1/messages", content=json.dumps(payload), headers=headers
            )
            response = await self._client.send(request, stream=True)
        except httpx.TimeoutException as exc:
            raise ProviderError(f"Claude upstream timeout: {exc}") from exc
        except httpx.HTTPError as exc:
            raise ProviderError(f"Claude upstream connection error: {exc}") from exc

        first_byte_holder: dict[str, float | None] = {"value": None}

        async def lines() -> AsyncIterator[str]:
            async for line in response.aiter_lines():
                if first_byte_holder["value"] is None:
                    first_byte_holder["value"] = time.perf_counter()
                yield line
            await response.aclose()

        first_byte = first_byte_holder["value"]
        first_byte_ms = (first_byte - start) * 1000.0 if first_byte is not None else None
        return StreamResponse(
            status_code=response.status_code,
            headers=dict(response.headers),
            lines=lines(),
            first_byte_ms=first_byte_ms,
        )


def parse_usage_from_body(body: bytes) -> dict:
    """Extract usage numbers from a non-streaming Messages response body."""
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return {}
    usage = data.get("usage")
    if not isinstance(usage, dict):
        return {}
    out: dict[str, int] = {}
    for key in (
        "input_tokens",
        "output_tokens",
        "cache_read_input_tokens",
        "cache_creation_input_tokens",
        "thinking_tokens",
    ):
        value = usage.get(key)
        if isinstance(value, int):
            out[key] = value
    return out


def parse_usage_from_sse(data_payload: str) -> dict:
    """Extract usage numbers from an SSE data frame (message_start / message_delta)."""
    try:
        data = json.loads(data_payload)
    except json.JSONDecodeError:
        return {}
    usage = data.get("usage") or (data.get("message") or {}).get("usage") or {}
    out: dict[str, int] = {}
    if isinstance(usage, dict):
        for key in (
            "input_tokens",
            "output_tokens",
            "cache_read_input_tokens",
            "cache_creation_input_tokens",
            "thinking_tokens",
        ):
            value = usage.get(key)
            if isinstance(value, int):
                out[key] = value
    return out
