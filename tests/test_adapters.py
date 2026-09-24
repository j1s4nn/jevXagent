"""Test agent adapters"""
from pathlib import Path
from jevxagent.adapters import ClaudeCodeAdapter, CodexAdapter, KiloAdapter


def test_claude_code_adapter_properties():
    """Test Claude Code adapter properties"""
    adapter = ClaudeCodeAdapter()

    assert adapter.name == "Claude Code"
    assert adapter.transport == "anthropic"
    assert adapter.supports_env_override()


def test_codex_adapter_properties():
    """Test Codex adapter properties"""
    adapter = CodexAdapter()

    assert adapter.name == "Codex"
    assert adapter.transport == "openai"
    assert adapter.supports_env_override()


def test_kilo_adapter_properties():
    """Test Kilo adapter properties"""
    adapter = KiloAdapter()

    assert adapter.name == "Kilo Code"
    assert adapter.transport == "anthropic"
    assert adapter.supports_env_override()


def test_adapter_detect_missing():
    """Test detection when agent not installed"""
    # Use unlikely path that won't exist
    adapter = ClaudeCodeAdapter()

    # Mock home to non-existent path
    import unittest.mock as mock
    with mock.patch("pathlib.Path.home", return_value=Path("/nonexistent")):
        result = adapter.detect()
        assert not result
