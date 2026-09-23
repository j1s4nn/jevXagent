"""Real JEV smoke test — proves the end-to-end decision path against the
live JEV Decisions API (OpenRouter), no mocks.

    client -> DecisionExecutor -> JevProvider -> OpenRouter -> JEV -> answer

Run:  python scripts/smoke_jev.py

Requires JEV_API_KEY / JEV_BASE_URL in `.env`. Makes a REAL network call.
"""

from __future__ import annotations

import asyncio
import json
import sys

from jevxagent.config import Settings
from jevxagent.providers.claude import ClaudeProvider
from jevxagent.providers.jev import JevProvider
from jevxagent.router.classifier import estimate_complexity
from jevxagent.router.decision import DecisionEvent
from jevxagent.router.executor import DecisionExecutor
from jevxagent.telemetry.events import DecisionType
from jevxagent.telemetry.storage import TelemetryStore


async def main() -> int:
    settings = Settings.from_env()
    if not settings.jev_api_key or not settings.jev_base_url:
        print("JEV not configured (JEV_API_KEY / JEV_BASE_URL missing).", file=sys.stderr)
        return 2

    jev = JevProvider(settings)
    print(f"JEV endpoint : {settings.jev_base_url}")
    print(f"JEV model    : {settings.jev_model or 'typesafe/jev-1.13'}")

    question = "Which action should be selected?"
    options = ["inspect_file", "run_test", "edit_code"]
    state = "The agent just saw a failing test and must decide its next step."

    # 1) Raw provider call against the real Decisions API (evidence of JEV).
    result = await jev.decide(
        state,
        {
            "decision": {
                "type": "choice",
                "instructions": question,
                "criteria": {option: option for option in options},
            }
        },
    )
    answer = result.answer("decision")
    print("\n--- Raw JEV Decisions API response (parsed) ---")
    print(f"  model      : {result.model}")
    print(f"  provider   : {result.provider}")
    print(f"  id         : {result.id}")
    print(f"  answer type: {answer.type}")
    print(f"  choice     : {answer.choice}")
    print(f"  probs      : {answer.probabilities}")
    print(f"  confidence : {answer.confidence}")
    print(f"  usage      : {result.usage}")
    print(f"  latency_ms : {round(result.latency_ms, 1)}")

    # 2) Full path through the existing decision interfaces.
    settings.ensure_data_dir()
    store = TelemetryStore(settings, path=settings.data_dir / "smoke.db")
    claude = ClaudeProvider(settings)
    executor = DecisionExecutor(settings, store, claude, jev)

    # Lower the confidence gate so the smoke test deterministically exercises
    # the JEV path (we are proving connectivity, not re-testing the policy).
    settings.jev_enabled = True
    settings.routing_enabled = True
    settings.jev_confidence_threshold = 0.0

    event = DecisionEvent(
        request_id="smoke-1",
        context=state,
        current_operation=question,
        options=options,
        answer_format="choice",
        decision_type=DecisionType.TOOL_SELECTION,
        complexity=estimate_complexity(question, options, state),
    )
    outcome = await executor.execute(event)

    print("\n--- DecisionExecutor result ---")
    print(json.dumps(outcome, indent=2, default=str))

    await claude.aclose()
    await jev.aclose()
    store.close()

    if outcome.get("provider") != "jev":
        print("\nREAL JEV API TEST: PARTIAL (executor did not route to JEV)", file=sys.stderr)
        return 1

    print("\nREAL JEV API TEST: PASSED")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        sys.exit(130)
