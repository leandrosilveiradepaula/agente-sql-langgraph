from __future__ import annotations

import re
from typing import Any


_SENSITIVE_PATTERNS = [
    re.compile(
        r"\b[a-z][a-z0-9+.-]*://[^\s]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:password|passwd|pwd|token|secret|api[_-]?key|dsn)"
        r"\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:user|username)\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
]


def sanitize_text(value: str) -> str:
    output = value
    for pattern in _SENSITIVE_PATTERNS:
        output = pattern.sub("[redacted]", output)
    return output


def safe_message(value: Any) -> str:
    text = str(value) if value is not None else "Falha de preflight."
    sanitized = sanitize_text(text)
    return sanitized[:300] if sanitized else "Falha de preflight."


def safe_provider_name(value: Any) -> str:
    text = sanitize_text(str(value)) if value is not None else ""
    return text[:80] if text else "unknown"


def safe_optional_text(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    sanitized = sanitize_text(value.strip())
    return sanitized[:300] if sanitized else None


def safe_warnings(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            item
            for item in (safe_optional_text(entry) for entry in value)
            if item
        },
        key=str.casefold,
    )
