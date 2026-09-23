"""MCP jevx_decide tool: event building, tool registration, end-to-end."""

import pytest

pytest.importorskip("mcp")

from jevxagent import mcp_server
from jevxagent.providers.claude import ClaudeProvider
from jevxagent.providers.jev import JevProvider
from jevxagent.router.executor import DecisionExecutor


async def test_tool_registered():
    names = [tool.name for tool in await mcp_server.mcp.list_tools()]
    assert "jevx_decide" in names


def test_norm_format():
    assert mcp_server._norm_format("SCORE") == "score"
    assert mcp_server._norm_format("noul") == "noul"
    assert mcp_server._norm_format("bogus") == "decision"
    assert mcp_server._norm_format("") == "decision"


def test_build_event_infers_selection_for_two_options():
    event = mcp_server.build_event("Which file?", options=["a.py", "b.py"])
    assert event.source == "mcp"
    assert event.options == ["a.py", "b.py"]
    assert event.answer_format == "decision"
    assert event.decision_type.value == "selection"


def test_build_event_explicit_type_and_format():
    event = mcp_server.build_event(
        "Which tool?", options=["a", "b"], answer_format="choice", decision_type="tool_selection"
    )
    assert event.answer_format == "choice"
    assert event.decision_type.value == "tool_selection"


def test_build_event_yesno_format():
    event = mcp_server.build_event("Is it valid?", answer_format="yesno")
    assert event.answer_format == "yesno"


async def test_decide_uses_existing_executor(settings, store, claude_client, jev_client, fake_jev):
    settings.jev_enabled = True
    settings.routing_enabled = True
    fake_jev.answers = {
        "decision": {
            "type": "choice",
            "choice": "b.py",
            "probabilities": {"a.py": 0.2, "b.py": 0.8},
            "confidence": 0.9,
        }
    }
    claude = ClaudeProvider(settings, client=claude_client)
    jev = JevProvider(settings, client=jev_client)
    executor = DecisionExecutor(settings, store, claude, jev)

    result = await mcp_server.decide(
        "Which file should we edit?", options=["a.py", "b.py"], executor=executor, settings=settings
    )

    assert result["source"] == "mcp"
    assert result["provider"] == "jev"
    assert result["decision"] == "b.py"
    assert result["confidence"] == 0.9
