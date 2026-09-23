"""JEV provider — the fast decision coprocessor.

> ================================================================
> MARK — JEV API SUBMISSION POINT
> ================================================================
> The real JEV API was not available when this project started
> (no login system yet; placeholder key only).
>
> When you receive a real JEV API key:
>   1. set JEV_API_KEY and JEV_BASE_URL in `.env`
>   2. verify the exact request/response protocol in JEV's docs
>   3. adjust `build_request()` / `_parse()` below if the protocol differs
>   4. set JEV_ENABLED=true in `.env`
>
> Assumed protocol (TO VERIFY): OpenAI-compatible
>     POST {JEV_BASE_URL}/v1/chat/completions
>     Authorization: Bearer <JEV_API_KEY>
>     {"model", "messages": [...], "temperature": 0, ...}
> ================================================================
"""

from __future__ import annotations

import json
import re
import time
from typing import Optional

import httpx

from ..config import Settings
from .base import JevDecision, ProviderError

_JSON_BLOCK_RE = re.compile(r"\{.*\}", re.DOTALL)


class JevProvider:
    """Calls JEV with a small, structured decision prompt and returns a
    validated structured result. Never sends large context: callers must
    pre-trim via the context extractor."""

    def __init__(
        self,
        settings: Settings,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=settings.jev_base_url,
            timeout=httpx.Timeout(settings.jev_timeout_s, connect=min(settings.jev_timeout_s, 3.0)),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def is_configured(self) -> bool:
        return bool(self._settings.jev_api_key and self._settings.jev_base_url)

    def build_request(self, prompt: str, temperature: float = 0.0) -> dict:
        return {
            # model id — set JEV_MODEL in .env once the real API is available
            "model": self._settings.jev_model or "jev",
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "You are a decision coprocessor. Answer ONLY with a JSON object: "
                        '{"decision": "<answer>", "confidence": <0.0-1.0>}. '
                        "Do not add explanations or extra text."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            "temperature": temperature,
        }

    async def decide(
        self, prompt: str, temperature: float = 0.0
    ) -> JevDecision:
        if not self.is_configured():
            raise ProviderError("JEV is not configured (JEV_API_KEY / JEV_BASE_URL)")

        body = self.build_request(prompt, temperature)
        headers = {
            "content-type": "application/json",
            # JEV API KEY USED HERE — the actual auth scheme must be verified
            "authorization": f"Bearer {self._settings.jev_api_key}",
        }
        last_error: Exception | None = None
        for attempt in range(self._settings.jev_max_retries + 1):
            start = time.perf_counter()
            try:
                response = await self._client.post("/v1/chat/completions", json=body, headers=headers)
                latency_ms = (time.perf_counter() - start) * 1000.0
                if response.status_code >= 400:
                    raise ProviderError(
                        f"JEV upstream error {response.status_code}: {response.text[:300]}",
                        status=response.status_code,
                    )
                return self._parse(response.json(), latency_ms)
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
        raise ProviderError(f"JEV request failed after retries: {last_error}")

    def _parse(self, data: dict, latency_ms: float) -> JevDecision:
        content = ""
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ProviderError("JEV response has unexpected shape") from exc

        if isinstance(content, list):  # some APIs return content blocks
            content = "".join(
                part.get("text", "") for part in content if isinstance(part, dict)
            )

        parsed = self._parse_json(content)
        if parsed is None:
            raise ProviderError("JEV returned malformed output (no JSON found)")
        decision = parsed.get("decision") or parsed.get("answer") or parsed.get("choice")
        if decision is None:
            raise ProviderError("JEV JSON missing required field 'decision'")
        if isinstance(decision, (dict, list)):
            decision = json.dumps(decision, ensure_ascii=False)

        confidence = parsed.get("confidence")
        if confidence is not None:
            try:
                confidence = float(confidence)
            except (TypeError, ValueError):
                confidence = None

        choice = parsed.get("choice") or parsed.get("option") or parsed.get("label")
        return JevDecision(
            decision=str(decision),
            choice=str(choice) if choice is not None else None,
            confidence=confidence,
            raw=content[:500],
            latency_ms=latency_ms,
            usage=data.get("usage") or {},
        )

    @staticmethod
    def _parse_json(text: str) -> dict | None:
        if not text:
            return None
        try:
            value = json.loads(text)
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            match = _JSON_BLOCK_RE.search(text)
            if match:
                try:
                    value = json.loads(match.group(0))
                    return value if isinstance(value, dict) else None
                except json.JSONDecodeError:
                    return None
        return None
