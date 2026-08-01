from __future__ import annotations

import json
from dataclasses import dataclass

from app.integrations.watson.flow_limits import (
    WatsonFlowContractError,
    WatsonFlowLimits,
)


@dataclass(frozen=True, slots=True)
class WatsonSqlTransportResult:
    status: str
    sql_transport: str | None
    error_code: str | None
    message: str | None


_NO_SPACE_BEFORE = {",", ")", ".", "::", ";", "+", "-", "*", "/", "%", "=", "<", ">", "<=", ">=", "<>", "!=", "||"}
_NO_SPACE_AFTER = {"(", ".", "::", "+", "-", "*", "/", "%", "=", "<", ">", "<=", ">=", "<>", "!=", "||"}


def build_watson_flow_payload(sql_transport: str) -> dict[str, object]:
    if not isinstance(sql_transport, str) or not sql_transport:
        raise WatsonFlowContractError("sql_transport deve ser texto nao vazio.")
    payload = {"sql_query": str(sql_transport)}
    _payload_size(payload)
    return dict(payload)


def compact_sql_for_watson_transport(
    approved_sql: str,
    limits: WatsonFlowLimits,
) -> WatsonSqlTransportResult:
    if not isinstance(approved_sql, str):
        return _error("WATSON_SQL_TRANSPORT_INVALID", "SQL aprovada invalida.")
    if "\x00" in approved_sql:
        return _error("WATSON_SQL_TRANSPORT_INVALID", "SQL contem NUL.")
    if any(_forbidden_control(char) for char in approved_sql):
        return _error("WATSON_SQL_TRANSPORT_INVALID", "SQL contem controle.")
    if not approved_sql.strip():
        return _error("WATSON_SQL_TRANSPORT_INVALID", "SQL vazia.")
    if len(approved_sql.encode("utf-8")) > limits.max_approved_sql_bytes:
        return _error("WATSON_SQL_TRANSPORT_TOO_LARGE", "SQL aprovada excede limite.")

    tokens: list[str] = []
    index = 0
    length = len(approved_sql)
    while index < length:
        char = approved_sql[index]
        if char.isspace():
            index += 1
            continue
        if char == "-" and _peek(approved_sql, index + 1) == "-":
            index = _skip_line_comment(approved_sql, index + 2)
            _append_comment_gap(tokens)
            continue
        if char == "/" and _peek(approved_sql, index + 1) == "*":
            end = approved_sql.find("*/", index + 2)
            if end < 0:
                return _error(
                    "WATSON_SQL_TRANSPORT_UNCLOSED_COMMENT",
                    "Comentario de bloco nao fechado.",
                )
            index = end + 2
            _append_comment_gap(tokens)
            continue
        if char == "'":
            token, index, error = _read_quoted(
                approved_sql,
                index,
                quote="'",
                error_code="WATSON_SQL_TRANSPORT_UNCLOSED_STRING",
            )
            if error:
                return error
            tokens.append(token)
            continue
        if char == '"':
            token, index, error = _read_quoted(
                approved_sql,
                index,
                quote='"',
                error_code="WATSON_SQL_TRANSPORT_UNCLOSED_IDENTIFIER",
            )
            if error:
                return error
            tokens.append(token)
            continue
        two = approved_sql[index : index + 2]
        if two in {"<=", ">=", "<>", "!=", "||", "::"}:
            tokens.append(two)
            index += 2
            continue
        if char in "(),.+-*/%=<>;":
            tokens.append(char)
            index += 1
            continue
        start = index
        while index < length and not approved_sql[index].isspace():
            if approved_sql[index] in "'\"(),.+-*/%=<>;":
                break
            if approved_sql[index] == "-" and _peek(approved_sql, index + 1) == "-":
                break
            index += 1
        tokens.append(approved_sql[start:index])

    compacted = _join_tokens([token for token in tokens if token])
    if not compacted:
        return _error("WATSON_SQL_TRANSPORT_INVALID", "SQL sem conteudo.")
    if len(compacted) > limits.max_transport_sql_characters:
        return _error(
            "WATSON_SQL_TRANSPORT_TOO_LARGE",
            "SQL compactada excede limite em caracteres.",
        )
    if len(compacted.encode("utf-8")) > limits.max_transport_sql_bytes:
        return _error(
            "WATSON_SQL_TRANSPORT_TOO_LARGE",
            "SQL compactada excede limite em bytes.",
        )
    try:
        payload = build_watson_flow_payload(compacted)
    except WatsonFlowContractError:
        return _error("WATSON_SQL_TRANSPORT_INVALID", "Payload Watson invalido.")
    if _payload_size(payload) > limits.max_payload_bytes:
        return _error("WATSON_SQL_TRANSPORT_TOO_LARGE", "Payload Watson excede limite.")
    return WatsonSqlTransportResult(
        status="success",
        sql_transport=compacted,
        error_code=None,
        message=None,
    )


def _read_quoted(
    sql: str,
    start: int,
    *,
    quote: str,
    error_code: str,
) -> tuple[str, int, WatsonSqlTransportResult | None]:
    index = start + 1
    length = len(sql)
    while index < length:
        if sql[index] == quote:
            if _peek(sql, index + 1) == quote:
                index += 2
                continue
            return sql[start : index + 1], index + 1, None
        index += 1
    return "", length, _error(error_code, "Literal SQL nao fechado.")


def _join_tokens(tokens: list[str]) -> str:
    output: list[str] = []
    previous = ""
    for token in tokens:
        if token == " ":
            if output and output[-1] != " ":
                output.append(" ")
            previous = token
            continue
        if output and output[-1] == " " and token in _NO_SPACE_BEFORE:
            output.pop()
        elif output and output[-1] != " " and _needs_space(previous, token):
            output.append(" ")
        output.append(token)
        previous = token
    return "".join(output).strip()


def _needs_space(previous: str, current: str) -> bool:
    if not previous or previous == " ":
        return False
    if current in _NO_SPACE_BEFORE or previous in _NO_SPACE_AFTER:
        return False
    return _token_can_merge(previous[-1], current[0])


def _token_can_merge(left: str, right: str) -> bool:
    return (
        (left.isalnum() or left == "_" or left in {"'", '"', ")"})
        and (right.isalnum() or right == "_" or right == '"' or right == "'")
    )


def _skip_line_comment(sql: str, index: int) -> int:
    while index < len(sql) and sql[index] not in "\r\n":
        index += 1
    return index


def _append_comment_gap(tokens: list[str]) -> None:
    if tokens and tokens[-1] != " ":
        tokens.append(" ")


def _peek(sql: str, index: int) -> str:
    return sql[index] if index < len(sql) else ""


def _forbidden_control(char: str) -> bool:
    return (ord(char) < 32 and char not in "\r\n\t") or ord(char) == 127


def _payload_size(payload: dict[str, object]) -> int:
    return len(
        json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    )


def _error(code: str, message: str) -> WatsonSqlTransportResult:
    return WatsonSqlTransportResult(
        status="rejected",
        sql_transport=None,
        error_code=code,
        message=message,
    )
