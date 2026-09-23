"""Deterministic classifier + context extractor."""

from jevxagent.context.extractor import (
    build_decision_prompt,
    naive_token_estimate,
    trim_context,
)
from jevxagent.router.classifier import (
    estimate_complexity,
    infer_decision_type,
    is_potentially_routable,
)
from jevxagent.telemetry.events import DecisionType


def test_github_url_classification():
    assert infer_decision_type("Is this a GitHub repo?", context="https://github.com/a/b") == \
        DecisionType.URL_CLASSIFICATION


def test_plain_url_entity_identification():
    assert infer_decision_type("What is this?", context="https://example.com/x") == \
        DecisionType.ENTITY_IDENTIFICATION


def test_yesno_binary():
    assert infer_decision_type("Is the sky blue?") == DecisionType.BINARY_DECISION


def test_multiple_choice():
    assert infer_decision_type("Which category?", options=["a", "b", "c"]) == \
        DecisionType.MULTIPLE_CHOICE


def test_two_options_selection():
    assert infer_decision_type("Choose one", options=["a", "b"]) == DecisionType.SELECTION


def test_verification():
    assert infer_decision_type("Does this output match the expected result?") == \
        DecisionType.VERIFICATION


def test_relevance():
    assert infer_decision_type("Is this result relevant?") == DecisionType.RELEVANCE


def test_comparison():
    assert infer_decision_type("Which is faster, A or B?") == DecisionType.SIMPLE_COMPARISON


def test_extraction():
    assert infer_decision_type("Extract the repo name from the URL") == \
        DecisionType.SIMPLE_EXTRACTION


def test_complexity_low_for_simple():
    assert estimate_complexity("Is this a GitHub URL?", [], "short context") < 0.6


def test_complexity_high_for_design():
    score = estimate_complexity(
        "Design a distributed system architecture and explain the tradeoffs",
        [],
        "complex project context",
    )
    assert score >= 0.6


def test_complexity_grows_with_length():
    short = estimate_complexity("short question?", [], "")
    long = estimate_complexity("q?" * 300, [], "")
    assert long > short


def test_potentially_routable_set():
    assert is_potentially_routable(DecisionType.BINARY_DECISION)
    assert not is_potentially_routable(DecisionType.OTHER)


def test_trim_context():
    assert trim_context("short", 100) == "short"
    trimmed = trim_context("word " * 100, 200)
    assert len(trimmed) < 300
    assert "[context truncated]" in trimmed


def test_naive_token_estimate():
    assert naive_token_estimate("abcd" * 10) == 10
    assert naive_token_estimate("") == 1


def test_build_decision_prompt_includes_everything():
    from jevxagent.config import Settings

    prompt = build_decision_prompt(
        "Is this valid?",
        ["YES", "NO"],
        "some context",
        "yesno",
        Settings(jev_max_context_chars=4000),
    )
    assert "Is this valid?" in prompt
    assert "YES" in prompt
    assert "some context" in prompt
    assert "confidence" in prompt
