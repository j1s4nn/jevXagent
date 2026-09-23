"""Telemetry event model.

Every proxied request produces a RequestRecord; every decision routed through
the decision endpoint produces a DecisionRecord. Records store only metadata
plus provider-reported token/latency numbers — never secrets, and never full
conversation content unless explicitly enabled in config.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Optional


class DecisionType(str, Enum):
    CLASSIFICATION = "classification"
    SELECTION = "selection"
    ROUTING = "routing"
    VERIFICATION = "verification"
    RELEVANCE = "relevance"
    TOOL_SELECTION = "tool_selection"
    ENTITY_IDENTIFICATION = "entity_identification"
    SIMPLE_COMPARISON = "simple_comparison"
    SIMPLE_EXTRACTION = "simple_extraction"
    SIMPLE_TRANSFORMATION = "simple_transformation"
    NEXT_ACTION = "next_action"
    BINARY_DECISION = "binary_decision"
    MULTIPLE_CHOICE = "multiple_choice"
    URL_CLASSIFICATION = "url_classification"
    OTHER = "other"


class RoutingStatus(str, Enum):
    ROUTED_JEV = "routed_jev"
    ROUTED_CLAUDE = "routed_claude"
    FALLBACK_CLAUDE = "fallback_claude"
    NOT_ROUTED = "not_routed"


def new_id() -> str:
    return uuid.uuid4().hex


def now_ts() -> float:
    return time.time()


@dataclass
class RequestRecord:
    """Metadata record for one proxied HTTP request."""

    event_id: str = field(default_factory=new_id)
    ts: float = field(default_factory=now_ts)
    request_id: str = ""
    model: str = ""
    operation: str = "messages"  # "messages" | "decision"
    stream: bool = False
    route: str = "claude"  # "claude" | "jev"
    status: int = 0
    total_ms: float = 0.0
    claude_ms: float = 0.0
    jev_ms: float = 0.0
    input_tokens: Optional[int] = None
    output_tokens: Optional[int] = None
    cache_read_input_tokens: Optional[int] = None
    cache_creation_input_tokens: Optional[int] = None
    thinking_tokens: Optional[int] = None
    error: str = ""
    summary: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "event_id": self.event_id,
            "ts": self.ts,
            "request_id": self.request_id,
            "model": self.model,
            "operation": self.operation,
            "stream": int(self.stream),
            "route": self.route,
            "status": self.status,
            "total_ms": self.total_ms,
            "claude_ms": self.claude_ms,
            "jev_ms": self.jev_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cache_read_input_tokens": self.cache_read_input_tokens,
            "cache_creation_input_tokens": self.cache_creation_input_tokens,
            "thinking_tokens": self.thinking_tokens,
            "error": self.error,
            "summary": self.summary,
            "meta": self.meta,
        }


@dataclass
class DecisionRecord:
    """Record for one decision event (decision endpoint)."""

    decision_id: str = field(default_factory=new_id)
    ts: float = field(default_factory=now_ts)
    request_id: str = ""
    decision_type: str = DecisionType.OTHER.value
    route: str = "claude"
    routing_status: str = RoutingStatus.ROUTED_CLAUDE.value
    fallback: bool = False
    confidence: Optional[float] = None
    status: str = "success"
    jev_ms: float = 0.0
    claude_ms: float = 0.0
    jev_input_tokens: Optional[int] = None
    jev_output_tokens: Optional[int] = None
    claude_input_tokens: Optional[int] = None
    claude_output_tokens: Optional[int] = None
    error: str = ""
    meta: dict[str, Any] = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "decision_id": self.decision_id,
            "ts": self.ts,
            "request_id": self.request_id,
            "decision_type": self.decision_type,
            "route": self.route,
            "routing_status": self.routing_status,
            "fallback": int(self.fallback),
            "confidence": self.confidence,
            "status": self.status,
            "jev_ms": self.jev_ms,
            "claude_ms": self.claude_ms,
            "jev_input_tokens": self.jev_input_tokens,
            "jev_output_tokens": self.jev_output_tokens,
            "claude_input_tokens": self.claude_input_tokens,
            "claude_output_tokens": self.claude_output_tokens,
            "error": self.error,
            "meta": self.meta,
        }
