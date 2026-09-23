"""MCP server — exposes ``jevx_decide`` to Claude Code (and other MCP clients).

This covers decision events that are NOT observable at the raw
``/v1/messages`` boundary (e.g. file selection, relevance, verification), where
the agent explicitly asks jevXagent for a structured decision mid-conversation.

Run it as a stdio MCP server:

    jevXagent mcp

and register it with Claude Code:

    claude mcp add jevxagent -- python -m jevxagent mcp

The tool reuses the existing ``DecisionExecutor`` / ``JevProvider`` /
``RoutingPolicy`` infrastructure — it does not re-implement JEV.
"""

from __future__ import annotations

from typing import Any

from mcp.server.mcpserver import MCPServer

from .config import Settings
from .providers.claude import ClaudeProvider
from .providers.jev import JevProvider
from .router.classifier import estimate_complexity, infer_decision_type
from .router.decision import DecisionEvent
from .router.executor import DecisionExecutor
from .telemetry.events import DecisionType
from .telemetry.storage import TelemetryStore

mcp = MCPServer(
    "jevxagent",
    version="0.1.0",
    instructions=(
        "Ask JEV (the structured decision coprocessor) a typed decision "
        "question. Use this for quick, structured decisions during the "
        "workflow — choice (pick an option), yes/no, or score (ordered rubric)."
    ),
)

_ALLOWED_FORMATS = {"decision", "choice", "label", "yesno", "score", "noul"}


def _norm_format(fmt: str) -> str:
    fmt = (fmt or "decision").strip().lower()
    return fmt if fmt in _ALLOWED_FORMATS else "decision"


def build_event(
    question: str,
    options: list[str] | None = None,
    context: str = "",
    answer_format: str = "decision",
    decision_type: str = "",
    source: str = "mcp",
) -> DecisionEvent:
    """Build a DecisionEvent from the MCP tool arguments (shared with tests)."""
    options = [str(o) for o in (options or [])]
    event = DecisionEvent(
        context=context or "",
        current_operation=(question or "").strip(),
        options=options,
        answer_format=_norm_format(answer_format),
        source=source,
    )
    explicit = (decision_type or "").strip()
    if explicit:
        try:
            event.decision_type = DecisionType(explicit)
        except ValueError:
            event.decision_type = infer_decision_type(question, options, context)
    else:
        event.decision_type = infer_decision_type(question, options, context)
    event.complexity = estimate_complexity(question, options, context)
    return event


async def decide(
    question: str,
    options: list[str] | None = None,
    context: str = "",
    answer_format: str = "decision",
    decision_type: str = "",
    settings: Settings | None = None,
    executor: DecisionExecutor | None = None,
) -> dict[str, Any]:
    """Core decision path shared by the MCP tool (and unit tests).

    Builds a ``DecisionEvent`` and runs it through the existing executor, so
    telemetry and fallback behave exactly like the ``/v1/decision`` endpoint.
    When ``executor`` is injected (tests), its providers/store are owned by the
    caller and left open.
    """
    event = build_event(question, options, context, answer_format, decision_type)
    if executor is not None:
        result = await executor.execute(event)
        result["source"] = "mcp"
        return result

    settings = settings or Settings.from_env()
    settings.ensure_data_dir()
    store = TelemetryStore(settings)
    claude = ClaudeProvider(settings)
    jev = JevProvider(settings)
    executor = DecisionExecutor(settings, store, claude, jev)
    try:
        result = await executor.execute(event)
        result["source"] = "mcp"
        return result
    finally:
        await claude.aclose()
        await jev.aclose()
        store.close()


@mcp.tool()
async def jevx_decide(
    question: str,
    options: list[str] | None = None,
    context: str = "",
    format: str = "decision",
    decision_type: str = "",
) -> dict[str, Any]:
    """Ask JEV (the structured decision coprocessor) a typed decision.

    Args:
        question: The decision question (required).
        options: Candidate options for a choice decision (e.g. file paths).
        context: Optional supporting context.
        format: "decision" (default), "choice", "label", "yesno", "score", "noul".
        decision_type: Optional explicit type; otherwise inferred from the question.
    """
    return await decide(question, options, context, format, decision_type)


def main() -> None:
    mcp.run()  # stdio transport (default)


if __name__ == "__main__":
    main()
