from __future__ import annotations

import re
from typing import Any


_SENSITIVE_PATTERNS = [
    re.compile(
        r"\b[a-z][a-z0-9+.-]*://[^\s]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:password|passwd|pwd|token|secret|api[_-]?key|dsn|"
        r"host|hostname)"
        r"\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:user|username)\s*[:=]\s*[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\b(?:authorization|auth)\s*[:=]\s*(?:bearer\s+)?[^\s,;]+",
        re.IGNORECASE,
    ),
    re.compile(
        r"\bbearer\s+[A-Za-z0-9._~+/\-]+=*",
        re.IGNORECASE,
    ),
]


def sanitize_text(
    value: str,
    *,
    forbidden_texts: tuple[str, ...] = (),
) -> str:
    output = value
    for forbidden in forbidden_texts:
        text = forbidden.strip() if isinstance(forbidden, str) else ""
        if len(text) >= 8:
            output = output.replace(text, "[redacted]")
    for pattern in _SENSITIVE_PATTERNS:
        output = pattern.sub("[redacted]", output)
    return output


def safe_message(
    value: Any,
    *,
    forbidden_texts: tuple[str, ...] = (),
) -> str:
    text = str(value) if value is not None else "Falha de preflight."
    sanitized = sanitize_text(text, forbidden_texts=forbidden_texts)
    return sanitized[:300] if sanitized else "Falha de preflight."


def safe_provider_name(
    value: Any,
    *,
    forbidden_texts: tuple[str, ...] = (),
) -> str:
    text = (
        sanitize_text(str(value), forbidden_texts=forbidden_texts)
        if value is not None
        else ""
    )
    return text[:80] if text else "unknown"


def safe_optional_text(
    value: Any,
    *,
    forbidden_texts: tuple[str, ...] = (),
) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    sanitized = sanitize_text(
        value.strip(),
        forbidden_texts=forbidden_texts,
    )
    return sanitized[:300] if sanitized else None


def safe_warnings(
    value: Any,
    *,
    forbidden_texts: tuple[str, ...] = (),
) -> list[str]:
    if not isinstance(value, list):
        return []
    return sorted(
        {
            item
            for item in (
                safe_optional_text(
                    entry,
                    forbidden_texts=forbidden_texts,
                )
                for entry in value
            )
            if item
        },
        key=str.casefold,
    )
