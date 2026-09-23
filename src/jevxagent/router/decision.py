"""Decision event model.

The fundamental abstraction is the *decision event* — not any particular
reasoning format (e.g. `<think>`). Reasoning formats vary by model/API;
decision events are the stable, internal representation the router works with.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from ..telemetry.events import DecisionType, RoutingStatus, new_id, now_ts


@dataclass
class DecisionEvent:
    event_id: str = field(default_factory=new_id)
    conversation_id: str = ""
    request_id: str = ""
    context: str = ""  # already-trimmed relevant context
    current_operation: str = ""
    candidate_action: str = ""
    decision_type: DecisionType = DecisionType.OTHER
    complexity: float = 0.0
    confidence: Optional[float] = None
    routing_status: RoutingStatus = RoutingStatus.NOT_ROUTED
    options: list[str] = field(default_factory=list)
    answer_format: str = "decision"  # "decision" | "choice" | "label" | "yesno" | "score" | "noul"
    source: str = "manual"  # "manual" (POST /v1/decision) | "intercept" (messages workflow)
    payload: dict[str, Any] = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "event_id": self.event_id,
            "conversation_id": self.conversation_id,
            "request_id": self.request_id,
            "decision_type": self.decision_type.value,
            "complexity": self.complexity,
            "confidence": self.confidence,
            "routing_status": self.routing_status.value,
            "current_operation": self.current_operation,
            "candidate_action": self.candidate_action,
            "source": self.source,
        }
