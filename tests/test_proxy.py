"""Test proxy server"""
import pytest
from unittest.mock import AsyncMock, patch
from jevxagent.proxy import ProxyServer
from jevxagent.models import ChatRequest, Message
from jevxagent.config import Config


@pytest.mark.asyncio
async def test_proxy_jev_disabled(test_config):
    """Test proxy with Jev disabled"""
    test_config.jev_enabled = False
    proxy = ProxyServer(test_config)

    request = ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="test")],
    )

    modified, metrics = await proxy.process_request(request)

    assert metrics.jev_status == "disabled"
    assert not metrics.bypass
    assert modified == request  # unchanged

    await proxy.close()


@pytest.mark.asyncio
async def test_proxy_jev_success(test_config):
    """Test proxy with successful Jev call"""
    proxy = ProxyServer(test_config)

    request = ChatRequest(
        model="test-model",
        messages=[Message(role="user", content="test prompt")],
    )

    with patch.object(proxy.jev_client, "evaluate", new_callable=AsyncMock) as mock_eval:
        from jevxagent.jev_client import JevDecision

        mock_eval.return_value = JevDecision(
            status="success",
            decisions={"category": "test"},
            needs_generation=True,
        )

        modified, metrics = await proxy.process_request(request)

        assert metrics.jev_status == "success"
        assert metrics.jev_enabled
        assert not metrics.bypass
        # Should have injected context
        assert len(modified.messages) > len(request.messages)

    await proxy.close()
