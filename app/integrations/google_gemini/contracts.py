from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Literal, TypedDict

from app.domain.sql_repair import SqlRepairRequest
from app.domain.sql_generation import SqlGenerationRequest
from app.integrations.google_gemini.configuration import (
    GoogleGeminiConfiguration,
)


GeminiClientStatus = Literal[
    "success",
    "secret_missing",
    "secret_unavailable",
    "secret_invalid",
    "transport_timeout",
    "transport_unavailable",
    "http_error",
    "authentication_failed",
    "rate_limited",
    "provider_unavailable",
    "invalid_response",
    "unexpected_error",
]


class GeminiClientResult(TypedDict, total=False):
    status: GeminiClientStatus
    output_text: str
    finish_reasons: list[str]
    duration_ms: int
    public_error_code: str
    public_error_message: str
    diagnostics: dict[str, object]


@dataclass(frozen=True, slots=True)
class GeminiContractError(ValueError):
    message: str

    def __str__(self) -> str:
        return self.message


def build_gemini_prompt(request: SqlGenerationRequest) -> str:
    request_json = _stable_json(request)
    return "\n".join(
        (
            "Tarefa: gerar exatamente uma instrucao SQL de leitura.",
            "Retorne somente SQL em texto puro.",
            "A resposta deve comecar com SELECT ou WITH.",
            "Nao use Markdown, comentarios, JSON ou explicacoes.",
            "Nao altere o plano recebido.",
            "Respeite integralmente instructions e output_constraints.",
            "Use somente os dados contidos em SqlGenerationRequest.",
            "SqlGenerationRequest:",
            request_json,
        )
    )


def build_gemini_payload(
    *,
    request: SqlGenerationRequest,
    configuration: GoogleGeminiConfiguration,
) -> bytes:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": build_gemini_prompt(request),
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": configuration.temperature,
            "topP": configuration.top_p,
            "topK": configuration.top_k,
            "maxOutputTokens": configuration.max_output_tokens,
            "responseMimeType": configuration.response_mime_type,
            "thinkingConfig": {
                "thinkingBudget": configuration.thinking_budget,
            },
        },
    }
    return _stable_json(payload).encode("utf-8")


def build_gemini_repair_prompt(request: SqlRepairRequest) -> str:
    request_json = _stable_json(request)
    return "\n".join(
        (
            "Tarefa: corrigir a SQL existente.",
            "Preserve a intencao original da consulta.",
            "Preserve filtros, metricas, agrupamentos e escopo semantico.",
            "Corrija somente o necessario para resolver a falha estruturada informada.",
            "Respeite integralmente repair_context.",
            "Respeite integralmente instructions e output_constraints.",
            "Considere previous_attempts para evitar repeticao.",
            "Retorne exatamente uma instrucao SQL.",
            "Retorne somente SQL em texto puro.",
            "A resposta deve comecar com SELECT ou WITH.",
            "Nao use Markdown, JSON, comentarios ou explicacoes.",
            "Nao invente schemas, tabelas, colunas ou joins fora do contexto autorizado.",
            "Nao tente executar a consulta.",
            "Use somente os dados contidos em SqlRepairRequest.",
            "Nao inclua estado interno do grafo.",
            "SqlRepairRequest:",
            request_json,
        )
    )


def build_gemini_repair_payload(
    *,
    request: SqlRepairRequest,
    configuration: GoogleGeminiConfiguration,
) -> bytes:
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": build_gemini_repair_prompt(request),
                    }
                ],
            }
        ],
        "generationConfig": {
            "temperature": configuration.temperature,
            "topP": configuration.top_p,
            "topK": configuration.top_k,
            "maxOutputTokens": configuration.max_output_tokens,
            "responseMimeType": configuration.response_mime_type,
            "thinkingConfig": {
                "thinkingBudget": configuration.thinking_budget,
            },
        },
    }
    return _stable_json(payload).encode("utf-8")


def extract_gemini_text(value: Mapping[str, Any]) -> tuple[str, list[str]]:
    candidates = value.get("candidates")
    if not isinstance(candidates, list) or not candidates:
        raise GeminiContractError("candidates ausente.")
    candidate = candidates[0]
    if not isinstance(candidate, Mapping):
        raise GeminiContractError("candidate invalido.")
    texts: list[str] = []
    finish_reasons: list[str] = []
    finish_reason = candidate.get("finishReason")
    if isinstance(finish_reason, str) and _is_public_text(finish_reason):
        finish_reasons.append(finish_reason[:64])
    content = candidate.get("content")
    if isinstance(content, Mapping):
        parts = content.get("parts")
        if isinstance(parts, list):
            for part in parts:
                if not isinstance(part, Mapping):
                    continue
                text = part.get("text")
                if isinstance(text, str):
                    texts.append(text)
    output = "".join(texts).strip()
    if not output:
        raise GeminiContractError("texto ausente.")
    return output, finish_reasons


def parse_gemini_json_response(body: bytes) -> dict[str, Any]:
    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        raise GeminiContractError("JSON invalido.") from exc

    def reject_constant(value: str) -> object:
        raise ValueError(value)

    def no_duplicates(pairs: list[tuple[str, object]]) -> dict[str, object]:
        output: dict[str, object] = {}
        for key, raw in pairs:
            if key in output:
                raise ValueError("duplicate key")
            output[key] = raw
        return output

    try:
        parsed = json.loads(
            text,
            object_pairs_hook=no_duplicates,
            parse_constant=reject_constant,
        )
    except ValueError as exc:
        raise GeminiContractError("JSON invalido.") from exc
    if not isinstance(parsed, dict):
        raise GeminiContractError("Envelope invalido.")
    return parsed


def gemini_success(
    *,
    output_text: str,
    finish_reasons: list[str],
    duration_ms: int,
) -> GeminiClientResult:
    return {
        "status": "success",
        "output_text": output_text,
        "finish_reasons": list(finish_reasons),
        "duration_ms": duration_ms,
        "diagnostics": {
            "finish_reasons": list(finish_reasons),
        },
    }


def gemini_failure(
    status: GeminiClientStatus,
    *,
    duration_ms: int = 0,
    diagnostics: Mapping[str, object] | None = None,
) -> GeminiClientResult:
    if status == "success":
        raise GeminiContractError("Use gemini_success.")
    return {
        "status": status,
        "duration_ms": duration_ms,
        "public_error_code": f"GEMINI_{status.upper()}",
        "public_error_message": "Google Gemini falhou de forma sanitizada.",
        "diagnostics": _sanitize_diagnostics(diagnostics),
    }


def _stable_json(value: object) -> str:
    try:
        return json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
    except (TypeError, ValueError) as exc:
        raise GeminiContractError(
            "Payload Gemini nao serializavel."
        ) from exc


def _sanitize_diagnostics(value: Mapping[str, object] | None) -> dict[str, object]:
    if not isinstance(value, Mapping):
        return {}
    blocked = {
        "authorization",
        "headers",
        "body",
        "raw_response",
        "secret",
        "token",
        "api_key",
        "apikey",
        "url",
    }
    output: dict[str, object] = {}
    for key, raw in value.items():
        if not isinstance(key, str) or key.casefold() in blocked:
            continue
        if isinstance(raw, (str, int, bool)) or raw is None:
            text = str(raw).casefold()
            if any(marker in text for marker in ("bearer", "apikey", "api_key", "token", "secret", "select ")):
                continue
            output[key[:64]] = raw
    return output


def _is_public_text(value: str) -> bool:
    lowered = value.casefold()
    return not any(marker in lowered for marker in ("bearer", "apikey", "token", "secret"))
