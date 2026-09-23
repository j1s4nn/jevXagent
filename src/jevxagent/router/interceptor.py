"""Observable decision-event interception for the /v1/messages workflow.

Claude Code drives the workflow through repeated ``POST /v1/messages`` calls.
Each assistant response that selects a tool is an *observable decision event*
at the API boundary. This module detects those events from real traffic and
turns them into :class:`DecisionEvent` objects for the existing router
(``RoutingPolicy`` → ``DecisionExecutor`` → JEV).

Honest scope — we can only observe what the Messages API exposes:

- **tool selection** IS observable: the response ``content`` contains a
  ``tool_use`` block, and the request ``tools`` array lists the candidates.
- Internal reasoning, token-level decisions, logits, and hidden agent state
  are NOT observable and are deliberately never intercepted.

This module only *detects* and *models* events. It makes no network calls and
holds no state, so independent conversations cannot leak into one another.
"""

from __future__ import annotations

import hashlib

from ..telemetry.events import DecisionType
from .decision import DecisionEvent

TOOL_SELECTION_QUESTION = "Which tool should be selected?"


def extract_candidate_tools(payload: dict) -> list[str]:
    """Return the tool names declared in a Messages request (the candidates)."""
    tools = payload.get("tools")
    if not isinstance(tools, list):
        return []
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, dict) and tool.get("name"):
            names.append(str(tool["name"]))
    return names


def extract_tool_use_names(content) -> list[str]:
    """Return the tool names selected in an assistant response ``content``.

    Accepts a list of content blocks (non-stream) or an already-extracted list
    of tool names (stream, where full blocks are not re-assembled).
    """
    if not isinstance(content, list):
        return []
    names: list[str] = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name"):
            names.append(str(block["name"]))
        elif isinstance(block, str):
            # stream path may pass tool names directly
            names.append(block)
    return names


def conversation_fingerprint(payload: dict) -> str:
    """Best-effort stable conversation id derived from the request.

    Claude Code does not send a conversation id header, so we fingerprint the
    first user text message (the stable seed of a task) as a heuristic. This is
    not a guarantee of uniqueness, but it lets telemetry group decisions that
    belong to the same workflow while keeping independent sessions separate.
    """
    messages = payload.get("messages") or []
    seed = ""
    for message in messages:
        if not isinstance(message, dict) or message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            seed = content
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "text":
                    seed = str(block.get("text", ""))
                    break
        if seed:
            break
    if not seed:
        seed = str(payload.get("system") or "")
    return hashlib.sha1(seed.encode("utf-8", errors="replace")).hexdigest()[:16]


def build_intercept_context(payload: dict, max_chars: int = 4000) -> str:
    """A compact, bounded summary of the most recent messages for JEV.

    Never sends the full conversation (project rule #10). Only the last few
    messages' text/type are summarized and truncated.
    """
    messages = payload.get("messages") or []
    recent = messages[-4:] if len(messages) > 4 else messages
    parts: list[str] = []
    for message in recent:
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "unknown")
        content = message.get("content")
        if isinstance(content, str):
            parts.append(f"{role}: {content}")
        elif isinstance(content, list):
            for block in content:
                if not isinstance(block, dict):
                    continue
                kind = block.get("type", "unknown")
                if kind == "text":
                    parts.append(f"{role}: {block.get('text', '')}")
                elif kind == "tool_use":
                    parts.append(f"{role}: tool_use({block.get('name', '?')})")
                elif kind == "tool_result":
                    parts.append(f"{role}: tool_result")
    text = "\n".join(parts)
    if len(text) > max_chars:
        text = text[:max_chars] + "\n…[context truncated]"
    return text


def detect_tool_selection(
    payload: dict,
    tool_use_names: list[str],
    request_id: str = "",
    context: str = "",
) -> DecisionEvent | None:
    """Build a tool-selection DecisionEvent from observable response data.

    Returns None when no tool was selected or no candidates are declared, i.e.
    there is no genuine observable decision to route.
    """
    if not tool_use_names:
        return None
    candidates = extract_candidate_tools(payload)
    if not candidates:
        return None

    event = DecisionEvent(
        request_id=request_id,
        conversation_id=conversation_fingerprint(payload),
        context=context,
        current_operation=TOOL_SELECTION_QUESTION,
        candidate_action=tool_use_names[0],
        decision_type=DecisionType.TOOL_SELECTION,
        options=candidates,
        answer_format="choice",
        source="intercept",
    )
    # Selecting a tool from a known, fixed list is a low-complexity decision.
    event.complexity = 0.0
    return event
