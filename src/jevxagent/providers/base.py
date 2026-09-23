"""Provider layer.

Providers wrap a single model API. The proxy (server) talks to providers;
the router chooses between them. A provider never stores telemetry — that is
the telemetry layer's job.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import AsyncIterator


class ProviderError(Exception):
    """A provider call failed (network, timeout, or upstream error)."""

    def __init__(self, message: str, *, status: int | None = None):
        super().__init__(message)
        self.status = status


@dataclass
class NonStreamResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    latency_ms: float


@dataclass
class StreamResponse:
    status_code: int
    headers: dict[str, str]
    lines: AsyncIterator[str]
    latency_ms: float = 0.0
    first_byte_ms: float | None = None


@dataclass
class JevDecision:
    """Structured, validated result from the JEV provider."""

    decision: str
    choice: str | None = None
    confidence: float | None = None
    raw: str = ""
    latency_ms: float = 0.0
    usage: dict = field(default_factory=dict)

    @property
    def input_tokens(self) -> int | None:
        value = self.usage.get("prompt_tokens")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def output_tokens(self) -> int | None:
        value = self.usage.get("completion_tokens")
        return int(value) if isinstance(value, (int, float)) else None
