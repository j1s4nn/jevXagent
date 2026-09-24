"""Test context injection (Line J)"""
from jevxagent.context_injection import inject_jev_context
from jevxagent.models import Message, ChatRequest
from jevxagent.jev_client import JevDecision


def test_inject_jev_context():
    """Test Line J injection"""
    request = ChatRequest(
        model="test-model",
        messages=[
            Message(role="user", content="Original prompt"),
        ],
        stream=True,
    )

    decision = JevDecision(
        status="success",
        decisions={"category": "DevOps"},
        needs_generation=True,
        facts={"ticket_id": "402"},
        agent_instructions="Generate script only",
    )

    modified = inject_jev_context(request, decision)

    # Should have system message prepended
    assert len(modified.messages) == 2
    assert modified.messages[0].role == "system"
    assert "SYSTEM EXECUTION CONTEXT" in modified.messages[0].content
    assert "DevOps" in modified.messages[0].content
    assert "402" in modified.messages[0].content
    assert "Generate script only" in modified.messages[0].content

    # Original message preserved
    assert modified.messages[1].role == "user"
    assert modified.messages[1].content == "Original prompt"


def test_inject_minimal_context():
    """Test injection with minimal decision"""
    request = ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="test")],
    )

    decision = JevDecision(
        status="success",
        decisions={},
        needs_generation=True,
    )

    modified = inject_jev_context(request, decision)

    assert len(modified.messages) == 2
    assert modified.messages[0].role == "system"
    assert "Jev Status: success" in modified.messages[0].content
