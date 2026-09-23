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
class JevAnswer:
    """One typed answer returned by the JEV Decisions API.

    The Decisions API answers *typed* questions about a state. Each answer is
    tagged with a `type` and carries the fields relevant to that type:

    - ``noul``   -> ``noul`` (probability 0..1 that the answer is "yes")
    - ``choice`` -> ``choice`` (criterion key) + ``probabilities`` distribution
    - ``score``  -> ``score`` (position on an ordered rubric) + ``probabilities``
    """

    type: str  # "choice" | "noul" | "score"
    noul: float | None = None
    choice: str | None = None
    score: float | None = None
    probabilities: dict[str, float] = field(default_factory=dict)
    confidence: float | None = None
    legend: dict[str, str] = field(default_factory=dict)


@dataclass
class JevDecideResult:
    """Structured result from the JEV Decisions API.

    Preserves the answers plus useful metadata returned by JEV/OpenRouter:
    probabilities, per-answer confidence, model, provider, usage.
    """

    answers: dict[str, JevAnswer] = field(default_factory=dict)
    model: str = ""
    provider: str = ""
    usage: dict = field(default_factory=dict)
    id: str = ""
    raw: str = ""
    latency_ms: float = 0.0

    def answer(self, name: str) -> JevAnswer | None:
        return self.answers.get(name)

    @property
    def input_tokens(self) -> int | None:
        value = self.usage.get("input_tokens")
        return int(value) if isinstance(value, (int, float)) else None

    @property
    def output_tokens(self) -> int | None:
        value = self.usage.get("output_tokens")
        return int(value) if isinstance(value, (int, float)) else None
