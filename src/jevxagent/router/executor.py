"""Decision executor — runs a DecisionEvent through JEV or Claude with
full fallback semantics, and records telemetry.

Fallback rules (project rule #14): JEV uncertain / timeout / malformed
output / complex task => Claude. Fail safely, never guess.
"""

from __future__ import annotations

import json
import re
from typing import Optional

from ..config import Settings
from ..context.extractor import build_decision_prompt
from ..providers.base import JevDecision, ProviderError
from ..providers.claude import ClaudeProvider
from ..providers.jev import JevProvider
from ..telemetry.events import DecisionRecord, RoutingStatus
from ..telemetry.storage import TelemetryStore
from .decision import DecisionEvent
from .policy import RoutingPolicy

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class DecisionExecutor:
    def __init__(
        self,
        settings: Settings,
        store: TelemetryStore,
        claude: ClaudeProvider,
        jev: JevProvider,
        policy: Optional[RoutingPolicy] = None,
    ) -> None:
        self._settings = settings
        self._store = store
        self._claude = claude
        self._jev = jev
        self._policy = policy or RoutingPolicy(settings)

    async def execute(self, event: DecisionEvent) -> dict:
        route = self._policy.route(event)

        if route.use_jev:
            try:
                return await self._execute_jev(event)
            except ProviderError as exc:
                event.routing_status = RoutingStatus.FALLBACK_CLAUDE
                fallback_reason = f"jev_provider_error: {exc}"
                attempt_ms = getattr(exc, "jev_attempt_ms", None)
                if attempt_ms is not None:
                    event.payload["jev_attempt_ms"] = attempt_ms
            except Exception as exc:  # noqa: BLE001 — never let JEV break the caller
                event.routing_status = RoutingStatus.FALLBACK_CLAUDE
                fallback_reason = f"jev_unexpected_error: {exc}"
        else:
            event.routing_status = RoutingStatus.ROUTED_CLAUDE
            fallback_reason = ""

        return await self._execute_claude(event, fallback_reason=fallback_reason)

    async def _execute_jev(self, event: DecisionEvent) -> dict:
        prompt = build_decision_prompt(
            event.current_operation,
            event.options or None,
            event.context,
            event.answer_format,
            self._settings,
        )
        result: JevDecision = await self._jev.decide(prompt)
        event.confidence = result.confidence

        if not self._policy.confidence_ok(result.confidence):
            error = ProviderError(
                f"JEV confidence {result.confidence} below threshold "
                f"{self._settings.jev_confidence_threshold}"
            )
            error.jev_attempt_ms = result.latency_ms
            raise error

        event.routing_status = RoutingStatus.ROUTED_JEV
        record = DecisionRecord(
            request_id=event.request_id,
            decision_type=event.decision_type.value,
            route="jev",
            routing_status=event.routing_status.value,
            fallback=False,
            confidence=result.confidence,
            status="success",
            jev_ms=result.latency_ms,
            jev_input_tokens=result.input_tokens,
            jev_output_tokens=result.output_tokens,
            meta=self._decision_meta(event),
        )
        self._store.record_decision(record)

        return {
            "decision": result.decision,
            "choice": result.choice,
            "confidence": result.confidence,
            "provider": "jev",
            "fallback": False,
            "routing_status": event.routing_status.value,
            "decision_type": event.decision_type.value,
            "complexity": round(event.complexity, 3),
            "latency_ms": round(result.latency_ms, 1),
            "request_id": event.request_id,
        }

    async def _execute_claude(self, event: DecisionEvent, fallback_reason: str = "") -> dict:
        prompt = build_decision_prompt(
            event.current_operation,
            event.options or None,
            event.context,
            event.answer_format,
            self._settings,
        )
        payload = {
            "model": "claude-sonnet-5",
            "max_tokens": 128,
            "temperature": 0.0,
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "Answer ONLY with a JSON object: "
                        '{"decision": "<answer>", "confidence": <0.0-1.0>}.\n' + prompt
                    ),
                }
            ],
        }
        response = await self._claude.post(payload)
        decision_text, confidence, parse_error = self._parse_claude_answer(response.body)

        is_fallback = bool(fallback_reason)
        jev_attempt_ms = event.payload.get("jev_attempt_ms")
        record = DecisionRecord(
            request_id=event.request_id,
            decision_type=event.decision_type.value,
            route="claude",
            routing_status=event.routing_status.value,
            fallback=is_fallback,
            confidence=confidence,
            status="success" if response.status_code < 400 else "error",
            claude_ms=response.latency_ms,
            jev_ms=float(jev_attempt_ms) if jev_attempt_ms is not None else 0.0,
            claude_input_tokens=_usage_int(response.body, "input_tokens"),
            claude_output_tokens=_usage_int(response.body, "output_tokens"),
            error=(fallback_reason or parse_error or _upstream_error(response.body)),
            meta=self._decision_meta(event, fallback_reason=fallback_reason),
        )
        self._store.record_decision(record)

        return {
            "decision": decision_text,
            "choice": None,
            "confidence": confidence,
            "provider": "claude",
            "fallback": is_fallback,
            "routing_status": event.routing_status.value,
            "decision_type": event.decision_type.value,
            "complexity": round(event.complexity, 3),
            "latency_ms": round(response.latency_ms, 1),
            "request_id": event.request_id,
        }

    def _decision_meta(self, event: DecisionEvent, fallback_reason: str = "") -> dict:
        meta: dict = {"complexity": round(event.complexity, 3)}
        if fallback_reason:
            meta["fallback_reason"] = fallback_reason
        if self._settings.store_decision_context and event.context:
            meta["context_chars"] = len(event.context)
            meta["question_chars"] = len(event.current_operation)
        return meta

    @staticmethod
    def _parse_claude_answer(body: bytes) -> tuple[str, Optional[float], str]:
        try:
            data = json.loads(body)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return "", None, "claude returned non-JSON body"
        try:
            content = data["content"]
            text = "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        except (KeyError, TypeError):
            return "", None, "claude response missing content"
        try:
            parsed = json.loads(text)
            if not isinstance(parsed, dict):
                raise ValueError("not an object")
        except (json.JSONDecodeError, ValueError):
            match = _JSON_BLOCK_RE.search(text)
            if match:
                try:
                    parsed = json.loads(match.group(0))
                except json.JSONDecodeError:
                    return text.strip(), None, "claude answer not JSON (raw text returned)"
            else:
                return text.strip(), None, "claude answer not JSON (raw text returned)"
        decision = parsed.get("decision") or parsed.get("answer") or ""
        confidence = parsed.get("confidence")
        try:
            confidence = float(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None
        return str(decision), confidence, ""


def _usage_int(body: bytes, key: str) -> Optional[int]:
    try:
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None
    value = (data.get("usage") or {}).get(key)
    return int(value) if isinstance(value, int) else None


def _upstream_error(body: bytes) -> str:
    try:
        data = json.loads(body)
        return str((data.get("error") or {}).get("message", ""))[:200]
    except (json.JSONDecodeError, UnicodeDecodeError):
        return ""
