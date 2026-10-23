"""Structural, deployment-owned pin for a versioned semantic snapshot.

The fingerprint is not business knowledge, not an authorization token and
never comes from a user question, generator response, tenant claim or benchmark.
Changing an approved snapshot must be an explicit operator configuration
change. With the pin absent, the historical loader stays compatible.
"""
from __future__ import annotations

import re

EXPECTED_CONTEXT_FINGERPRINT_ENV = "SEMANTIC_CONTEXT_EXPECTED_FINGERPRINT"
_SHA256_LOWER_HEX = re.compile(r"^[a-f0-9]{64}$")


def validate_expected_context_fingerprint(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not _SHA256_LOWER_HEX.fullmatch(value):
        raise ValueError("Expected semantic context fingerprint is invalid.")
    return value
