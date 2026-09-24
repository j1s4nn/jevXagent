"""Jev API client"""
import httpx
from typing import Any, Optional
from pydantic import BaseModel


class JevDecision(BaseModel):
    """Jev decision output"""
    status: str  # success, timeout, error, disabled
    decisions: dict[str, Any]
    needs_generation: bool
    backend_actions: list[dict[str, Any]] = []
    facts: dict[str, Any] = {}
    agent_instructions: str = ""
    timing_ms: float = 0


class JevClient:
    """Client for Jev API"""

    def __init__(self, api_key: str, base_url: str, model: str, timeout: float = 0.8):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.client = httpx.AsyncClient(timeout=timeout)

    async def evaluate(self, prompt: str) -> JevDecision:
        """Evaluate prompt with Jev

        Returns structured decision including whether generation needed
        """
        try:
            response = await self.client.post(
                f"{self.base_url}/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            response.raise_for_status()
            data = response.json()

            # Parse Jev response
            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Basic parsing - in production would use structured output
            needs_gen = "needs_generation=false" not in content.lower()

            return JevDecision(
                status="success",
                decisions={"raw_response": content},
                needs_generation=needs_gen,
                timing_ms=data.get("usage", {}).get("total_time_ms", 0),
            )

        except httpx.TimeoutException:
            return JevDecision(
                status="timeout",
                decisions={},
                needs_generation=True,
            )
        except Exception as e:
            return JevDecision(
                status="error",
                decisions={"error": str(e)},
                needs_generation=True,
            )

    async def close(self):
        """Close client"""
        await self.client.aclose()
