"""Conservative routing policy.

Rules (project rules #12/#14/#26):
- JEV is only used when BOTH JEV_ENABLED and ROUTING_ENABLED are true.
- Only explicitly allowed decision types are routed.
- Anything that looks complex is never routed.
- Any failure / low confidence / timeout falls back to Claude.
Quality first, latency/cost second. Fail safely.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..config import Settings
from ..telemetry.events import DecisionType
from .classifier import is_potentially_routable
from .decision import DecisionEvent


@dataclass
class RouteDecision:
    use_jev: bool
    reason: str


class RoutingPolicy:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings

    def route(self, event: DecisionEvent) -> RouteDecision:
        if not self._settings.jev_enabled:
            return RouteDecision(False, "JEV_ENABLED=false")
        if not self._settings.routing_enabled:
            return RouteDecision(False, "ROUTING_ENABLED=false")
        if event.decision_type.value not in self._settings.jev_routable_types:
            return RouteDecision(False, f"decision type '{event.decision_type.value}' not routable")
        if not is_potentially_routable(event.decision_type):
            return RouteDecision(False, "decision type outside routable set")
        if event.complexity > self._settings.jev_max_complexity:
            return RouteDecision(False, f"complexity {event.complexity:.2f} too high")
        return RouteDecision(True, "routable")

    def confidence_ok(self, confidence: float | None) -> bool:
        if confidence is None:
            return False
        return confidence >= self._settings.jev_confidence_threshold
