"""Verification layer: JEV-vs-Claude agreement verdict + metrics."""

from jevxagent.router import verification
from jevxagent.router.decision import DecisionEvent
from jevxagent.telemetry import metrics


def _event(candidate_action: str, source: str = "intercept") -> DecisionEvent:
    return DecisionEvent(candidate_action=candidate_action, source=source)


def test_agree():
    verdict = verification.evaluate(_event("Read"), "Read")
    assert verdict.agreement is True
    assert verdict.label == "agree"
    assert verdict.jev_choice == "Read"


def test_disagree():
    verdict = verification.evaluate(_event("Bash"), "Read")
    assert verdict.agreement is False
    assert verdict.label == "disagree"


def test_no_candidate_action_is_not_comparable():
    verdict = verification.evaluate(DecisionEvent(source="intercept"), "Read")
    assert verdict.agreement is None
    assert verdict.label is None


def test_manual_source_is_not_comparable():
    verdict = verification.evaluate(_event("Read", source="manual"), "Read")
    assert verdict.agreement is None
    assert verdict.label is None


def test_none_jev_choice_is_not_comparable():
    verdict = verification.evaluate(_event("Read"), None)
    assert verdict.agreement is None
    assert verdict.label is None


def test_whitespace_normalized():
    verdict = verification.evaluate(_event("  Read  "), "Read")
    assert verdict.agreement is True


def _row(verdict: str | None) -> dict:
    return {"meta": {"verdict": verdict}}


def test_agreement_stats():
    decisions = [
        _row("agree"),
        _row("agree"),
        _row("disagree"),
        _row("jev_unavailable"),
        {"meta": {}},  # manual decision, no verdict
    ]
    stats = metrics.agreement_stats(decisions)
    assert stats["compared"] == 3
    assert stats["agree"] == 2
    assert stats["disagree"] == 1
    assert stats["unavailable"] == 1
    assert stats["agreement_rate"] == round(2 / 3 * 100, 1)


def test_agreement_stats_empty():
    stats = metrics.agreement_stats([])
    assert stats["compared"] == 0
    assert stats["agreement_rate"] is None
