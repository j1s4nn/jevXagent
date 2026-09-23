"""JEV provider — the structured decision coprocessor.

JEV is served by OpenRouter's Decisions API, NOT a text chat-completions API.
The model does not generate free text; it answers *typed* questions about a
``state`` (a string, object, or array) and returns calibrated probabilities.

Protocol:

    POST {JEV_BASE_URL}          (e.g. https://openrouter.ai/api/alpha/decisions)
    Authorization: Bearer <JEV_API_KEY>

    {
      "model": "typesafe/jev-1.13",
      "state": "<string | object | array>",
      "questions": {
        "decision": {
          "type": "choice" | "noul" | "score",
          "instructions": "...",
          "criteria": {...}   // "choice"/"noul": key -> description
                              // "score": ordered rubric list
        }
      }
    }

The response carries structured answers under ``answers``, keyed by question
name, each tagged with a ``type``:

    - "noul":   {"type": "noul", "noul": <0.0-1.0>}
    - "choice": {"type": "choice", "choice": <key>, "probabilities": {...},
                 "confidence": <float>}
    - "score":  {"type": "score", "score": <float>, "legend": {...},
                 "probabilities": {...}, "confidence": <float>}

JEV remains a *structured decision model* here — never converted into a text
generation model.
"""

from __future__ import annotations

import json
import time
from typing import Optional

import httpx

from ..config import Settings
from .base import JevAnswer, JevDecideResult, ProviderError

_ALLOWED_TYPES = {"noul", "choice", "score"}


class JevProvider:
    """Calls the JEV Decisions API with typed questions and returns validated,
    structured answers. Callers own the workflow and act on the answers."""

    def __init__(
        self,
        settings: Settings,
        client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._settings = settings
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(settings.jev_timeout_s, connect=min(settings.jev_timeout_s, 3.0)),
        )

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    def is_configured(self) -> bool:
        return bool(self._settings.jev_api_key and self._settings.jev_base_url)

    def build_request(self, state: str, questions: dict) -> dict:
        """Build a Decisions API request body."""
        return {
            "model": self._settings.jev_model or "typesafe/jev-1.13",
            "state": state,
            "questions": questions,
        }

    async def decide(self, state: str, questions: dict) -> JevDecideResult:
        if not self.is_configured():
            raise ProviderError("JEV is not configured (JEV_API_KEY / JEV_BASE_URL)")

        body = self.build_request(state, questions)
        headers = {
            "content-type": "application/json",
            "authorization": f"Bearer {self._settings.jev_api_key}",
        }

        last_error: Exception | None = None
        for _ in range(self._settings.jev_max_retries + 1):
            start = time.perf_counter()
            try:
                response = await self._client.post(
                    self._settings.jev_base_url, json=body, headers=headers
                )
            except (httpx.TimeoutException, httpx.HTTPError) as exc:
                last_error = exc
                continue
            latency_ms = (time.perf_counter() - start) * 1000.0

            if response.status_code >= 400:
                raise ProviderError(
                    f"JEV upstream error {response.status_code}: {_error_detail(response)}",
                    status=response.status_code,
                )

            try:
                data = response.json()
            except (json.JSONDecodeError, ValueError) as exc:
                raise ProviderError("JEV response is not valid JSON") from exc
            if not isinstance(data, dict):
                raise ProviderError("JEV response is not a JSON object")
            return self._parse(data, latency_ms)

        raise ProviderError(f"JEV request failed after retries: {last_error}")

    def _parse(self, data: dict, latency_ms: float) -> JevDecideResult:
        answers_raw = data.get("answers")
        if not isinstance(answers_raw, dict) or not answers_raw:
            raise ProviderError("JEV response missing 'answers'")

        answers: dict[str, JevAnswer] = {}
        for name, raw in answers_raw.items():
            if not isinstance(raw, dict):
                raise ProviderError(f"JEV answer '{name}' is not an object")
            answers[str(name)] = self._parse_answer(raw, str(name))

        usage = data.get("usage")
        if not isinstance(usage, dict):
            usage = {}

        return JevDecideResult(
            answers=answers,
            model=str(data.get("model") or ""),
            provider=str(data.get("provider") or ""),
            usage=usage,
            id=str(data.get("id") or ""),
            raw=json.dumps(data, ensure_ascii=False)[:2000],
            latency_ms=latency_ms,
        )

    @staticmethod
    def _parse_answer(raw: dict, name: str) -> JevAnswer:
        type_ = str(raw.get("type") or "").strip().lower()
        if type_ not in _ALLOWED_TYPES:
            raise ProviderError(f"JEV answer '{name}' has invalid type '{type_}'")

        probabilities: dict[str, float] = {}
        probs = raw.get("probabilities")
        if isinstance(probs, dict):
            for key, value in probs.items():
                try:
                    probabilities[str(key)] = float(value)
                except (TypeError, ValueError):
                    continue

        choice = raw.get("choice")
        legend = raw.get("legend")
        if not isinstance(legend, dict):
            legend = {}

        noul = _to_float(raw.get("noul"))
        score = _to_float(raw.get("score"))
        confidence = _to_float(raw.get("confidence"))

        if type_ == "noul" and noul is None:
            raise ProviderError(f"JEV noul answer '{name}' missing 'noul'")
        if type_ == "choice" and choice is None:
            raise ProviderError(f"JEV choice answer '{name}' missing 'choice'")
        if type_ == "score" and score is None:
            raise ProviderError(f"JEV score answer '{name}' missing 'score'")

        return JevAnswer(
            type=type_,
            noul=noul,
            choice=str(choice) if choice is not None else None,
            score=score,
            probabilities=probabilities,
            confidence=confidence,
            legend=legend,
        )


def _to_float(value) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _error_detail(response: httpx.Response) -> str:
    """Extract a concise error message from an upstream error body."""
    try:
        data = response.json()
    except (json.JSONDecodeError, ValueError):
        return response.text[:300]
    if isinstance(data, dict):
        error = data.get("error")
        if isinstance(error, dict):
            return str(error.get("message") or error)[:300]
        if error:
            return str(error)[:300]
        if data.get("message"):
            return str(data["message"])[:300]
    return response.text[:300]
