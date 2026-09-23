"""Relevant-context extraction.

JEV must NEVER receive the entire conversation by default (project rule #10).
This module trims context to a small, bounded budget so each JEV request stays
tiny and structured. Deterministic — no model calls.
"""

from __future__ import annotations

import math

from ..config import Settings


def naive_token_estimate(text: str) -> int:
    """Rough 4 chars/token estimate. Used only for budgets, never reported as
    a measured token count."""
    return max(1, math.ceil(len(text) / 4))


def trim_context(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    cut = text[:max_chars]
    last_space = cut.rfind(" ")
    if last_space > max_chars // 2:
        cut = cut[:last_space]
    return cut.rstrip() + "\n…[context truncated]"


def build_decision_prompt(
    question: str,
    options: list[str] | None,
    context: str,
    answer_format: str,
    settings: Settings,
) -> str:
    """Small, structured prompt for JEV. Answer format is constrained."""
    trimmed = trim_context(context or "", settings.jev_max_context_chars)
    parts = []
    if trimmed:
        parts.append(f"Context:\n{trimmed}")
    parts.append(f"Question: {question}")
    if options:
        numbered = "\n".join(f"{i + 1}. {option}" for i, option in enumerate(options))
        parts.append(f"Options:\n{numbered}")

    if answer_format == "yesno":
        parts.append('Answer "decision" with YES or NO only.')
    elif answer_format == "choice" and options:
        parts.append(
            "Answer with the exact text of the chosen option in \"decision\", "
            "and its number in \"choice\"."
        )
    elif answer_format == "label":
        parts.append('Answer with a short label in "decision".')
    else:
        parts.append('Answer with a short value in "decision".')

    parts.append("Always include a numeric \"confidence\" between 0.0 and 1.0.")
    return "\n".join(parts)
