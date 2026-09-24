"""Context injection - Line J implementation"""
from .models import Message, ChatRequest
from .jev_client import JevDecision


def inject_jev_context(request: ChatRequest, decision: JevDecision) -> ChatRequest:
    """Inject Jev execution context into agent request (Line J)

    This is THE core architectural primitive - Jev's decisions/facts
    are injected as system context so agent sees them before generation
    """

    # Build structured context
    context_lines = [
        "SYSTEM EXECUTION CONTEXT (completed by backend):",
        "",
        f"Jev Status: {decision.status}",
    ]

    if decision.decisions:
        context_lines.append(f"Decisions: {decision.decisions}")

    if decision.facts:
        context_lines.append(f"Facts: {decision.facts}")

    if decision.backend_actions:
        context_lines.append(f"Backend Actions: {len(decision.backend_actions)} completed")
        for action in decision.backend_actions:
            context_lines.append(f"  - {action}")

    if decision.agent_instructions:
        context_lines.append("")
        context_lines.append("INSTRUCTIONS:")
        context_lines.append(decision.agent_instructions)

    context_text = "\n".join(context_lines)

    # Inject as system message at start
    jev_message = Message(role="system", content=context_text)

    # Create new request with injected context
    new_messages = [jev_message] + request.messages

    return ChatRequest(
        model=request.model,
        messages=new_messages,
        stream=request.stream,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
    )
