from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Literal, TypedDict


SQL_ANALYZER_VERSION = "v1.0.0-conservative-sql-analysis"

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
    source: Literal["from", "join", "cte", "function"]
    is_cte: bool
    is_function: bool


class SqlColumnReference(TypedDict, total=False):
    raw: str
    qualifier: str | None
    schema: str | None
    table: str | None
    column: str
    clause: str
    is_wildcard: bool


class SqlJoinReference(TypedDict, total=False):
    join_type: str
    left_table: str | None
    right_table: str | None
    right_alias: str | None
    condition_columns: list[SqlColumnReference]


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
    "left",
    "like",
    "limit",
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
    "when",
    "where",
    "with",
}

_TABLE_BOUNDARY_KEYWORDS = {
    "where",
    "join",
    "left",
    "right",
    "inner",
    "full",
    "cross",
    "outer",
    "on",
    "group",
    "order",
    "having",
    "limit",
    "union",
}

_JOIN_PREFIX_WORDS = {
    "join",
    "left",
    "right",
    "inner",
    "full",
    "cross",
    "outer",
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
    aliases = {
        item["alias"].casefold(): _qualified_or_table(item)
        for item in object_references
        if item.get("alias") and not item.get("is_cte")
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
            if not item.get("is_cte") and not item.get("is_function")
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
        if _norm_at(tokens, index) == "(":
            index += 1
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
            and norm not in table_aliases
            and norm not in table_names
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


def _extract_joins(
    tokens: list[SqlToken],
    objects: list[SqlObjectReference],
) -> list[SqlJoinReference]:
    physical = [
        item
        for item in objects
        if not item.get("is_cte") and not item.get("is_function")
    ]
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
    del item
    return [
        column
        for column in _extract_columns(tokens, [], {})
        if column.get("clause") == "on"
    ]


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
