"""Proxy server - handles agent requests"""
import asyncio
import time
import uuid
import json
import re
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Optional

from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse
import httpx

from .config import Config
from .jev_client import JevClient
from .context_injection import inject_jev_context
from .models import ChatRequest, ProxyMetrics, UsageInfo, Message
from .stats import StatsStorage


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
        self.stats_storage = StatsStorage(config.stats_path)
        self._request_count = 0

    def _should_bypass_jev(self, request: ChatRequest) -> bool:
        """Check if request contains media that should bypass Jev"""
        for message in request.messages:
            content = message.content.lower()
            # Check for common image/doc references
            if any(ext in content for ext in ['.png', '.jpg', '.jpeg', '.pdf', '.doc', '.docx', 'image', 'screenshot']):
                return True
        return False

    async def process_request(self, request: ChatRequest) -> tuple[ChatRequest, ProxyMetrics]:
        """Process request through Jev, return modified request and metrics"""
        trace_id = str(uuid.uuid4())[:8]
        start_time = time.time()
        self._request_count += 1

        metrics = ProxyMetrics(
            trace_id=trace_id,
            jev_enabled=self.config.jev_enabled,
            jev_status="disabled",
        )

        # If Jev disabled, pass through
        if not self.config.jev_enabled:
            metrics.total_latency_ms = (time.time() - start_time) * 1000
            return request, metrics

        # Check for media content that should bypass Jev
        if self._should_bypass_jev(request):
            metrics.jev_status = "bypassed_media"
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

    def _parse_sse_usage(self, chunk_text: str) -> Optional[UsageInfo]:
        """Extract usage from SSE chunk"""
        try:
            # SSE format: data: {json}
            if chunk_text.startswith("data: "):
                json_str = chunk_text[6:].strip()
                if json_str and json_str != "[DONE]":
                    data = json.loads(json_str)
                    if "usage" in data:
                        usage = data["usage"]
                        return UsageInfo(
                            prompt_tokens=usage.get("input_tokens"),
                            completion_tokens=usage.get("output_tokens"),
                            total_tokens=usage.get("input_tokens", 0) + usage.get("output_tokens", 0),
                        )
        except Exception:
            pass
        return None

    async def stream_agent_response(
        self, request: ChatRequest, metrics: ProxyMetrics
    ) -> AsyncGenerator[bytes, None]:
        """Stream response from agent API"""
        agent_start = time.time()
        first_token_time = None
        accumulated_usage: Optional[UsageInfo] = None

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

                # Try to extract usage from chunk
                try:
                    chunk_text = chunk.decode('utf-8')
                    usage = self._parse_sse_usage(chunk_text)
                    if usage:
                        accumulated_usage = usage
                except Exception:
                    pass

                yield chunk

        agent_latency = (time.time() - agent_start) * 1000
        metrics.agent_latency_ms = agent_latency
        metrics.total_latency_ms += agent_latency

        # Update metrics with usage if found
        if accumulated_usage:
            metrics.agent_input_tokens = accumulated_usage.prompt_tokens or 0
            metrics.agent_output_tokens = accumulated_usage.completion_tokens or 0

        # Save to stats
        self.stats_storage.save_metric(metrics)

        # Queue metrics for display
        self.metrics_queue.append(metrics)

    def print_metrics(self, metrics: ProxyMetrics) -> None:
        """Print metrics to console"""
        print("\n" + "─" * 50)
        print(f"Request #{self._request_count} | Trace: {metrics.trace_id}")

        # Jev section
        if metrics.jev_enabled:
            status_display = metrics.jev_status
            if metrics.jev_status == "success":
                status_display = f"✓ {metrics.jev_status}"
            elif metrics.jev_status in ["timeout", "error"]:
                status_display = f"✗ {metrics.jev_status}"

            print(f"Jev: {status_display} | {metrics.jev_latency_ms:.0f}ms")

            if metrics.jev_input_tokens or metrics.jev_output_tokens:
                print(f"  Tokens: in={metrics.jev_input_tokens} out={metrics.jev_output_tokens}")
        else:
            print("Jev: OFF")

        # Agent section
        if metrics.agent_called:
            print(f"Agent: {metrics.agent_latency_ms:.0f}ms")
            if metrics.agent_ttft_ms:
                print(f"  TTFT: {metrics.agent_ttft_ms:.0f}ms")
            if metrics.agent_input_tokens or metrics.agent_output_tokens:
                total = metrics.agent_input_tokens + metrics.agent_output_tokens
                print(f"  Tokens: in={metrics.agent_input_tokens} out={metrics.agent_output_tokens} total={total}")
        else:
            print("Agent: BYPASSED")

        # Overall
        print(f"Total: {metrics.total_latency_ms:.0f}ms")
        print("─" * 50)

    def save_stats_snapshot(self) -> None:
        """Save current statistics snapshot (Ctrl+S handler)"""
        summary = self.stats_storage.get_summary()

        print("\n" + "=" * 50)
        print("STATISTICS SNAPSHOT")
        print("=" * 50)
        print(f"Total Requests: {summary.get('total_requests', 0)}")
        print(f"Jev Enabled: {summary.get('jev_enabled_count', 0)}")
        print(f"Bypassed: {summary.get('bypass_count', 0)}")

        if summary.get('avg_jev_latency_ms'):
            print(f"Avg Jev Latency: {summary['avg_jev_latency_ms']:.0f}ms")
        if summary.get('avg_total_latency_ms'):
            print(f"Avg Total Latency: {summary['avg_total_latency_ms']:.0f}ms")

        if self.config.stats_path:
            print(f"Saved to: {self.config.stats_path}")
        print("=" * 50 + "\n")

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
            async def stream_with_metrics():
                async for chunk in proxy.stream_agent_response(modified_request, metrics):
                    yield chunk
                # Print metrics after stream completes
                proxy.print_metrics(metrics)

            return StreamingResponse(
                stream_with_metrics(),
                media_type="text/event-stream",
            )

        # Non-streaming not implemented yet
        return {"error": "Non-streaming not implemented"}

    @app.post("/v1/chat/completions")
    async def proxy_openai_chat(request: Request):
        """Proxy OpenAI chat completions endpoint"""
        body = await request.json()

        # Convert OpenAI format to internal format
        messages = []
        for msg in body.get("messages", []):
            messages.append(Message(
                role=msg["role"],
                content=msg["content"]
            ))

        chat_request = ChatRequest(
            model=body.get("model", "gpt-4"),
            messages=messages,
            stream=body.get("stream", False),
            temperature=body.get("temperature"),
            max_tokens=body.get("max_tokens"),
        )

        # Process through Jev
        modified_request, metrics = await proxy.process_request(chat_request)

        # Handle bypass case
        if metrics.bypass:
            proxy.print_metrics(metrics)
            return {
                "id": metrics.trace_id,
                "object": "chat.completion",
                "created": int(time.time()),
                "model": body.get("model"),
                "choices": [{
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": "Request completed by Jev (no generation needed)"
                    },
                    "finish_reason": "stop"
                }]
            }

        # For OpenAI, need to adapt the backend call
        # This is a simplified implementation
        return {"error": "OpenAI backend not fully implemented yet"}

    return app
