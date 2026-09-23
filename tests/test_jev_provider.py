"""JEV provider: Decisions API request building, response parsing, errors."""

import json

import httpx
import pytest

from jevxagent.config import Settings
from jevxagent.providers.base import ProviderError
from jevxagent.providers.jev import JevProvider

DECISIONS_URL = "https://openrouter.ai/api/alpha/decisions"

CHOICE_QUESTION = {
    "decision": {
        "type": "choice",
        "instructions": "Which action?",
        "criteria": {"inspect_file": "inspect_file", "run_test": "run_test"},
    }
}


def make_settings(**overrides) -> Settings:
    base = dict(
        jev_api_key="k",
        jev_base_url=DECISIONS_URL,
        jev_model="typesafe/jev-1.13",
    )
    base.update(overrides)
    return Settings(**base)


def _client(seen, responder) -> httpx.AsyncClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return responder(request)

    return httpx.AsyncClient(transport=httpx.MockTransport(handler), base_url="https://openrouter.ai")


def _ok_body(answers: dict) -> dict:
    return {
        "id": "gen-1",
        "model": "typesafe/jev-1.13",
        "provider": "TypeSafe",
        "answers": answers,
        "usage": {"input_tokens": 100, "output_tokens": 10},
    }


async def test_build_request_uses_decisions_schema():
    provider = JevProvider(make_settings(), client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={}))))
    body = provider.build_request("state text", CHOICE_QUESTION)
    assert body["model"] == "typesafe/jev-1.13"
    assert body["state"] == "state text"
    assert body["questions"] == CHOICE_QUESTION
    assert "messages" not in body
    assert "temperature" not in body


def test_build_request_default_model():
    provider = JevProvider(Settings(jev_api_key="k", jev_base_url="u"), client=None)
    body = provider.build_request("s", {})
    assert body["model"] == "typesafe/jev-1.13"


async def test_decide_posts_to_decisions_endpoint_with_auth():
    seen = []

    def responder(request):
        return httpx.Response(200, json=_ok_body({
            "decision": {
                "type": "choice",
                "choice": "run_test",
                "probabilities": {"inspect_file": 0.1, "run_test": 0.9},
                "confidence": 0.9,
            }
        }))

    provider = JevProvider(make_settings(), client=_client(seen, responder))
    result = await provider.decide("state text", CHOICE_QUESTION)

    assert str(seen[0].url) == DECISIONS_URL
    assert seen[0].headers["authorization"] == "Bearer k"
    sent = json.loads(seen[0].content)
    assert sent["model"] == "typesafe/jev-1.13"
    assert sent["state"] == "state text"

    answer = result.answer("decision")
    assert answer.type == "choice"
    assert answer.choice == "run_test"
    assert answer.probabilities == {"inspect_file": 0.1, "run_test": 0.9}
    assert answer.confidence == 0.9
    assert result.model == "typesafe/jev-1.13"
    assert result.provider == "TypeSafe"
    assert result.input_tokens == 100
    assert result.output_tokens == 10


async def test_noul_answer_parsing():
    def responder(request):
        return httpx.Response(200, json=_ok_body({"decision": {"type": "noul", "noul": 0.95}}))

    provider = JevProvider(make_settings(), client=_client([], responder))
    result = await provider.decide("s", {"decision": {"type": "noul", "instructions": "urgent?", "criteria": {"true": "yes", "false": "no"}}})
    answer = result.answer("decision")
    assert answer.type == "noul"
    assert answer.noul == 0.95


async def test_score_answer_parsing():
    def responder(request):
        return httpx.Response(200, json=_ok_body({
            "decision": {
                "type": "score",
                "score": 1.04,
                "legend": {"0": "Calm", "1": "Frustrated", "2": "Very angry"},
                "probabilities": {"0": 0.0, "1": 0.96, "2": 0.04},
                "confidence": 0.94,
            }
        }))

    provider = JevProvider(make_settings(), client=_client([], responder))
    result = await provider.decide("s", {"decision": {"type": "score", "instructions": "frustration?", "criteria": ["Calm", "Frustrated", "Very angry"]}})
    answer = result.answer("decision")
    assert answer.type == "score"
    assert answer.score == 1.04
    assert answer.probabilities["1"] == 0.96
    assert answer.confidence == 0.94
    assert answer.legend == {"0": "Calm", "1": "Frustrated", "2": "Very angry"}


async def test_decide_when_not_configured_raises():
    provider = JevProvider(Settings(jev_api_key="", jev_base_url=""), client=None)
    with pytest.raises(ProviderError) as exc:
        await provider.decide("s", CHOICE_QUESTION)
    assert "not configured" in str(exc.value)


async def test_http_error_raises_provider_error_with_status():
    def responder(request):
        return httpx.Response(401, json={"error": {"message": "invalid api key"}})

    provider = JevProvider(make_settings(), client=_client([], responder))
    with pytest.raises(ProviderError) as exc:
        await provider.decide("s", CHOICE_QUESTION)
    assert exc.value.status == 401
    assert "401" in str(exc.value)


async def test_timeout_retries_then_raises():
    seen = []

    def responder(request):
        raise httpx.ConnectTimeout("slow")

    provider = JevProvider(make_settings(jev_max_retries=2), client=_client(seen, responder))
    with pytest.raises(ProviderError) as exc:
        await provider.decide("s", CHOICE_QUESTION)
    assert len(seen) == 3  # initial attempt + 2 retries
    assert "retries" in str(exc.value)


async def test_non_json_response_raises():
    def responder(request):
        return httpx.Response(200, content=b"not json")

    provider = JevProvider(make_settings(), client=_client([], responder))
    with pytest.raises(ProviderError) as exc:
        await provider.decide("s", CHOICE_QUESTION)
    assert "JSON" in str(exc.value)


async def test_missing_answers_raises():
    def responder(request):
        return httpx.Response(200, json={"model": "x"})

    provider = JevProvider(make_settings(), client=_client([], responder))
    with pytest.raises(ProviderError) as exc:
        await provider.decide("s", CHOICE_QUESTION)
    assert "answers" in str(exc.value)


async def test_invalid_answer_type_raises():
    def responder(request):
        return httpx.Response(200, json=_ok_body({"decision": {"type": "chat", "text": "hi"}}))

    provider = JevProvider(make_settings(), client=_client([], responder))
    with pytest.raises(ProviderError) as exc:
        await provider.decide("s", CHOICE_QUESTION)
    assert "invalid type" in str(exc.value)


async def test_missing_choice_field_raises():
    def responder(request):
        return httpx.Response(200, json=_ok_body({"decision": {"type": "choice"}}))

    provider = JevProvider(make_settings(), client=_client([], responder))
    with pytest.raises(ProviderError) as exc:
        await provider.decide("s", CHOICE_QUESTION)
    assert "missing 'choice'" in str(exc.value)
