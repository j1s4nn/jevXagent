"""Test fixtures"""
import pytest
from pathlib import Path
from jevxagent.config import Config, JevConfig, AgentConfig, ProxyConfig


@pytest.fixture
def test_config():
    """Test configuration"""
    return Config(
        jev=JevConfig(
            api_key="test-jev-key",
            base_url="https://api.test.jev",
            model="jev-test",
            timeout=0.8,
        ),
        agent=AgentConfig(
            api_key="test-agent-key",
            base_url="https://api.test.agent",
            model="test-model",
        ),
        proxy=ProxyConfig(
            host="127.0.0.1",
            port=9099,
        ),
        jev_enabled=True,
        stats_path=Path("/tmp/test_stats.jsonl"),
        agent_type="test-agent",
    )


@pytest.fixture
def mock_jev_response():
    """Mock Jev API response"""
    return {
        "id": "test-id",
        "choices": [
            {
                "message": {
                    "role": "assistant",
                    "content": "Classification: DevOps\nneeds_generation=false",
                }
            }
        ],
        "usage": {
            "total_time_ms": 100,
        },
    }
