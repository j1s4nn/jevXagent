"""Proxy server - handles agent requests"""
import asyncio
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx

from .config import Config
from .jev_client import JevClient
from .context_injection import inject_jev_context
from .models import ChatRequest, ProxyMetrics


class ProxyServer:
    """Transparent proxy intercepting agent requests"""

    def __init__(self, config: Config):
        self.config = config
        self.jev_client = JevClient(
            api_key=config.jev.api_key,
            base_url=config.jev.base_url,
            model=config.jev.model,
            timeout=config.jev.timeout,
        )
        self.agent_client = httpx.AsyncClient(timeout=30.0)
        self.metrics_queue: list[ProxyMetrics] = []

    async def process_request(self, request: ChatRequest) -> tuple[ChatRequest, ProxyMetrics]:
        """Process request through Jev, return modified request and metrics"""
        trace_id = str(uuid.uuid4())
        start_time = time.time()

        metrics = ProxyMetrics(
            trace_id=trace_id,
            jev_enabled=self.config.jev_enabled,
            jev_status="disabled",
        )

        # If Jev disabled, pass through
        if not self.config.jev_enabled:
            metrics.total_latency_ms = (time.time() - start_time) * 1000
            return request, metrics

        # Extract prompt from last user message
        user_messages = [m for m in request.messages if m.role == "user"]
        if not user_messages:
            metrics.jev_status = "skipped"
            metrics.total_latency_ms = (time.time() - start_time) * 1000
            return request, metrics

        prompt = user_messages[-1].content

        # Call Jev
        jev_start = time.time()
        decision = await self.jev_client.evaluate(prompt)
        jev_latency = (time.time() - jev_start) * 1000

        metrics.jev_status = decision.status
        metrics.jev_latency_ms = jev_latency

        # If Jev failed/timeout, pass through
        if decision.status != "success":
            metrics.total_latency_ms = (time.time() - start_time) * 1000
            return request, metrics

        # Check bypass
        if not decision.needs_generation:
            metrics.bypass = True
            metrics.agent_called = False
            metrics.total_latency_ms = (time.time() - start_time) * 1000
            # For bypass, would return deterministic response directly
            # For now, still call agent but mark bypass
            return request, metrics

        # Line J: inject Jev context
        modified_request = inject_jev_context(request, decision)
        metrics.total_latency_ms = (time.time() - start_time) * 1000

        return modified_request, metrics

    async def stream_agent_response(
        self, request: ChatRequest, metrics: ProxyMetrics
    ) -> AsyncGenerator[bytes, None]:
        """Stream response from agent API"""
        agent_start = time.time()
        first_token_time = None

        # Build agent request
        url = f"{self.config.agent.base_url}/v1/messages"
        headers = {
            "x-api-key": self.config.agent.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }

        # Convert to Anthropic format
        messages = [{"role": m.role, "content": m.content} for m in request.messages]

        payload = {
            "model": self.config.agent.model,
            "messages": messages,
            "stream": request.stream,
            "max_tokens": request.max_tokens or 4096,
        }

        async with self.agent_client.stream("POST", url, json=payload, headers=headers) as resp:
            async for chunk in resp.aiter_bytes():
                if first_token_time is None:
                    first_token_time = time.time()
                    metrics.agent_ttft_ms = (first_token_time - agent_start) * 1000

                yield chunk

        agent_latency = (time.time() - agent_start) * 1000
        metrics.agent_latency_ms = agent_latency
        metrics.total_latency_ms += agent_latency

        # Queue metrics for display
        self.metrics_queue.append(metrics)

    def print_metrics(self, metrics: ProxyMetrics) -> None:
        """Print metrics to console"""
        print("\n" + "─" * 50)
        print(f"Trace: {metrics.trace_id[:8]}")
        print(f"Jev: {metrics.jev_status} | {metrics.jev_latency_ms:.0f}ms")
        if metrics.agent_called:
            print(f"Agent: {metrics.agent_latency_ms:.0f}ms")
            if metrics.agent_ttft_ms:
                print(f"TTFT: {metrics.agent_ttft_ms:.0f}ms")
        else:
            print("Agent: BYPASSED")
        print(f"Total: {metrics.total_latency_ms:.0f}ms")
        print("─" * 50)

    async def close(self):
        """Cleanup"""
        await self.jev_client.close()
        await self.agent_client.aclose()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifespan manager"""
    yield
    if hasattr(app.state, "proxy"):
        await app.state.proxy.close()


def create_app(config: Config) -> FastAPI:
    """Create FastAPI app"""
    app = FastAPI(lifespan=lifespan)
    proxy = ProxyServer(config)
    app.state.proxy = proxy

    @app.post("/v1/messages")
    async def proxy_messages(request: Request):
        """Proxy Anthropic messages endpoint"""
        body = await request.json()
        chat_request = ChatRequest(**body)

        # Process through Jev
        modified_request, metrics = await proxy.process_request(chat_request)

        # Handle bypass case
        if metrics.bypass:
            proxy.print_metrics(metrics)
            return {
                "id": metrics.trace_id,
                "type": "message",
                "role": "assistant",
                "content": [{"type": "text", "text": "Request completed by Jev (no generation needed)"}],
            }

        # Stream response
        if modified_request.stream:
            return StreamingResponse(
                proxy.stream_agent_response(modified_request, metrics),
                media_type="text/event-stream",
            )

        # Non-streaming not implemented yet
        return {"error": "Non-streaming not implemented"}

    return app
