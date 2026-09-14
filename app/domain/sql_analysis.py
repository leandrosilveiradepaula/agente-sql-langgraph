from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict


SQL_ANALYZER_VERSION = "v1.1.0-structured-where-predicates"

TokenKind = Literal[
    "word",
    "quoted_identifier",
    "string",
    "number",
    "symbol",
]

SqlAnalysisStatus = Literal["analyzed", "invalid"]

SqlAnalysisErrorCode = Literal[
    "SQL_ANALYSIS_INPUT_INVALID",
    "SQL_ANALYSIS_CONTROL_CHARACTER",
    "SQL_ANALYSIS_UNTERMINATED_STRING",
    "SQL_ANALYSIS_UNTERMINATED_IDENTIFIER",
    "SQL_ANALYSIS_UNTERMINATED_COMMENT",
    "SQL_ANALYSIS_EMPTY",
    "SQL_ANALYSIS_MULTIPLE_STATEMENTS",
    "SQL_ANALYSIS_UNSUPPORTED_STRUCTURE",
]


class SqlToken(TypedDict):
    kind: TokenKind
    value: str
    normalized: str
    position: int


class SqlObjectReference(TypedDict, total=False):
    raw: str
    schema: str | None
    table: str
    alias: str | None
    source: Literal["from", "join", "cte", "function", "subquery"]
    is_cte: bool
    is_function: bool
    is_subquery: bool
    position: int


class SqlColumnReference(TypedDict, total=False):
    raw: str
    qualifier: str | None
    schema: str | None
    table: str | None
    column: str
    clause: str
    is_wildcard: bool


class SqlJoinComparison(TypedDict, total=False):
    left_qualifier: str | None
    left_column: str
    operator: str
    right_qualifier: str | None
    right_column: str


class SqlJoinReference(TypedDict, total=False):
    join_type: str
    left_table: str | None
    right_table: str | None
    right_alias: str | None
    condition_columns: list[SqlColumnReference]
    join_comparisons: list[SqlJoinComparison]


class SqlSelectItem(TypedDict, total=False):
    expression: str
    alias: str | None
    functions: list[str]
    column_references: list[SqlColumnReference]


class SqlOrderByItem(TypedDict, total=False):
    expression: str
    direction: Literal["asc", "desc"] | None
    direction_explicit: bool
    nulls: Literal["first", "last"] | None
    referenced_alias: str | None
    resolved_select_item_index: int | None


class SqlPredicate(TypedDict, total=False):
    clause: str
    qualifier: str | None
    column: str | None
    operator: str | None
    literal_type: str | None
    value: Any
    supported: bool
    reason: str


class SqlQueryScope(TypedDict):
    scope_id: str
    parent_scope_id: str | None
    is_root: bool
    scope_type: Literal["root", "cte", "subquery"]
    scope_name: str | None
    physical_tables: list[str]
    child_scopes: list[str]
    object_references: list[SqlObjectReference]
    select_items: list[SqlSelectItem]
    group_by_items: list[str]
    order_by_items: list[SqlOrderByItem]
    has_aggregate: bool
    has_reducing_aggregate: bool
    joins: list[SqlJoinReference]
    output_lineage: list[dict[str, Any]]
    raw_table_join_count: int
    aggregated_scope_join_count: int


class SqlStatementAnalysis(TypedDict):
    status: SqlAnalysisStatus
    analyzer_version: str
    sql_fingerprint: str
    statement_count: int
    statement_type: str | None
    starts_with_read_keyword: bool
    with_body_is_select: bool
    tokens: list[SqlToken]
    token_norms: list[str]
    object_references: list[SqlObjectReference]
    column_references: list[SqlColumnReference]
    joins: list[SqlJoinReference]
    predicates: list[SqlPredicate]
    query_scopes: list[SqlQueryScope]
    ctes: list[str]
    cte_output_columns: dict[str, list[str]]
    aliases: dict[str, str]
    expression_aliases: list[str]
    functions: list[str]
    schemas: list[str]
    tables: list[str]
    has_comments: bool
    comment_count: int
    has_limit: bool
    has_select_star: bool
    has_table_star: bool
    has_select_into: bool
    errors: list[dict[str, Any]]
    warnings: list[str]


class SqlAnalysisError(ValueError):
    def __init__(
        self,
        code: SqlAnalysisErrorCode,
        message: str,
    ) -> None:
        self.code = code
        self.message = message
        super().__init__(message)


_CLAUSE_KEYWORDS = {
    "select",
    "from",
    "where",
    "join",
    "on",
    "group",
    "order",
    "having",
    "limit",
    "union",
}

_RESERVED_WORDS = {
    "all",
    "and",
    "as",
    "asc",
    "between",
    "by",
    "case",
    "cast",
    "cross",
    "current_date",
    "current_time",
    "current_timestamp",
    "desc",
    "distinct",
    "else",
    "end",
    "false",
    "filter",
    "from",
    "full",
    "group",
    "having",
    "in",
    "inner",
    "interval",
    "is",
    "join",
    "lateral",
    "left",
    "like",
    "limit",
    "natural",
    "not",
    "null",
    "on",
    "or",
    "order",
    "outer",
    "over",
    "right",
    "select",
    "then",
    "true",
    "union",
    "using",
    "when",
    "where",
    "with",
}

_JOIN_STRUCTURE_KEYWORDS = {
    "join",
    "inner",
    "left",
    "right",
    "full",
    "outer",
    "cross",
    "natural",
    "on",
    "using",
    "lateral",
}

_TABLE_BOUNDARY_KEYWORDS = {
    "where",
    *_JOIN_STRUCTURE_KEYWORDS,
    "group",
    "order",
    "having",
    "limit",
    "union",
}

_JOIN_PREFIX_WORDS = _JOIN_STRUCTURE_KEYWORDS - {"on", "using", "lateral"}

_TEMPORAL_PART_WORDS = {
    "microsecond",
    "microseconds",
    "millisecond",
    "milliseconds",
    "second",
    "seconds",
    "minute",
    "minutes",
    "hour",
    "hours",
    "day",
    "days",
    "week",
    "weeks",
    "month",
    "months",
    "quarter",
    "quarters",
    "year",
    "years",
}

_TEMPORAL_PART_FUNCTIONS = {
    "date_add",
    "date_diff",
    "date_part",
    "date_sub",
    "date_trunc",
    "datediff",
    "extract",
    "strftime",
    "time_bucket",
}


def analyze_sql(sql: str) -> SqlStatementAnalysis:
    if not isinstance(sql, str):
        raise SqlAnalysisError(
            "SQL_ANALYSIS_INPUT_INVALID",
            "SQL deve ser texto.",
        )

    tokens, comment_count = _tokenize(sql)
    statement_tokens = _single_statement(tokens)
    if not statement_tokens:
        raise SqlAnalysisError(
            "SQL_ANALYSIS_EMPTY",
            "SQL nao pode estar vazia.",
        )
    _validate_balanced_parentheses(statement_tokens)

    statement_type = _first_word(statement_tokens)
    ctes = _extract_ctes(statement_tokens)
    cte_output_columns = _extract_cte_output_columns(statement_tokens)
    with_body_is_select = (
        _first_word_after_ctes(statement_tokens, ctes) == "select"
        if statement_type == "with"
        else False
    )

    object_references = _extract_objects(statement_tokens, ctes)
    column_references = _extract_columns(
        statement_tokens,
        object_references,
        cte_output_columns,
    )
    joins = _extract_joins(statement_tokens, object_references)
    predicates = _extract_predicates(statement_tokens)
    query_scopes = _extract_query_scopes(statement_tokens)
    aliases = {
        item["alias"].casefold(): _qualified_or_table(item)
        for item in object_references
        if item.get("alias")
        and not item.get("is_cte")
        and not item.get("is_subquery")
    }
    expression_aliases = _extract_expression_aliases(statement_tokens)
    functions = sorted(set(_extract_functions(statement_tokens)))
    schemas = sorted(
        {
            str(item.get("schema")).casefold()
            for item in object_references
            if item.get("schema")
        }
    )
    tables = sorted(
        {
            _qualified_or_table(item).casefold()
            for item in object_references
            if not item.get("is_cte")
            and not item.get("is_function")
            and not item.get("is_subquery")
        }
    )

    analysis: SqlStatementAnalysis = {
        "status": "analyzed",
        "analyzer_version": SQL_ANALYZER_VERSION,
        "sql_fingerprint": _fingerprint(sql),
        "statement_count": 1,
        "statement_type": statement_type,
        "starts_with_read_keyword": statement_type in {"select", "with"},
        "with_body_is_select": with_body_is_select,
        "tokens": deepcopy(statement_tokens),
        "token_norms": [token["normalized"] for token in statement_tokens],
        "object_references": object_references,
        "column_references": column_references,
        "joins": joins,
        "predicates": predicates,
        "query_scopes": query_scopes,
        "ctes": ctes,
        "cte_output_columns": cte_output_columns,
        "aliases": aliases,
        "expression_aliases": expression_aliases,
        "functions": functions,
        "schemas": schemas,
        "tables": tables,
        "has_comments": comment_count > 0,
        "comment_count": comment_count,
        "has_limit": any(
            token["normalized"] == "limit"
            for token in statement_tokens
        ),
        "has_select_star": any(
            item.get("is_wildcard") and not item.get("qualifier")
            for item in column_references
        ),
        "has_table_star": any(
            item.get("is_wildcard") and item.get("qualifier")
            for item in column_references
        ),
        "has_select_into": _has_select_into(statement_tokens),
        "errors": [],
        "warnings": [],
    }
    return deepcopy(analysis)


def analysis_fingerprint(analysis: SqlStatementAnalysis) -> str:
    return _stable_hash(
        {
            "analyzer_version": analysis.get("analyzer_version"),
            "sql_fingerprint": analysis.get("sql_fingerprint"),
            "statement_count": analysis.get("statement_count"),
            "statement_type": analysis.get("statement_type"),
            "objects": analysis.get("object_references", []),
            "columns": analysis.get("column_references", []),
            "joins": analysis.get("joins", []),
            "predicates": analysis.get("predicates", []),
            "query_scopes": analysis.get("query_scopes", []),
        }
    )


def safe_sql_analysis(
    analysis: SqlStatementAnalysis,
) -> SqlStatementAnalysis:
    """
    Remove tokens brutos antes de persistir a analise no GraphState.
    """

    safe = deepcopy(analysis)
    safe["tokens"] = []
    safe["token_norms"] = [
        token["normalized"]
        for token in analysis.get("tokens", [])
        if token.get("kind") != "string"
    ]
    for predicate in safe.get("predicates", []):
        if predicate.get("literal_type") == "string":
            predicate["value"] = "<string>"
    return safe


def sanitized_sql_text(sql: str) -> str:
    tokens, _ = _tokenize(sql)
    statement_tokens = _single_statement(tokens)
    return " ".join(
        token["value"]
        for token in statement_tokens
        if token["kind"] != "string"
    ).casefold()


def normalized_sql_tokens(
    sql: str,
    *,
    include_string_values: bool,
) -> list[str]:
    tokens, _ = _tokenize(sql)
    statement_tokens = _single_statement(tokens)
    return [
        (
            token["normalized"]
            if include_string_values or token["kind"] != "string"
            else "<string>"
        )
        for token in statement_tokens
    ]


def _tokenize(sql: str) -> tuple[list[SqlToken], int]:
    tokens: list[SqlToken] = []
    comment_count = 0
    index = 0
    while index < len(sql):
        character = sql[index]
        if ord(character) < 32 and character not in "\r\n\t":
            raise SqlAnalysisError(
                "SQL_ANALYSIS_CONTROL_CHARACTER",
                "SQL contem caractere de controle nao permitido.",
            )
        if character.isspace():
            index += 1
            continue
        if character == "-" and _peek(sql, index + 1) == "-":
            comment_count += 1
            index += 2
            while index < len(sql) and sql[index] not in "\r\n":
                index += 1
            continue
        if character == "/" and _peek(sql, index + 1) == "*":
            comment_count += 1
            index += 2
            while index + 1 < len(sql) and not (
                sql[index] == "*" and sql[index + 1] == "/"
            ):
                index += 1
            if index + 1 >= len(sql):
                raise SqlAnalysisError(
                    "SQL_ANALYSIS_UNTERMINATED_COMMENT",
                    "Comentario SQL nao foi fechado.",
                )
            index += 2
            continue
        if character == "'":
            value, index = _read_single_quoted(sql, index)
            tokens.append(_token("string", value, index - len(value)))
            continue
        if character == '"':
            value, index = _read_double_quoted(sql, index)
            tokens.append(
                _token("quoted_identifier", value, index - len(value) - 2)
            )
            continue
        if character.isalpha() or character == "_":
            start = index
            index += 1
            while index < len(sql) and (
                sql[index].isalnum() or sql[index] in {"_", "$"}
            ):
                index += 1
            value = sql[start:index]
            tokens.append(_token("word", value, start))
            continue
        if character.isdigit():
            start = index
            index += 1
            while index < len(sql) and (
                sql[index].isdigit() or sql[index] == "."
            ):
                index += 1
            tokens.append(_token("number", sql[start:index], start))
            continue
        if character in "(),.;*+-/%=<>":
            tokens.append(_token("symbol", character, index))
            index += 1
            continue
        raise SqlAnalysisError(
            "SQL_ANALYSIS_UNSUPPORTED_STRUCTURE",
            f"Token SQL nao suportado: {character}",
        )
    return tokens, comment_count


def _single_statement(tokens: list[SqlToken]) -> list[SqlToken]:
    statements: list[list[SqlToken]] = []
    current: list[SqlToken] = []
    for token in tokens:
        if token["kind"] == "symbol" and token["value"] == ";":
            if current:
                statements.append(current)
                current = []
            continue
        current.append(token)
    if current:
        statements.append(current)
    if len(statements) > 1:
        raise SqlAnalysisError(
            "SQL_ANALYSIS_MULTIPLE_STATEMENTS",
            "SQL contem multiplos statements.",
        )
    return statements[0] if statements else []


def _validate_balanced_parentheses(tokens: list[SqlToken]) -> None:
    depth = 0
    for token in tokens:
        if token["value"] == "(":
            depth += 1
        elif token["value"] == ")":
            depth -= 1
            if depth < 0:
                raise SqlAnalysisError(
                    "SQL_ANALYSIS_UNSUPPORTED_STRUCTURE",
                    "Parenteses SQL nao balanceados.",
                )
    if depth != 0:
        raise SqlAnalysisError(
            "SQL_ANALYSIS_UNSUPPORTED_STRUCTURE",
            "Parenteses SQL nao balanceados.",
        )


def _extract_ctes(tokens: list[SqlToken]) -> list[str]:
    if _first_word(tokens) != "with":
        return []
    ctes: list[str] = []
    index = 1
    if _norm_at(tokens, index) == "recursive":
        index += 1
    while index < len(tokens):
        if not _is_identifier(tokens[index]):
            break
        ctes.append(tokens[index]["normalized"])
        index += 1
        if _norm_at(tokens, index) == "(":
            index = _skip_balanced(tokens, index)
        if _norm_at(tokens, index) != "as":
            break
        index += 1
        if _norm_at(tokens, index) != "(":
            break
        index = _skip_balanced(tokens, index)
        if _norm_at(tokens, index) == ",":
            index += 1
            continue
        break
    return sorted(set(ctes))


def _first_word_after_ctes(tokens: list[SqlToken], ctes: list[str]) -> str | None:
    if not ctes:
        return _first_word(tokens)
    index = 1
    if _norm_at(tokens, index) == "recursive":
        index += 1
    while index < len(tokens):
        if not _is_identifier(tokens[index]):
            break
        index += 1
        if _norm_at(tokens, index) == "(":
            index = _skip_balanced(tokens, index)
        if _norm_at(tokens, index) != "as":
            break
        index += 1
        if _norm_at(tokens, index) != "(":
            break
        index = _skip_balanced(tokens, index)
        if _norm_at(tokens, index) == ",":
            index += 1
            continue
        break
    while index < len(tokens):
        if tokens[index]["kind"] in {"word", "quoted_identifier"}:
            return tokens[index]["normalized"]
        index += 1
    return None


def _extract_objects(
    tokens: list[SqlToken],
    ctes: list[str],
) -> list[SqlObjectReference]:
    objects: list[SqlObjectReference] = []
    cte_names = {name.casefold() for name in ctes}
    index = 0
    while index < len(tokens):
        norm = tokens[index]["normalized"]
        source: Literal["from", "join"] | None = None
        if norm == "from":
            source = "from"
        elif norm == "join":
            source = "join"
        if source is None:
            index += 1
            continue
        index += 1
        while _norm_at(tokens, index) in {"lateral", "only"}:
            index += 1
        position = index
        if _norm_at(tokens, index) == "(":
            end = _matching_paren_index(tokens, index)
            alias = _read_alias(tokens, end + 1)
            if alias:
                objects.append(
                    {
                        "raw": alias[0],
                        "schema": None,
                        "table": alias[0],
                        "alias": alias[0],
                        "source": "subquery",
                        "is_cte": False,
                        "is_function": False,
                        "is_subquery": True,
                        "position": position,
                    }
                )
                index += 1
                continue
            index = end
            continue
        reference, index = _read_name(tokens, index)
        if not reference:
            continue
        is_function = _norm_at(tokens, index) == "("
        if is_function:
            index = _skip_balanced(tokens, index)
        schema, table = _schema_table(reference)
        alias = _read_alias(tokens, index)
        if alias:
            index = alias[1]
        is_cte = table.casefold() in cte_names and schema is None
        objects.append(
            {
                "raw": ".".join(reference),
                "schema": schema,
                "table": table,
                "alias": alias[0] if alias else None,
                "source": "cte" if is_cte else ("function" if is_function else source),
                "is_cte": is_cte,
                "is_function": is_function,
                "is_subquery": False,
                "position": position,
            }
        )
    return _stable_objects(objects)


def _extract_columns(
    tokens: list[SqlToken],
    objects: list[SqlObjectReference],
    cte_output_columns: Mapping[str, list[str]] | None = None,
) -> list[SqlColumnReference]:
    columns: list[SqlColumnReference] = []
    cte_outputs = {
        name.casefold(): {column.casefold() for column in output_columns}
        for name, output_columns in (cte_output_columns or {}).items()
    }
    cte_qualifiers = _cte_qualifiers(objects)
    expression_aliases = set(_extract_expression_aliases(tokens))
    table_aliases = {
        alias.casefold()
        for alias in (
            item.get("alias") for item in objects if item.get("alias")
        )
        if alias
    }
    table_names = {
        str(item.get("table", "")).casefold()
        for item in objects
        if not item.get("is_cte")
    }
    relation_identifiers = (
        table_aliases
        | table_names
        | set(cte_outputs)
        | set(cte_qualifiers)
        | set(cte_qualifiers.values())
    )
    index = 0
    current_clause = ""
    while index < len(tokens):
        norm = tokens[index]["normalized"]
        if norm in _CLAUSE_KEYWORDS:
            current_clause = norm
        if norm == "." and index > 0 and index + 1 < len(tokens):
            if _is_table_position(tokens, index - 1):
                index += 1
                continue
            left = tokens[index - 1]
            right = tokens[index + 1]
            if _is_identifier(left) and (
                _is_identifier(right)
                or right["value"] == "*"
            ):
                if index >= 2 and _norm_at(tokens, index - 2) == ".":
                    index += 1
                    continue
                if index + 2 < len(tokens) and _norm_at(tokens, index + 2) == ".":
                    if index + 3 < len(tokens):
                        columns.append(
                            {
                                "raw": (
                                    f"{tokens[index - 1]['value']}."
                                    f"{tokens[index + 1]['value']}."
                                    f"{tokens[index + 3]['value']}"
                                ),
                                "qualifier": tokens[index + 1]["normalized"],
                                "schema": left["normalized"],
                                "table": right["normalized"],
                                "column": tokens[index + 3]["normalized"],
                                "clause": current_clause or "unknown",
                                "is_wildcard": (
                                    tokens[index + 3]["value"] == "*"
                                ),
                            }
                        )
                    index += 1
                    continue
                qualifier = left["normalized"]
                column = right["normalized"]
                if _is_cte_output_reference(
                    qualifier,
                    column,
                    cte_qualifiers,
                    cte_outputs,
                ):
                    index += 1
                    continue
                columns.append(
                    {
                        "raw": f"{left['value']}.{right['value']}",
                        "qualifier": qualifier,
                        "schema": None,
                        "table": qualifier,
                        "column": column,
                        "clause": current_clause or "unknown",
                        "is_wildcard": right["value"] == "*",
                    }
                )
        elif (
            current_clause in {"select", "where", "on", "group", "order", "having"}
            and _is_identifier(tokens[index])
            and norm not in _RESERVED_WORDS
            and not (
                norm in expression_aliases
                and current_clause in {"select", "group", "order"}
            )
            and not _is_table_position(tokens, index)
            and _norm_at(tokens, index + 1) != "("
            and _norm_at(tokens, index - 1) != "."
            and _norm_at(tokens, index + 1) != "."
            and norm not in relation_identifiers
            and not _is_structural_literal_token(tokens, index)
            and not _is_cte_output_reference(
                None,
                norm,
                cte_qualifiers,
                cte_outputs,
            )
        ):
            columns.append(
                {
                    "raw": tokens[index]["value"],
                    "qualifier": None,
                    "schema": None,
                    "table": None,
                    "column": norm,
                    "clause": current_clause,
                    "is_wildcard": False,
                }
            )
        elif (
            current_clause == "select"
            and tokens[index]["kind"] == "symbol"
            and tokens[index]["value"] == "*"
        ):
            columns.append(
                {
                    "raw": "*",
                    "qualifier": None,
                    "schema": None,
                    "table": None,
                    "column": "*",
                    "clause": "select",
                    "is_wildcard": True,
                }
            )
        index += 1
    return _stable_columns(columns)


def _extract_predicates(tokens: list[SqlToken]) -> list[SqlPredicate]:
    """Extract only simple, independently verifiable WHERE predicates."""
    predicates: list[SqlPredicate] = []
    clause_by_depth: dict[int, str] = {}
    depth = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        norm = token["normalized"]
        if token["value"] == "(":
            parent_clause = clause_by_depth.get(depth)
            depth += 1
            if parent_clause:
                clause_by_depth[depth] = parent_clause
            index += 1
            continue
        if token["value"] == ")":
            clause_by_depth.pop(depth, None)
            depth = max(0, depth - 1)
            index += 1
            continue
        if norm in _CLAUSE_KEYWORDS:
            clause_by_depth[depth] = norm
            index += 1
            continue
        if (
            clause_by_depth.get(depth) != "where"
            or not _is_identifier(token)
            or norm in _RESERVED_WORDS
        ):
            index += 1
            continue
        qualifier: str | None = None
        column = norm
        cursor = index + 1
        if _norm_at(tokens, cursor) == "." and cursor + 1 < len(tokens):
            if not _is_identifier(tokens[cursor + 1]):
                index += 1
                continue
            qualifier = norm
            column = tokens[cursor + 1]["normalized"]
            cursor += 2
        if _norm_at(tokens, index - 1) == ".":
            index += 1
            continue
        operator, cursor = _comparison_operator(tokens, cursor)
        if operator is None:
            boundaries = {"", "and", "or", "group", "order", "having", "limit"}
            if _norm_at(tokens, cursor) not in boundaries:
                predicates.append(
                    {
                        "clause": "where",
                        "qualifier": qualifier,
                        "column": column,
                        "operator": None,
                        "literal_type": None,
                        "value": None,
                        "supported": False,
                        "reason": "operator_not_supported",
                    }
                )
            index += 1
            continue
        literal = _predicate_literal(tokens, cursor)
        if literal is None:
            predicates.append({
                "clause": "where", "qualifier": qualifier, "column": column,
                "operator": operator, "literal_type": None, "value": None,
                "supported": False, "reason": "right_operand_not_literal",
            })
            index = cursor + 1
            continue
        literal_type, value, end = literal
        predicates.append({
            "clause": "where", "qualifier": qualifier, "column": column,
            "operator": operator, "literal_type": literal_type, "value": value,
            "supported": True, "reason": "simple_comparison",
        })
        index = end
    if any(token["normalized"] == "or" for token in tokens):
        for predicate in predicates:
            predicate["supported"] = False
            predicate["reason"] = "boolean_or_not_verifiable"
    return predicates


def _comparison_operator(
    tokens: list[SqlToken],
    index: int,
) -> tuple[str | None, int]:
    first, second = _norm_at(tokens, index), _norm_at(tokens, index + 1)
    if first in {"<", ">"} and second == "=":
        return first + second, index + 2
    if first == "<" and second == ">":
        return "<>", index + 2
    if first in {"=", "<", ">"}:
        return first, index + 1
    return None, index


def _predicate_literal(
    tokens: list[SqlToken],
    index: int,
) -> tuple[str, Any, int] | None:
    sign = 1
    if _norm_at(tokens, index) in {"+", "-"}:
        sign = -1 if _norm_at(tokens, index) == "-" else 1
        index += 1
    if index >= len(tokens):
        return None
    token = tokens[index]
    if token["kind"] == "string":
        return "string", token["value"][1:-1].replace("''", "'"), index + 1
    if token["kind"] == "number":
        raw = token["value"]
        value: int | float = float(raw) if "." in raw else int(raw)
        return "number", sign * value, index + 1
    if sign != 1:
        return None
    if token["kind"] == "word" and token["normalized"] in {"true", "false"}:
        return "boolean", token["normalized"] == "true", index + 1
    if token["kind"] == "word" and token["normalized"] == "null":
        return "null", None, index + 1
    return None


def _extract_joins(
    tokens: list[SqlToken],
    objects: list[SqlObjectReference],
) -> list[SqlJoinReference]:
    physical = [
        item
        for item in objects
        if not item.get("is_cte") and not item.get("is_function")
    ]
    physical = sorted(physical, key=lambda item: int(item.get("position") or 0))
    joins: list[SqlJoinReference] = []
    previous: SqlObjectReference | None = None
    for item in physical:
        if item.get("source") == "from":
            previous = item
            continue
        if item.get("source") == "join":
            joins.append(
                {
                    "join_type": _join_type_before(tokens, item["table"]),
                    "left_table": (
                        _qualified_or_table(previous) if previous else None
                    ),
                    "right_table": _qualified_or_table(item),
                    "right_alias": item.get("alias"),
                    "condition_columns": _columns_after_join(tokens, item),
                    "join_comparisons": _comparisons_after_join(tokens, item),
                }
            )
            previous = item
    return joins


def _extract_expression_aliases(tokens: list[SqlToken]) -> list[str]:
    aliases: set[str] = set()
    for index, token in enumerate(tokens[:-1]):
        if (
            token["normalized"] == "as"
            and _is_identifier(tokens[index + 1])
            and _clause_before(tokens, index) == "select"
        ):
            aliases.add(tokens[index + 1]["normalized"])
    return sorted(aliases)


def _clause_before(tokens: list[SqlToken], target_index: int) -> str:
    depth = 0
    clauses_by_depth: dict[int, str] = {}
    for index, token in enumerate(tokens):
        if index >= target_index:
            break
        if token["value"] == "(":
            depth += 1
            continue
        if token["value"] == ")":
            depth = max(0, depth - 1)
            continue
        norm = token["normalized"]
        if norm in _CLAUSE_KEYWORDS:
            clauses_by_depth[depth] = norm
    return clauses_by_depth.get(depth, "")


def _extract_functions(tokens: list[SqlToken]) -> list[str]:
    functions: list[str] = []
    for index, token in enumerate(tokens[:-1]):
        if _is_identifier(token) and tokens[index + 1]["normalized"] == "(":
            if token["normalized"] not in {"as", "select", "from", "where"}:
                functions.append(token["normalized"])
    return functions


def _has_select_into(tokens: list[SqlToken]) -> bool:
    if _first_word(tokens) != "select":
        return False
    depth = 0
    for token in tokens:
        if token["value"] == "(":
            depth += 1
        elif token["value"] == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token["normalized"] == "from":
            return False
        elif depth == 0 and token["normalized"] == "into":
            return True
    return False


def _is_table_position(tokens: list[SqlToken], index: int) -> bool:
    previous = _norm_at(tokens, index - 1)
    return previous in {"from", "join", "into", "update"}


def _join_type_before(tokens: list[SqlToken], table_name: str) -> str:
    for index, token in enumerate(tokens):
        if token["normalized"] == table_name.casefold():
            prefix: list[str] = []
            cursor = index - 1
            while cursor >= 0 and tokens[cursor]["normalized"] in _JOIN_PREFIX_WORDS:
                prefix.append(tokens[cursor]["normalized"])
                cursor -= 1
            if prefix:
                return " ".join(reversed(prefix))
    return "join"


def _columns_after_join(
    tokens: list[SqlToken],
    item: SqlObjectReference,
) -> list[SqlColumnReference]:
    clause = _join_on_token_range(tokens, item)
    if clause is None:
        return []
    start, end = clause
    return [
        column
        for column in _extract_columns(tokens[start:end], [], {})
        if column.get("clause") == "unknown"
    ]


def _comparisons_after_join(
    tokens: list[SqlToken],
    item: SqlObjectReference,
) -> list[SqlJoinComparison]:
    clause = _join_on_token_range(tokens, item)
    if clause is None:
        return []
    start, end = clause
    comparisons: list[SqlJoinComparison] = []
    index = start
    while index < end:
        left = _join_operand(tokens, index)
        if left is None:
            index += 1
            continue
        _, _, cursor = left
        operator, cursor = _comparison_operator(tokens, cursor)
        if operator is None:
            index += 1
            continue
        right = _join_operand(tokens, cursor)
        if right is None:
            index += 1
            continue
        right_qualifier, right_column, cursor = right
        left_qualifier, left_column, _ = left
        comparisons.append(
            {
                "left_qualifier": left_qualifier,
                "left_column": left_column,
                "operator": operator,
                "right_qualifier": right_qualifier,
                "right_column": right_column,
            }
        )
        index = cursor
    return comparisons


def _join_on_token_range(
    tokens: list[SqlToken],
    item: SqlObjectReference,
) -> tuple[int, int] | None:
    start = int(item.get("position") or 0)
    depth = 0
    index = start
    on_index: int | None = None
    while index < len(tokens):
        token = tokens[index]
        if token["value"] == "(":
            depth += 1
        elif token["value"] == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and token["normalized"] == "on":
            on_index = index + 1
            break
        elif depth == 0 and index > start and _is_join_clause_boundary(tokens, index):
            return None
        index += 1
    if on_index is None:
        return None
    end = on_index
    depth = 0
    while end < len(tokens):
        token = tokens[end]
        if token["value"] == "(":
            depth += 1
        elif token["value"] == ")":
            depth = max(0, depth - 1)
        elif depth == 0 and _is_join_clause_boundary(tokens, end):
            break
        end += 1
    return on_index, end


def _is_join_clause_boundary(tokens: list[SqlToken], index: int) -> bool:
    norm = tokens[index]["normalized"]
    if norm in {
        "join",
        "where",
        "group",
        "order",
        "having",
        "limit",
        "union",
        "except",
        "intersect",
    }:
        return True
    return norm == "," and _clause_before(tokens, index) in {"from", "on"}


def _join_operand(
    tokens: list[SqlToken],
    index: int,
) -> tuple[str | None, str, int] | None:
    if index >= len(tokens) or not _is_identifier(tokens[index]):
        return None
    if _norm_at(tokens, index + 1) == "." and _is_identifier(tokens[index + 2]):
        return tokens[index]["normalized"], tokens[index + 2]["normalized"], index + 3
    if tokens[index]["normalized"] in _RESERVED_WORDS:
        return None
    return None, tokens[index]["normalized"], index + 1


def _extract_cte_output_columns(
    tokens: list[SqlToken],
) -> dict[str, list[str]]:
    if _first_word(tokens) != "with":
        return {}
    outputs: dict[str, list[str]] = {}
    index = 1
    if _norm_at(tokens, index) == "recursive":
        index += 1
    while index < len(tokens):
        if not _is_identifier(tokens[index]):
            break
        cte_name = tokens[index]["normalized"]
        index += 1
        explicit_columns: list[str] = []
        if _norm_at(tokens, index) == "(":
            end = _matching_paren_index(tokens, index)
            explicit_columns = [
                token["normalized"]
                for token in tokens[index + 1 : end]
                if _is_identifier(token)
            ]
            index = end + 1
        if _norm_at(tokens, index) != "as":
            break
        index += 1
        if _norm_at(tokens, index) != "(":
            break
        body_end = _matching_paren_index(tokens, index)
        body = tokens[index + 1 : body_end]
        outputs[cte_name] = sorted(
            set(explicit_columns or _select_output_columns(body))
        )
        index = body_end + 1
        if _norm_at(tokens, index) == ",":
            index += 1
            continue
        break
    return outputs


def _select_output_columns(tokens: list[SqlToken]) -> list[str]:
    select_index = _top_level_keyword_index(tokens, "select")
    if select_index is None:
        return []
    from_index = _top_level_keyword_index(tokens, "from", start=select_index + 1)
    end = from_index if from_index is not None else len(tokens)
    items = _split_top_level_commas(tokens[select_index + 1 : end])
    output: list[str] = []
    for item in items:
        alias = _select_item_alias(item)
        if alias:
            output.append(alias)
            continue
        name = _select_item_column_name(item)
        if name:
            output.append(name)
    return output


def _extract_query_scopes(tokens: list[SqlToken]) -> list[SqlQueryScope]:
    scopes: list[SqlQueryScope] = []
    cte_bodies = _cte_bodies(tokens)
    cte_names = [cte_name for cte_name, _body in cte_bodies]
    visible_ctes: list[str] = []
    for cte_name, body in cte_bodies:
        scopes.extend(
            _scope_tree(
                body,
                scope_id=f"cte:{cte_name}",
                parent_scope_id="root",
                is_root=False,
                scope_type="cte",
                scope_name=cte_name,
                cte_names=visible_ctes,
            )
        )
        visible_ctes = [*visible_ctes, cte_name]
    root_tokens = _root_query_tokens(tokens)
    scopes.append(
        _scope_from_tokens(
            root_tokens,
            scope_id="root",
            parent_scope_id=None,
            is_root=True,
            scope_type="root",
            scope_name=None,
            cte_names=cte_names,
        )
    )
    for index, body in enumerate(_subquery_bodies(root_tokens), start=1):
        scopes.extend(
            _scope_tree(
                body,
                scope_id=f"subquery:{index}",
                parent_scope_id="root",
                is_root=False,
                scope_type="subquery",
                scope_name=None,
                cte_names=cte_names,
            )
        )
    return _enrich_scope_lineage(scopes)


def _scope_tree(
    tokens: list[SqlToken],
    *,
    scope_id: str,
    parent_scope_id: str,
    is_root: bool,
    scope_type: Literal["cte", "subquery"],
    scope_name: str | None,
    cte_names: list[str],
) -> list[SqlQueryScope]:
    scope = _scope_from_tokens(
        tokens,
        scope_id=scope_id,
        parent_scope_id=parent_scope_id,
        is_root=is_root,
        scope_type=scope_type,
        scope_name=scope_name,
        cte_names=cte_names,
    )
    scopes = [scope]
    for index, body in enumerate(_subquery_bodies(tokens), start=1):
        scopes.extend(
            _scope_tree(
                body,
                scope_id=f"{scope_id}:subquery:{index}",
                parent_scope_id=scope_id,
                is_root=False,
                scope_type="subquery",
                scope_name=None,
                cte_names=cte_names,
            )
        )
    return scopes


def _scope_from_tokens(
    tokens: list[SqlToken],
    *,
    scope_id: str,
    parent_scope_id: str | None,
    is_root: bool,
    scope_type: Literal["root", "cte", "subquery"],
    scope_name: str | None,
    cte_names: list[str],
) -> SqlQueryScope:
    objects = _extract_scope_objects(tokens, cte_names)
    select_items = _extract_select_items(tokens, cte_names=cte_names)
    joins = _extract_scope_joins(tokens, objects)
    group_by_items = _extract_group_by_items(tokens)
    return {
        "scope_id": scope_id,
        "parent_scope_id": parent_scope_id,
        "is_root": is_root,
        "scope_type": scope_type,
        "scope_name": scope_name,
        "physical_tables": _scope_physical_tables(objects),
        "child_scopes": [],
        "object_references": objects,
        "select_items": select_items,
        "group_by_items": group_by_items,
        "order_by_items": _extract_order_by_items(tokens, select_items),
        "has_aggregate": _has_aggregate_function(tokens),
        "has_reducing_aggregate": _has_reducing_aggregate(tokens),
        "joins": joins,
        "output_lineage": [],
        "raw_table_join_count": _raw_table_join_count(joins, objects),
        "aggregated_scope_join_count": 0,
    }


_AGGREGATE_FUNCTIONS = {"avg", "count", "max", "min", "sum"}


def _scope_physical_tables(
    objects: list[SqlObjectReference],
) -> list[str]:
    tables = {
        _qualified_or_table(item)
        for item in objects
        if not item.get("is_cte")
        and not item.get("is_function")
        and not item.get("is_subquery")
    }
    return sorted(table for table in tables if table)


def _extract_group_by_items(tokens: list[SqlToken]) -> list[str]:
    group_index = _top_level_keyword_pair_index(tokens, "group", "by")
    if group_index is None:
        return []
    end = _top_level_clause_end(
        tokens,
        start=group_index + 2,
        stop_words={"having", "order", "limit", "offset", "fetch", "union"},
    )
    return [
        _tokens_expression(item)
        for item in _split_top_level_commas(tokens[group_index + 2 : end])
        if item
    ]


def _has_aggregate_function(tokens: list[SqlToken]) -> bool:
    for item in _top_level_select_items(tokens):
        for index, token in enumerate(item[:-1]):
            if (
                _is_identifier(token)
                and token["normalized"] in _AGGREGATE_FUNCTIONS
                and item[index + 1]["normalized"] == "("
            ):
                return True
    return False


def _has_reducing_aggregate(tokens: list[SqlToken]) -> bool:
    if _extract_group_by_items(tokens):
        return True
    for item in _top_level_select_items(tokens):
        for index, token in enumerate(item[:-1]):
            if not (
                _is_identifier(token)
                and token["normalized"] in _AGGREGATE_FUNCTIONS
                and item[index + 1]["normalized"] == "("
            ):
                continue
            if _aggregate_invocation_is_window(item, index):
                continue
            return True
    return False


def _aggregate_invocation_is_window(
    tokens: list[SqlToken],
    function_index: int,
) -> bool:
    end = _matching_paren_index(tokens, function_index + 1)
    next_index = end + 1
    if _norm_at(tokens, next_index) == "filter" and _norm_at(tokens, next_index + 1) == "(":
        next_index = _matching_paren_index(tokens, next_index + 1) + 1
    return _norm_at(tokens, next_index) == "over"


def _top_level_select_items(tokens: list[SqlToken]) -> list[list[SqlToken]]:
    select_index = _top_level_keyword_index(tokens, "select")
    if select_index is None:
        return []
    from_index = _top_level_keyword_index(tokens, "from", start=select_index + 1)
    end = from_index if from_index is not None else len(tokens)
    return _split_top_level_commas(tokens[select_index + 1 : end])


def _raw_table_join_count(
    joins: list[SqlJoinReference],
    objects: list[SqlObjectReference],
) -> int:
    physical_refs = _physical_reference_names(objects)
    total = 0
    for join in joins:
        left = str(join.get("left_table") or "").casefold()
        right = str(join.get("right_table") or "").casefold()
        if left in physical_refs and right in physical_refs:
            total += 1
    return total


def _extract_scope_joins(
    tokens: list[SqlToken],
    objects: list[SqlObjectReference],
) -> list[SqlJoinReference]:
    relational = [item for item in objects if not item.get("is_function")]
    joins: list[SqlJoinReference] = []
    previous: SqlObjectReference | None = None
    for item in relational:
        if item.get("source") == "from":
            previous = item
            continue
        if item.get("source") == "join":
            joins.append(
                {
                    "join_type": _join_type_before(tokens, item["table"]),
                    "left_table": (
                        _qualified_or_table(previous) if previous else None
                    ),
                    "right_table": _qualified_or_table(item),
                    "right_alias": item.get("alias"),
                    "condition_columns": _columns_after_join(tokens, item),
                }
            )
            previous = item
    return joins


def _enrich_scope_lineage(scopes: list[SqlQueryScope]) -> list[SqlQueryScope]:
    output = [deepcopy(scope) for scope in scopes]
    by_id = {scope["scope_id"]: scope for scope in output}
    child_ids: dict[str, list[str]] = {}
    for scope in output:
        parent = scope.get("parent_scope_id")
        if parent:
            child_ids.setdefault(parent, []).append(scope["scope_id"])
    for scope in output:
        scope["child_scopes"] = sorted(child_ids.get(scope["scope_id"], []))

    for scope in output:
        scope_ref_map = _scope_reference_map(scope, by_id)
        scope["output_lineage"] = _scope_output_lineage(scope, scope_ref_map, by_id)
        scope["aggregated_scope_join_count"] = _aggregated_scope_join_count(
            scope,
            scope_ref_map,
            by_id,
        )
    return output


def _physical_reference_names(
    objects: list[SqlObjectReference],
) -> set[str]:
    refs: set[str] = set()
    for item in objects:
        if item.get("is_cte") or item.get("is_function") or item.get("is_subquery"):
            continue
        table = str(item.get("table") or "").casefold()
        qualified = _qualified_or_table(item).casefold()
        alias = str(item.get("alias") or "").casefold()
        if table:
            refs.add(table)
        if qualified:
            refs.add(qualified)
        if alias:
            refs.add(alias)
    return refs


def _scope_reference_map(
    scope: SqlQueryScope,
    by_id: Mapping[str, SqlQueryScope],
) -> dict[str, str]:
    refs: dict[str, str] = {}
    subquery_children = [
        child_id
        for child_id in scope.get("child_scopes", [])
        if by_id[child_id].get("scope_type") == "subquery"
    ]
    subquery_index = 0
    for item in scope.get("object_references", []):
        if item.get("is_cte"):
            scope_id = f"cte:{item.get('table')}"
        elif item.get("is_subquery"):
            if subquery_index >= len(subquery_children):
                continue
            scope_id = subquery_children[subquery_index]
            subquery_index += 1
        else:
            continue
        if scope_id not in by_id:
            continue
        table = str(item.get("table") or "").casefold()
        alias = str(item.get("alias") or "").casefold()
        if table:
            refs[table] = scope_id
        if alias:
            refs[alias] = scope_id
    return refs


def _scope_output_lineage(
    scope: SqlQueryScope,
    scope_ref_map: Mapping[str, str],
    by_id: Mapping[str, SqlQueryScope],
) -> list[dict[str, Any]]:
    lineage: list[dict[str, Any]] = []
    child_outputs = {
        scope_id: _scope_output_names(by_id[scope_id])
        for scope_id in set(scope_ref_map.values())
    }
    for index, item in enumerate(scope.get("select_items", [])):
        output_name = _select_output_name(item)
        for column in item.get("column_references", []):
            qualifier = str(column.get("qualifier") or "").casefold()
            if not qualifier or qualifier not in scope_ref_map:
                continue
            source_scope_id = scope_ref_map[qualifier]
            source_output = str(column.get("column") or "").casefold()
            if source_output not in child_outputs.get(source_scope_id, set()):
                continue
            lineage.append(
                {
                    "select_item_index": index,
                    "output_name": output_name,
                    "source_scope_id": source_scope_id,
                    "source_output": source_output,
                }
            )
    return lineage


def _scope_output_names(scope: SqlQueryScope) -> set[str]:
    return {
        name
        for item in scope.get("select_items", [])
        for name in [_select_output_name(item)]
        if name
    }


def _select_output_name(item: SqlSelectItem) -> str | None:
    alias = item.get("alias")
    if alias:
        return str(alias).casefold()
    expression = str(item.get("expression") or "").casefold()
    if expression and _is_plain_identifier_text(expression):
        return expression
    columns = item.get("column_references", [])
    if len(columns) == 1:
        return str(columns[0].get("column") or "").casefold()
    return None


def _is_plain_identifier_text(value: str) -> bool:
    if not value:
        return False
    first = value[0]
    if not (first == "_" or first.isalpha()):
        return False
    return all(character == "_" or character.isalnum() for character in value)


def _aggregated_scope_join_count(
    scope: SqlQueryScope,
    scope_ref_map: Mapping[str, str],
    by_id: Mapping[str, SqlQueryScope],
) -> int:
    total = 0
    for join in scope.get("joins", []):
        left = str(join.get("left_table") or "").casefold()
        right = str(join.get("right_table") or "").casefold()
        left_scope = scope_ref_map.get(left)
        right_scope = scope_ref_map.get(right)
        if (
            left_scope
            and right_scope
            and by_id[left_scope].get("has_reducing_aggregate") is True
            and by_id[right_scope].get("has_reducing_aggregate") is True
        ):
            total += 1
    return total


def _top_level_keyword_pair_index(
    tokens: list[SqlToken],
    first: str,
    second: str,
) -> int | None:
    depth = 0
    for index, token in enumerate(tokens[:-1]):
        if token["value"] == "(":
            depth += 1
            continue
        if token["value"] == ")":
            depth = max(0, depth - 1)
            continue
        if (
            depth == 0
            and token["normalized"] == first
            and tokens[index + 1]["normalized"] == second
        ):
            return index
    return None


def _top_level_clause_end(
    tokens: list[SqlToken],
    *,
    start: int,
    stop_words: set[str],
) -> int:
    depth = 0
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token["value"] == "(":
            depth += 1
            continue
        if token["value"] == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0 and token["normalized"] in stop_words:
            return index
    return len(tokens)


def _extract_select_items(
    tokens: list[SqlToken],
    *,
    cte_names: list[str] | None = None,
) -> list[SqlSelectItem]:
    select_index = _top_level_keyword_index(tokens, "select")
    if select_index is None:
        return []
    from_index = _top_level_keyword_index(tokens, "from", start=select_index + 1)
    end = from_index if from_index is not None else len(tokens)
    items = _split_top_level_commas(tokens[select_index + 1 : end])
    scope_objects = _extract_scope_objects(tokens, cte_names or _extract_ctes(tokens))
    output: list[SqlSelectItem] = []
    for item in items:
        output.append(
            {
                "expression": _tokens_expression(item),
                "alias": _select_item_alias(item),
                "functions": sorted(set(_extract_functions(item))),
                "column_references": _resolve_scope_column_references(
                    _extract_columns(
                        [_token("word", "select", 0), *item],
                        scope_objects,
                        {},
                    ),
                    scope_objects,
                ),
            }
        )
    return output


def _resolve_scope_column_references(
    columns: list[SqlColumnReference],
    objects: list[SqlObjectReference],
) -> list[SqlColumnReference]:
    physical_objects = [
        item
        for item in objects
        if not item.get("is_cte")
        and not item.get("is_function")
        and not item.get("is_subquery")
    ]
    aliases = {
        str(item.get("alias", "")).casefold(): item
        for item in physical_objects
        if item.get("alias")
    }
    output: list[SqlColumnReference] = []
    for column in columns:
        item = deepcopy(column)
        qualifier = item.get("qualifier")
        if qualifier and qualifier.casefold() in aliases:
            table = aliases[qualifier.casefold()]
            item["schema"] = table.get("schema")
            item["table"] = table.get("table")
        elif not qualifier and len(physical_objects) == 1:
            table = physical_objects[0]
            item["schema"] = table.get("schema")
            item["table"] = table.get("table")
        output.append(item)
    return output


def _extract_scope_objects(
    tokens: list[SqlToken],
    ctes: list[str],
) -> list[SqlObjectReference]:
    objects: list[SqlObjectReference] = []
    cte_names = {name.casefold() for name in ctes}
    depth = 0
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token["value"] == "(":
            depth += 1
            index += 1
            continue
        if token["value"] == ")":
            depth = max(0, depth - 1)
            index += 1
            continue
        if depth != 0:
            index += 1
            continue
        norm = token["normalized"]
        source: Literal["from", "join"] | None = None
        if norm == "from":
            source = "from"
        elif norm == "join":
            source = "join"
        if source is None:
            index += 1
            continue
        index += 1
        while _norm_at(tokens, index) in {"lateral", "only"}:
            index += 1
        if _norm_at(tokens, index) == "(":
            end = _matching_paren_index(tokens, index)
            alias = _read_alias(tokens, end + 1)
            if alias:
                objects.append(
                    {
                        "raw": alias[0],
                        "schema": None,
                        "table": alias[0],
                        "alias": alias[0],
                        "source": source,
                        "is_cte": False,
                        "is_function": False,
                        "is_subquery": True,
                    }
                )
                index = alias[1]
                continue
            index = end + 1
            continue
        reference, index = _read_name(tokens, index)
        if not reference:
            continue
        is_function = _norm_at(tokens, index) == "("
        if is_function:
            index = _skip_balanced(tokens, index)
        schema, table = _schema_table(reference)
        alias = _read_alias(tokens, index)
        if alias:
            index = alias[1]
        is_cte = table.casefold() in cte_names and schema is None
        objects.append(
            {
                "raw": ".".join(reference),
                "schema": schema,
                "table": table,
                "alias": alias[0] if alias else None,
                "source": source,
                "is_cte": is_cte,
                "is_function": is_function,
                "is_subquery": False,
            }
        )
    return _stable_objects(objects)


def _extract_order_by_items(
    tokens: list[SqlToken],
    select_items: list[SqlSelectItem],
) -> list[SqlOrderByItem]:
    order_index = _top_level_order_by_index(tokens)
    if order_index is None:
        return []
    end = _top_level_order_by_end(tokens, start=order_index + 2)
    items = _split_top_level_commas(tokens[order_index + 2 : end])
    aliases = {
        str(item.get("alias")).casefold(): index
        for index, item in enumerate(select_items)
        if item.get("alias")
    }
    output: list[SqlOrderByItem] = []
    for item in items:
        expression_tokens = list(item)
        direction: Literal["asc", "desc"] | None = None
        direction_explicit = False
        nulls: Literal["first", "last"] | None = None
        if (
            len(expression_tokens) >= 2
            and expression_tokens[-2]["normalized"] == "nulls"
            and expression_tokens[-1]["normalized"] in {"first", "last"}
        ):
            nulls = expression_tokens[-1]["normalized"]  # type: ignore[assignment]
            expression_tokens = expression_tokens[:-2]
        if expression_tokens and expression_tokens[-1]["normalized"] in {
            "asc",
            "desc",
        }:
            direction = expression_tokens[-1]["normalized"]  # type: ignore[assignment]
            direction_explicit = True
            expression_tokens = expression_tokens[:-1]
        else:
            direction = "asc"
        expression = _tokens_expression(expression_tokens)
        referenced_alias = (
            expression_tokens[0]["normalized"]
            if len(expression_tokens) == 1
            and _is_identifier(expression_tokens[0])
            and expression_tokens[0]["normalized"] in aliases
            else None
        )
        output.append(
            {
                "expression": expression,
                "direction": direction,
                "direction_explicit": direction_explicit,
                "nulls": nulls,
                "referenced_alias": referenced_alias,
                "resolved_select_item_index": (
                    aliases[referenced_alias]
                    if referenced_alias is not None
                    else None
                ),
            }
        )
    return output


def _top_level_order_by_index(tokens: list[SqlToken]) -> int | None:
    depth = 0
    for index, token in enumerate(tokens[:-1]):
        if token["value"] == "(":
            depth += 1
            continue
        if token["value"] == ")":
            depth = max(0, depth - 1)
            continue
        if (
            depth == 0
            and token["normalized"] == "order"
            and tokens[index + 1]["normalized"] == "by"
        ):
            return index
    return None


def _top_level_order_by_end(
    tokens: list[SqlToken],
    *,
    start: int,
) -> int:
    depth = 0
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token["value"] == "(":
            depth += 1
            continue
        if token["value"] == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0 and token["normalized"] in {
            "limit",
            "offset",
            "fetch",
            "union",
        }:
            return index
    return len(tokens)


def _cte_bodies(tokens: list[SqlToken]) -> list[tuple[str, list[SqlToken]]]:
    if _first_word(tokens) != "with":
        return []
    bodies: list[tuple[str, list[SqlToken]]] = []
    index = 1
    if _norm_at(tokens, index) == "recursive":
        index += 1
    while index < len(tokens):
        if not _is_identifier(tokens[index]):
            break
        cte_name = tokens[index]["normalized"]
        index += 1
        if _norm_at(tokens, index) == "(":
            index = _skip_balanced(tokens, index)
        if _norm_at(tokens, index) != "as":
            break
        index += 1
        if _norm_at(tokens, index) != "(":
            break
        body_end = _matching_paren_index(tokens, index)
        bodies.append((cte_name, tokens[index + 1 : body_end]))
        index = body_end + 1
        if _norm_at(tokens, index) == ",":
            index += 1
            continue
        break
    return bodies


def _root_query_tokens(tokens: list[SqlToken]) -> list[SqlToken]:
    if _first_word(tokens) != "with":
        return tokens
    index = 1
    if _norm_at(tokens, index) == "recursive":
        index += 1
    while index < len(tokens):
        if not _is_identifier(tokens[index]):
            break
        index += 1
        if _norm_at(tokens, index) == "(":
            index = _skip_balanced(tokens, index)
        if _norm_at(tokens, index) != "as":
            break
        index += 1
        if _norm_at(tokens, index) != "(":
            break
        index = _skip_balanced(tokens, index)
        if _norm_at(tokens, index) == ",":
            index += 1
            continue
        break
    return tokens[index:]


def _subquery_bodies(tokens: list[SqlToken]) -> list[list[SqlToken]]:
    bodies: list[list[SqlToken]] = []
    index = 0
    while index < len(tokens):
        if _norm_at(tokens, index) != "(":
            index += 1
            continue
        end = _matching_paren_index(tokens, index)
        body = tokens[index + 1 : end]
        if _first_word(body) in {"select", "with"}:
            bodies.append(body)
        index = end + 1
    return bodies


def _tokens_expression(tokens: list[SqlToken]) -> str:
    output: list[str] = []
    for token in tokens:
        value = "<string>" if token["kind"] == "string" else token["value"]
        if value == "." and output:
            output[-1] += "."
            continue
        if output and output[-1].endswith("."):
            output[-1] += value
            continue
        output.append(value)
    return " ".join(output).strip()


def _select_item_alias(tokens: list[SqlToken]) -> str | None:
    for index, token in enumerate(tokens[:-1]):
        if token["normalized"] == "as" and _is_identifier(tokens[index + 1]):
            return tokens[index + 1]["normalized"]
    if len(tokens) >= 2 and _is_identifier(tokens[-1]):
        previous = tokens[-2]["normalized"]
        if (
            previous not in {".", ")"}
            and tokens[-1]["normalized"] not in _RESERVED_WORDS
        ):
            return tokens[-1]["normalized"]
    return None


def _select_item_column_name(tokens: list[SqlToken]) -> str | None:
    if not tokens:
        return None
    if len(tokens) >= 3 and _norm_at(tokens, len(tokens) - 2) == ".":
        candidate = tokens[-1]
        if _is_identifier(candidate) or candidate["value"] == "*":
            return candidate["normalized"]
    if len(tokens) == 1 and _is_identifier(tokens[0]):
        norm = tokens[0]["normalized"]
        if norm not in _RESERVED_WORDS:
            return norm
    return None


def _split_top_level_commas(tokens: list[SqlToken]) -> list[list[SqlToken]]:
    output: list[list[SqlToken]] = []
    current: list[SqlToken] = []
    depth = 0
    for token in tokens:
        if token["value"] == "(":
            depth += 1
        elif token["value"] == ")":
            depth = max(0, depth - 1)
        if token["value"] == "," and depth == 0:
            if current:
                output.append(current)
                current = []
            continue
        current.append(token)
    if current:
        output.append(current)
    return output


def _cte_qualifiers(
    objects: list[SqlObjectReference],
) -> dict[str, str]:
    qualifiers: dict[str, str] = {}
    for item in objects:
        if not item.get("is_cte"):
            continue
        table = item.get("table")
        if not table:
            continue
        table_name = str(table).casefold()
        qualifiers[table_name] = table_name
        alias = item.get("alias")
        if alias:
            qualifiers[str(alias).casefold()] = table_name
    return qualifiers


def _is_cte_output_reference(
    qualifier: str | None,
    column: str,
    cte_qualifiers: Mapping[str, str],
    cte_outputs: Mapping[str, set[str]],
) -> bool:
    column_name = column.casefold()
    if qualifier:
        cte_name = cte_qualifiers.get(qualifier.casefold())
        return bool(cte_name and column_name in cte_outputs.get(cte_name, set()))
    matches = [
        cte_name
        for cte_name, output_columns in cte_outputs.items()
        if column_name in output_columns and cte_name in cte_qualifiers.values()
    ]
    return len(matches) == 1


def _top_level_keyword_index(
    tokens: list[SqlToken],
    keyword: str,
    *,
    start: int = 0,
) -> int | None:
    depth = 0
    for index in range(start, len(tokens)):
        token = tokens[index]
        if token["value"] == "(":
            depth += 1
            continue
        if token["value"] == ")":
            depth = max(0, depth - 1)
            continue
        if depth == 0 and token["normalized"] == keyword:
            return index
    return None


def _matching_paren_index(tokens: list[SqlToken], index: int) -> int:
    if _norm_at(tokens, index) != "(":
        return index
    depth = 0
    while index < len(tokens):
        if tokens[index]["value"] == "(":
            depth += 1
        elif tokens[index]["value"] == ")":
            depth -= 1
            if depth == 0:
                return index
        index += 1
    raise SqlAnalysisError(
        "SQL_ANALYSIS_UNSUPPORTED_STRUCTURE",
        "Parenteses SQL nao balanceados.",
    )


def _read_single_quoted(sql: str, index: int) -> tuple[str, int]:
    start = index
    index += 1
    while index < len(sql):
        if sql[index] == "'" and _peek(sql, index + 1) == "'":
            index += 2
            continue
        if sql[index] == "'":
            return sql[start : index + 1], index + 1
        index += 1
    raise SqlAnalysisError(
        "SQL_ANALYSIS_UNTERMINATED_STRING",
        "Literal textual SQL nao foi fechado.",
    )


def _read_double_quoted(sql: str, index: int) -> tuple[str, int]:
    index += 1
    start = index
    value: list[str] = []
    while index < len(sql):
        if sql[index] == '"' and _peek(sql, index + 1) == '"':
            value.append('"')
            index += 2
            continue
        if sql[index] == '"':
            return "".join(value), index + 1
        value.append(sql[index])
        index += 1
    raise SqlAnalysisError(
        "SQL_ANALYSIS_UNTERMINATED_IDENTIFIER",
        "Identificador SQL entre aspas nao foi fechado.",
    )


def _read_name(
    tokens: list[SqlToken],
    index: int,
) -> tuple[list[str], int]:
    parts: list[str] = []
    if index >= len(tokens) or not _is_identifier(tokens[index]):
        return parts, index
    parts.append(tokens[index]["normalized"])
    index += 1
    while (
        index + 1 < len(tokens)
        and _norm_at(tokens, index) == "."
        and _is_identifier(tokens[index + 1])
    ):
        parts.append(tokens[index + 1]["normalized"])
        index += 2
    return parts, index


def _read_alias(
    tokens: list[SqlToken],
    index: int,
) -> tuple[str, int] | None:
    if _norm_at(tokens, index) == "as":
        index += 1
    if index >= len(tokens) or not _is_identifier(tokens[index]):
        return None
    norm = tokens[index]["normalized"]
    if norm in _TABLE_BOUNDARY_KEYWORDS or norm in _RESERVED_WORDS:
        return None
    return norm, index + 1


def _skip_alias(tokens: list[SqlToken], index: int) -> int:
    alias = _read_alias(tokens, index)
    return alias[1] if alias else index


def _skip_balanced(tokens: list[SqlToken], index: int) -> int:
    if _norm_at(tokens, index) != "(":
        return index
    depth = 0
    while index < len(tokens):
        if tokens[index]["value"] == "(":
            depth += 1
        elif tokens[index]["value"] == ")":
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise SqlAnalysisError(
        "SQL_ANALYSIS_UNSUPPORTED_STRUCTURE",
        "Parenteses SQL nao balanceados.",
    )


def _schema_table(parts: list[str]) -> tuple[str | None, str]:
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return None, parts[0]


def _qualified_or_table(item: Mapping[str, Any]) -> str:
    schema = item.get("schema")
    table = item.get("table", "")
    return f"{schema}.{table}" if schema else str(table)


def _stable_objects(
    objects: list[SqlObjectReference],
) -> list[SqlObjectReference]:
    return sorted(
        objects,
        key=lambda item: (
            str(item.get("source", "")),
            str(item.get("schema", "")),
            item.get("table", ""),
            str(item.get("alias", "")),
        ),
    )


def _stable_columns(
    columns: list[SqlColumnReference],
) -> list[SqlColumnReference]:
    seen: set[str] = set()
    output: list[SqlColumnReference] = []
    for column in columns:
        key = _stable_json(column)
        if key in seen:
            continue
        seen.add(key)
        output.append(column)
    return sorted(
        output,
        key=lambda item: (
            item.get("clause", ""),
            str(item.get("schema", "")),
            str(item.get("table", "")),
            str(item.get("qualifier", "")),
            item.get("column", ""),
        ),
    )


def _first_word(tokens: list[SqlToken]) -> str | None:
    for token in tokens:
        if token["kind"] in {"word", "quoted_identifier"}:
            return token["normalized"]
    return None


def _is_identifier(token: SqlToken) -> bool:
    return token["kind"] in {"word", "quoted_identifier"}


def _is_structural_literal_token(tokens: list[SqlToken], index: int) -> bool:
    token = tokens[index]
    norm = token["normalized"]
    if token["kind"] == "string":
        return True
    if token["kind"] != "word" or norm not in _TEMPORAL_PART_WORDS:
        return False
    if _is_interval_unit(tokens, index):
        return True
    return _is_temporal_function_part_argument(tokens, index)


def _is_interval_unit(tokens: list[SqlToken], index: int) -> bool:
    if tokens[index]["normalized"] not in _TEMPORAL_PART_WORDS:
        return False
    previous = index - 1
    if previous >= 0 and tokens[previous]["kind"] == "number":
        previous -= 1
    if previous >= 0 and tokens[previous]["kind"] == "string":
        previous -= 1
    return previous >= 0 and tokens[previous]["normalized"] == "interval"


def _is_temporal_function_part_argument(
    tokens: list[SqlToken],
    index: int,
) -> bool:
    if tokens[index]["normalized"] not in _TEMPORAL_PART_WORDS:
        return False
    if _norm_at(tokens, index - 1) != "(":
        return False
    function_index = index - 2
    return (
        function_index >= 0
        and _is_identifier(tokens[function_index])
        and tokens[function_index]["normalized"] in _TEMPORAL_PART_FUNCTIONS
    )


def _norm_at(tokens: list[SqlToken], index: int) -> str:
    if index < 0 or index >= len(tokens):
        return ""
    return tokens[index]["normalized"]


def _peek(value: str, index: int) -> str:
    return value[index] if index < len(value) else ""


def _token(kind: TokenKind, value: str, position: int) -> SqlToken:
    normalized = (
        value[1:-1].casefold()
        if kind == "string"
        else value.casefold()
    )
    return {
        "kind": kind,
        "value": value,
        "normalized": normalized,
        "position": position,
    }


def _fingerprint(sql: str) -> str:
    return hashlib.sha256(sql.strip().encode("utf-8")).hexdigest()


def _stable_hash(value: Any) -> str:
    return hashlib.sha256(
        _stable_json(value).encode("utf-8")
    ).hexdigest()


def _stable_json(value: Any) -> str:
    return json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
        default=str,
    )
