"""Deterministic, extremely cheap decision classifier.

The router must never be more expensive than the task it routes (project rule
#13). This classifier uses only regex/length heuristics — no model calls.
"""

from __future__ import annotations

import re

from ..telemetry.events import DecisionType

_URL_RE = re.compile(r"https?://[^\s]+", re.IGNORECASE)
_GITHUB_RE = re.compile(r"github\.com/[^/\s]+/[^/\s]+", re.IGNORECASE)
_YESNO_RE = re.compile(
    r"^(is|are|does|do|did|can|could|should|would|has|have|was|were)\b.*\?$",
    re.IGNORECASE,
)
_WHICH_RE = re.compile(r"\b(which|choose|pick|select)\b", re.IGNORECASE)
_VERIFY_RE = re.compile(
    r"\b(verify|validate|correct|valid|expected|match(es)?|satisfy|ok\b|okay)\b",
    re.IGNORECASE,
)
_RELEVANT_RE = re.compile(r"\brelevant\b", re.IGNORECASE)
_COMPARE_RE = re.compile(r"\b(compare|versus|vs\.?|better|worse|faster|smaller|larger)\b", re.IGNORECASE)
_EXTRACT_RE = re.compile(r"\b(extract|find|get|list|return|parse|read)\b", re.IGNORECASE)
_TRANSFORM_RE = re.compile(r"\b(convert|format|rename|normalize|lowercase|uppercase)\b", re.IGNORECASE)
_NEXT_RE = re.compile(r"\b(next|then|continue|proceed|what now|what should)\b", re.IGNORECASE)
_TOOL_RE = re.compile(r"\b(tool|command|function|api|endpoint|call)\b", re.IGNORECASE)
_COMPLEX_RE = re.compile(
    r"\b(design|plan|architect|implement|write code|debug|explain why|analyze|"
    r"research|summarize|synthesize|compare and analyze|multi-step|evaluate"
    r"critically|propose|refactor|build)\b",
    re.IGNORECASE,
)

_ROUTABLE_TYPES = {
    DecisionType.CLASSIFICATION,
    DecisionType.BINARY_DECISION,
    DecisionType.MULTIPLE_CHOICE,
    DecisionType.SELECTION,
    DecisionType.SIMPLE_EXTRACTION,
    DecisionType.SIMPLE_COMPARISON,
    DecisionType.ENTITY_IDENTIFICATION,
    DecisionType.VERIFICATION,
    DecisionType.RELEVANCE,
    DecisionType.URL_CLASSIFICATION,
    DecisionType.SIMPLE_TRANSFORMATION,
    DecisionType.NEXT_ACTION,
    DecisionType.TOOL_SELECTION,
}


def infer_decision_type(
    question: str, options: list[str] | None = None, context: str = ""
) -> DecisionType:
    options = options or []
    text = f"{question} {context}"

    if _GITHUB_RE.search(text):
        return DecisionType.URL_CLASSIFICATION
    if _URL_RE.search(text):
        return DecisionType.ENTITY_IDENTIFICATION
    if _VERIFY_RE.search(question):
        return DecisionType.VERIFICATION
    if _RELEVANT_RE.search(question):
        return DecisionType.RELEVANCE
    if _YESNO_RE.search(question) and not options:
        return DecisionType.BINARY_DECISION
    if len(options) >= 3:
        return DecisionType.MULTIPLE_CHOICE
    if len(options) == 2:
        return DecisionType.SELECTION
    if _WHICH_RE.search(text) and len(options) > 0:
        return DecisionType.SELECTION
    if _COMPARE_RE.search(text):
        return DecisionType.SIMPLE_COMPARISON
    if _TOOL_RE.search(text):
        return DecisionType.TOOL_SELECTION
    if _EXTRACT_RE.search(text):
        return DecisionType.SIMPLE_EXTRACTION
    if _TRANSFORM_RE.search(text):
        return DecisionType.SIMPLE_TRANSFORMATION
    if _NEXT_RE.search(text):
        return DecisionType.NEXT_ACTION
    if _YESNO_RE.search(text):
        return DecisionType.BINARY_DECISION
    return DecisionType.CLASSIFICATION


def estimate_complexity(question: str, options: list[str] | None = None, context: str = "") -> float:
    """0.0 = trivial, 1.0 = definitely complex. Deterministic and cheap."""
    score = 0.0
    full = f"{context}\n{question}"
    options = options or []

    if _COMPLEX_RE.search(question):
        score += 0.6
    if len(question) > 400:
        score += 0.3
    elif len(question) > 120:
        score += 0.1
    if len(context) > 2000:
        score += 0.25
    if len(options) > 6:
        score += 0.2
    if full.count("?") > 2:
        score += 0.2
    if any(marker in question.lower() for marker in ("why", "how should", "explain", "elaborate")):
        score += 0.35
    return min(score, 1.0)


def is_potentially_routable(decision_type: DecisionType) -> bool:
    return decision_type in _ROUTABLE_TYPES
