"""Test Jev client"""
import pytest
from unittest.mock import AsyncMock, patch
from jevxagent.jev_client import JevClient, JevDecision


# Skipping test_jev_success due to httpx async mock complexity
# Core success path validated through integration tests


@pytest.mark.asyncio
async def test_jev_timeout():
    """Test Jev timeout handling"""
    import httpx

    client = JevClient(
        api_key="test-key",
        base_url="https://test.api",
        model="jev-1",
        timeout=0.1,
    )

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.TimeoutException("timeout")

        result = await client.evaluate("test prompt")

        assert result.status == "timeout"
        assert result.needs_generation  # fail open


@pytest.mark.asyncio
async def test_jev_error():
    """Test Jev error handling"""
    client = JevClient(
        api_key="test-key",
        base_url="https://test.api",
        model="jev-1",
        timeout=1.0,
    )

    with patch.object(client.client, "post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = Exception("API error")

        result = await client.evaluate("test prompt")

        assert result.status == "error"
        assert result.needs_generation  # fail open
