"""Fail-closed source boundary for approved canonical tenant contexts.

Historical/evaluation SQL and question examples belong to independent
quality-control artifacts. The new canonical runtime may use versioned
structural intent patterns but never source SQL text or example questions
until a separately attested semantic-signal provenance workflow exists.

Unlike a caller-supplied historical_evaluation_sql_excluded=True flag,
this checks the actual content of the pattern collection. It is deliberately
limited to the canonical mode; legacy behavior remains unchanged.
"""
from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class CanonicalSourceBoundaryError(ValueError):
    """A canonical pattern may include historical/evaluation material."""


def require_structural_patterns_only(raw: Mapping[str, Any]) -> None:
    """Check actual fields, never trusting a provenance declaration alone.

    Empty examples are intentional: the separate benchmark contains questions
    as well as expected SQL. Tenant-approved entity aliases and intent signals
    are still available elsewhere in the canonical context.
    """
    entries = raw.get("padroes")
    if not isinstance(entries, list) or not 1 <= len(entries) <= 4096:
        raise CanonicalSourceBoundaryError("CANONICAL_PATTERNS_INVALID")
    for item in entries:
        if not isinstance(item, Mapping):
            raise CanonicalSourceBoundaryError("CANONICAL_PATTERN_INVALID")
        if item.get("source_use") != "APPROVED_SEMANTIC_STRUCTURAL":
            raise CanonicalSourceBoundaryError(
                "CANONICAL_PATTERN_PROVENANCE_UNAPPROVED"
            )
        sql_text = item.get("sql_pattern")
        if sql_text is not None and (
            not isinstance(sql_text, str) or sql_text.strip()
        ):
            raise CanonicalSourceBoundaryError(
                "CANONICAL_SQL_EXAMPLE_FORBIDDEN"
            )
        examples = item.get("business_question_examples")
        if examples != []:
            raise CanonicalSourceBoundaryError(
                "CANONICAL_EVALUATION_QUESTION_FORBIDDEN"
            )
        # Do not copy any unreviewed free-text instructions into the provider.
        if item.get("notes") not in (None, ""):
            raise CanonicalSourceBoundaryError(
                "CANONICAL_PATTERN_FREE_TEXT_UNREVIEWED"
            )
