"""Verification layer: compare JEV's structured decision with Claude's choice.

For intercepted ``tool_selection`` events, the proxy records both:

- ``candidate_action`` — the tool Claude actually selected (observable from the
  assistant response), and
- the JEV decision — what JEV chose for the same question.

This module turns those two into a small verdict. It is advisory: it flags
agreement/disagreement for later action, it never blocks or rewrites traffic.
"""

from __future__ import annotations

from dataclasses import dataclass

from .decision import DecisionEvent


@dataclass
class Verdict:
    jev_choice: str | None
    agreement: bool | None  # None when not comparable
    label: str | None  # "agree" | "disagree" | None


def evaluate(event: DecisionEvent, jev_choice: str | None) -> Verdict:
    """Compare JEV's decision against the observable Claude choice.

    Returns a Verdict with ``agreement=None`` when the event has no
    ``candidate_action`` (e.g. a manual ``/v1/decision`` request) — those are
    not verification events.
    """
    if jev_choice is None:
        return Verdict(None, None, None)
    candidate = (event.candidate_action or "").strip()
    if event.source != "intercept" or not candidate:
        return Verdict(jev_choice, None, None)
    agree = candidate == jev_choice.strip()
    return Verdict(jev_choice, agree, "agree" if agree else "disagree")
