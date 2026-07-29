from __future__ import annotations

import getpass
import hashlib
import json
import socket
import sys
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import psycopg
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row

from app.adapters.postgres.context_repository import (
    LOAD_SEMANTIC_CONTEXT_SQL,
)
from app.domain.context_normalizer import (
    ContextNormalizationError,
    normalize_context_snapshot,
)
from app.domain.context_validator import validate_context_snapshot
from app.domain.intent_resolver import (
    IntentResolverInputError,
    resolve_intent,
)


DEFAULT_PORT = 5432
DEFAULT_DATABASE = "postgres"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 10
SSL_MODE = "require"
CONFIRM_ACTION = "APLICAR_CLONAGEM_DEFINITIVA"

CATALOG_PATH = (
    Path(__file__).resolve().parent
    / "semantic_context"
    / "intent_catalog_curado_v1.json"
)

TABLE_SPECS: dict[str, dict[str, Any]] = {
    "ai_ducklake_agent_rules": {
        "activation_column": "is_active",
        "columns": (
            "rule_group",
            "rule_name",
            "rule_content",
            "applies_to_intents",
            "validation_hint",
            "severity",
            "is_active",
            "priority",
            "agent_version",
        ),
    },
    "ai_ducklake_entity_aliases": {
        "activation_column": "is_active",
        "columns": (
            "entity_type",
            "user_term",
            "canonical_value",
            "target_table",
            "target_column",
            "sql_filter_hint",
            "business_rule",
            "is_active",
            "priority",
            "agent_version",
        ),
    },
    "ai_ducklake_dre_mapping": {
        "activation_column": "is_active",
        "columns": (
            "dre_code",
            "nivel_1_bi",
            "business_description",
            "sign_convention",
            "category",
            "is_revenue",
            "is_deduction",
            "is_cost",
            "is_opex",
            "is_financial_result",
            "sql_filter_hint",
            "sort_order",
            "is_active",
            "agent_version",
        ),
    },
    "ai_ducklake_sql_patterns": {
        "activation_column": "is_active",
        "columns": (
            "intent_name",
            "pattern_name",
            "business_question_examples",
            "required_tables",
            "required_rules",
            "sql_pattern",
            "notes",
            "is_active",
            "priority",
            "agent_version",
        ),
    },
    "ai_ducklake_table_catalog": {
        "activation_column": "is_allowed",
        "columns": (
            "table_name",
            "schema_name",
            "table_type",
            "description",
            "grain",
            "primary_key",
            "key_columns",
            "metric_columns",
            "date_columns",
            "join_rules",
            "ai_hint",
            "is_allowed",
            "priority",
            "agent_version",
        ),
    },
}


def _required_input(label: str) -> str:
    value = input(f"{label}: ").strip()
    if not value:
        raise ValueError(f"{label} não pode ficar vazio.")
    return value


def _optional_input(label: str) -> str:
    return input(f"{label} (Enter para ignorar): ").strip()


def _hidden_required_input(label: str) -> str:
    value = getpass.getpass(f"{label} (entrada oculta): ").strip()
    if not value:
        raise ValueError(f"{label} não pode ficar vazio.")
    return value


def _positive_integer_input(
    label: str,
    *,
    default: int,
) -> int:
    raw = input(f"{label} (Enter para usar {default}): ").strip()
    if not raw:
        return default

    try:
        value = int(raw)
    except ValueError as error:
        raise ValueError(f"{label} deve ser inteiro.") from error

    if value <= 0:
        raise ValueError(f"{label} deve ser positivo.")

    return value


def _text_input_with_default(
    label: str,
    *,
    default: str,
) -> str:
    raw = input(f"{label} (Enter para usar {default}): ").strip()
    return raw or default


def _connection_preflight(
    *,
    host: str,
    port: int,
    dsn: str,
    connect_timeout_seconds: int,
) -> bool:
    try:
        socket.getaddrinfo(host, port)
        print("DNS: OK")
    except OSError:
        print("DNS: ERRO")
        return False

    try:
        with psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
        ) as connection:
            connection.read_only = True
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1 AS ok")
                row = cursor.fetchone()
                if not row or row.get("ok") != 1:
                    print("CONEXAO_BASICA: ERRO")
                    return False

        print("CONEXAO_BASICA: OK")
        return True

    except psycopg.Error as error:
        print("CONEXAO_BASICA: ERRO")
        print(f"TIPO_TECNICO: {type(error).__name__}")
        print(f"SQLSTATE: {getattr(error, 'sqlstate', None) or '-'}")
        return False


def _load_catalog_file() -> tuple[str, list[dict[str, Any]]]:
    if not CATALOG_PATH.exists():
        raise ValueError(
            "Arquivo de catálogo não encontrado em "
            f"{CATALOG_PATH}."
        )

    try:
        payload = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError(
            "O arquivo de catálogo contém JSON inválido."
        ) from error

    if not isinstance(payload, Mapping):
        raise ValueError("O arquivo de catálogo deve ser um objeto.")

    catalog_version = payload.get("catalog_version")
    definitions = payload.get("definitions")

    if not isinstance(catalog_version, str) or not catalog_version.strip():
        raise ValueError("catalog_version deve ser texto não vazio.")

    if not isinstance(definitions, list) or not definitions:
        raise ValueError("definitions deve ser uma lista não vazia.")

    normalized_definitions: list[dict[str, Any]] = []
    for index, item in enumerate(definitions):
        if not isinstance(item, Mapping):
            raise ValueError(
                f"definitions[{index}] deve ser um objeto."
            )
        normalized_definitions.append(dict(item))

    return catalog_version.strip(), normalized_definitions


def _fetch_count(
    cursor: Any,
    *,
    table_name: str,
    agent_version: str,
) -> dict[str, int]:
    spec = TABLE_SPECS[table_name]
    activation_column = spec["activation_column"]

    cursor.execute(
        f"""
        SELECT
          COUNT(*) AS total,
          COUNT(*) FILTER (
            WHERE COALESCE({activation_column}, TRUE) = TRUE
          ) AS active
        FROM public.{table_name}
        WHERE agent_version = %(agent_version)s
        """,
        {"agent_version": agent_version},
    )
    row = cursor.fetchone()
    if row is None:
        return {"total": 0, "active": 0}

    return {
        "total": int(row.get("total", 0)),
        "active": int(row.get("active", 0)),
    }


def _collect_counts(
    cursor: Any,
    *,
    agent_version: str,
) -> dict[str, dict[str, int]]:
    return {
        table_name: _fetch_count(
            cursor,
            table_name=table_name,
            agent_version=agent_version,
        )
        for table_name in TABLE_SPECS
    }



def _clone_table(
    cursor: Any,
    *,
    table_name: str,
    source_version: str,
    target_version: str,
) -> int:
    columns: Sequence[str] = TABLE_SPECS[table_name]["columns"]
    destination_columns = ", ".join(columns)
    select_expressions = ", ".join(
        "%(target_version)s"
        if column_name == "agent_version"
        else column_name
        for column_name in columns
    )

    cursor.execute(
        f"""
        INSERT INTO public.{table_name}
          ({destination_columns})
        SELECT
          {select_expressions}
        FROM public.{table_name}
        WHERE agent_version = %(source_version)s
        ORDER BY id
        """,
        {
            "source_version": source_version,
            "target_version": target_version,
        },
    )
    return int(cursor.rowcount)


def _insert_catalog_definitions(
    cursor: Any,
    *,
    definitions: list[dict[str, Any]],
    target_version: str,
) -> int:
    inserted = 0

    for index, definition in enumerate(definitions):
        entity_type = definition.get("entity_type")
        user_term = definition.get("user_term")
        canonical_value = definition.get("canonical_value")
        target_table = definition.get("target_table")
        target_column = definition.get("target_column")
        sql_filter_hint = definition.get("sql_filter_hint")
        business_rule = definition.get("business_rule")
        priority = definition.get("priority")

        if entity_type != "intent_definition":
            raise ValueError(
                f"definitions[{index}].entity_type deve ser "
                "intent_definition."
            )
        if not isinstance(user_term, str) or not user_term.strip():
            raise ValueError(
                f"definitions[{index}].user_term deve ser texto."
            )
        if (
            not isinstance(canonical_value, str)
            or not canonical_value.strip()
        ):
            raise ValueError(
                f"definitions[{index}].canonical_value deve ser texto."
            )
        if target_table is not None or target_column is not None:
            raise ValueError(
                f"definitions[{index}] não pode possuir alvo físico."
            )
        if sql_filter_hint is not None:
            raise ValueError(
                f"definitions[{index}] não pode possuir "
                "sql_filter_hint."
            )
        if not isinstance(business_rule, Mapping):
            raise ValueError(
                f"definitions[{index}].business_rule deve ser objeto."
            )
        if not isinstance(priority, int) or isinstance(priority, bool):
            raise ValueError(
                f"definitions[{index}].priority deve ser inteiro."
            )


        cursor.execute(
            """
            INSERT INTO public.ai_ducklake_entity_aliases (
              entity_type,
              user_term,
              canonical_value,
              target_table,
              target_column,
              sql_filter_hint,
              business_rule,
              is_active,
              priority,
              agent_version
            )
            VALUES (
              %(entity_type)s,
              %(user_term)s,
              %(canonical_value)s,
              NULL,
              NULL,
              NULL,
              %(business_rule)s,
              TRUE,
              %(priority)s,
              %(agent_version)s
            )
            """,
            {
                "entity_type": entity_type,
                "user_term": user_term.strip(),
                "canonical_value": canonical_value.strip(),
                "business_rule": json.dumps(
                    business_rule,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                "priority": priority,
                "agent_version": target_version,
            },
        )
        inserted += int(cursor.rowcount)

    return inserted


def _load_target_snapshot(
    cursor: Any,
    *,
    target_version: str,
) -> dict[str, Any]:
    cursor.execute(
        LOAD_SEMANTIC_CONTEXT_SQL,
        {"agent_version": target_version},
    )
    row = cursor.fetchone()

    if row is None:
        raise ValueError(
            "A consulta não retornou snapshot para a versão simulada."
        )

    return dict(row)


def _collect_examples(
    query_patterns: Any,
) -> list[tuple[str, str, str]]:
    if not isinstance(query_patterns, list):
        raise ValueError("query_patterns não é uma lista.")

    examples: list[tuple[str, str, str]] = []
    for pattern in query_patterns:
        if not isinstance(pattern, Mapping):
            continue

        intent_name = str(pattern.get("intent_name") or "").strip()
        pattern_name = str(pattern.get("pattern_name") or "").strip()
        values = pattern.get("business_question_examples")

        if not intent_name or not isinstance(values, list):
            continue

        for value in values:
            if isinstance(value, str) and value.strip():
                examples.append(
                    (intent_name, pattern_name, value.strip())
                )

    return examples


def _candidate_summary(candidate: Any) -> str:
    if not isinstance(candidate, Mapping):
        return "-"

    return (
        f"{candidate.get('intent_name', '-')}="
        f"{candidate.get('score', '-')}"
    )


def _evaluate_examples(
    snapshot: Mapping[str, Any],
) -> tuple[int, int]:
    examples = _collect_examples(snapshot.get("query_patterns"))
    intent_resolution = snapshot.get("intent_resolution")

    if not isinstance(intent_resolution, Mapping):
        raise ValueError("intent_resolution não é um objeto.")

    total = 0
    passed = 0
    by_intent: dict[str, dict[str, int]] = defaultdict(
        lambda: {"total": 0, "passed": 0}
    )
    failures: list[dict[str, Any]] = []

    for expected_intent, pattern_name, question in examples:
        total += 1
        by_intent[expected_intent]["total"] += 1

        result = resolve_intent(question, intent_resolution)
        predicted = result.get("intent")
        applied = result.get("applied") is True
        ok = applied and predicted == expected_intent

        if ok:
            passed += 1
            by_intent[expected_intent]["passed"] += 1
            continue

        failures.append(
            {
                "expected_intent": expected_intent,
                "pattern_name": pattern_name,
                "question": question,
                "applied": applied,
                "predicted_intent": predicted,
                "reason": result.get("reason"),
                "best_candidate": _candidate_summary(
                    result.get("best_candidate")
                ),
                "second_candidate": _candidate_summary(
                    result.get("second_candidate")
                ),
            }
        )

    print()
    print("AVALIACAO_DOS_EXEMPLOS:")
    print(f"- total={total}")
    print(f"- passed={passed}")
    print(f"- failed={total - passed}")
    print(
        f"- coverage={(passed / total * 100) if total else 0:.2f}%"
    )

    print()
    print("COBERTURA_POR_INTENCAO:")
    for intent_name in sorted(by_intent):
        values = by_intent[intent_name]
        print(
            f"- {intent_name}: "
            f"{values['passed']}/{values['total']}"
        )

    print()
    print(f"FALHAS: {len(failures)}")
    for index, failure in enumerate(failures, start=1):
        print(
            f"- {index}: expected={failure['expected_intent']} "
            f"predicted={failure['predicted_intent'] or '-'} "
            f"applied={failure['applied']} "
            f"reason={failure['reason'] or '-'}"
        )
        print(f"  pattern={failure['pattern_name']}")
        print(f"  question={failure['question']}")
        print(
            f"  best={failure['best_candidate']} "
            f"second={failure['second_candidate']}"
        )

    return passed, total


def _evaluate_custom_question(
    snapshot: Mapping[str, Any],
    *,
    question: str,
    expected_intent: str,
) -> bool:
    if not question:
        print()
        print("PERGUNTA_CUSTOMIZADA: IGNORADA")
        return True

    intent_resolution = snapshot.get("intent_resolution")
    if not isinstance(intent_resolution, Mapping):
        raise ValueError("intent_resolution não é um objeto.")

    result = resolve_intent(question, intent_resolution)
    predicted_intent = str(result.get("intent") or "")
    passed = (
        result.get("applied") is True
        and (
            not expected_intent
            or predicted_intent == expected_intent
        )
    )

    print()
    print("PERGUNTA_CUSTOMIZADA:")
    print(f"- applied={result.get('applied')}")
    print(f"- reason={result.get('reason')}")
    print(f"- intent={predicted_intent or '-'}")
    print(f"- expected_intent={expected_intent or '-'}")
    print(f"- passed={passed}")
    print(
        "- best_candidate="
        f"{_candidate_summary(result.get('best_candidate'))}"
    )
    print(
        "- second_candidate="
        f"{_candidate_summary(result.get('second_candidate'))}"
    )

    catalog_diagnostic = result.get("intent_catalog")
    if isinstance(catalog_diagnostic, Mapping):
        print(
            "- catalog_available="
            f"{catalog_diagnostic.get('available')}"
        )
        print(
            "- catalog_used_for_selected_intent="
            f"{catalog_diagnostic.get('used_for_selected_intent')}"
        )

    return passed



def _catalog_sha256() -> str:
    return hashlib.sha256(CATALOG_PATH.read_bytes()).hexdigest()


def _validate_snapshot(
    cursor: Any,
    *,
    target_version: str,
    expected_fingerprint: str,
    question: str,
    expected_intent: str,
    stage_label: str,
) -> tuple[dict[str, Any], bool]:
    raw_snapshot = _load_target_snapshot(
        cursor,
        target_version=target_version,
    )
    snapshot = normalize_context_snapshot(raw_snapshot)
    validation = validate_context_snapshot(snapshot)

    actual_fingerprint = str(snapshot.get("fingerprint") or "")

    print()
    print("=" * 70)
    print(stage_label)
    print("=" * 70)
    print(f"- context_version={snapshot.get('version', '-')}")
    print(f"- context_fingerprint={actual_fingerprint or '-'}")
    print(f"- expected_fingerprint={expected_fingerprint}")
    print(
        "- fingerprint_match="
        f"{actual_fingerprint == expected_fingerprint}"
    )
    print(f"- validation_status={validation['status']}")

    if validation["status"] != "valid":
        for error in validation["errors"]:
            print(
                f"- {error.get('code', 'UNKNOWN')}: "
                f"{error.get('message', '')} "
                f"path={error.get('path', '-')}"
            )
        raise ValueError(
            "O contexto clonado não passou na validação canônica."
        )

    if actual_fingerprint != expected_fingerprint:
        raise ValueError(
            "O fingerprint do contexto difere do dry run aprovado. "
            "A origem ou o catálogo pode ter mudado."
        )

    passed, total = _evaluate_examples(snapshot)
    custom_question_passed = _evaluate_custom_question(
        snapshot,
        question=question,
        expected_intent=expected_intent,
    )

    semantic_passed = (
        total > 0
        and passed == total
        and custom_question_passed
    )

    print(
        f"{stage_label}_RESULT: "
        + ("APPROVED" if semantic_passed else "REVIEW_REQUIRED")
    )

    if not semantic_passed:
        raise ValueError(
            "A validação semântica não foi aprovada."
        )

    return snapshot, semantic_passed


def _verify_persisted_target(
    *,
    dsn: str,
    target_version: str,
    expected_counts: Mapping[str, int],
    expected_fingerprint: str,
    question: str,
    expected_intent: str,
    connect_timeout_seconds: int,
) -> bool:
    with psycopg.connect(
        dsn,
        connect_timeout=connect_timeout_seconds,
        row_factory=dict_row,
    ) as connection:
        connection.read_only = True

        with connection.cursor() as cursor:
            counts = _collect_counts(
                cursor,
                agent_version=target_version,
            )

            print()
            print("=" * 70)
            print("VERIFICACAO_POS_COMMIT")
            print("=" * 70)

            counts_match = True
            for table_name, values in counts.items():
                expected_total = int(expected_counts[table_name])
                match = values["total"] == expected_total
                counts_match = counts_match and match
                print(
                    f"- {table_name}: "
                    f"expected={expected_total} "
                    f"actual={values['total']} "
                    f"active={values['active']} "
                    f"match={match}"
                )

            if not counts_match:
                raise ValueError(
                    "As contagens persistidas não correspondem ao "
                    "resultado pré-commit."
                )

            _validate_snapshot(
                cursor,
                target_version=target_version,
                expected_fingerprint=expected_fingerprint,
                question=question,
                expected_intent=expected_intent,
                stage_label="VALIDACAO_POS_COMMIT",
            )

    return True


def main() -> int:
    print("=" * 70)
    print("POSTGRES CONTEXT VERSION CLONE — DEFINITIVE APPLY")
    print("=" * 70)
    print(
        "ATENÇÃO: este script cria uma nova versão semântica "
        "persistente no PostgreSQL. A versão de origem não será "
        "alterada. Qualquer falha antes do commit executará rollback."
    )
    print()

    connection: psycopg.Connection[dict[str, Any]] | None = None
    committed = False
    precommit_passed = False
    postcommit_passed = False
    expected_counts: dict[str, int] = {}
    target_version = ""
    dsn = ""
    connect_timeout_seconds = DEFAULT_CONNECT_TIMEOUT_SECONDS
    return_code = 0

    try:
        catalog_version, definitions = _load_catalog_file()
        catalog_sha256 = _catalog_sha256()

        host = _required_input("POSTGRES_HOST")
        port = _positive_integer_input(
            "POSTGRES_PORT",
            default=DEFAULT_PORT,
        )
        database = _text_input_with_default(
            "POSTGRES_DATABASE",
            default=DEFAULT_DATABASE,
        )
        user = _required_input("POSTGRES_USER")
        password = _hidden_required_input("POSTGRES_PASSWORD")
        source_version = _required_input("SOURCE_AGENT_VERSION")
        target_version = _required_input("TARGET_AGENT_VERSION")
        expected_fingerprint = _required_input(
            "EXPECTED_CONTEXT_FINGERPRINT"
        )
        connect_timeout_seconds = _positive_integer_input(
            "POSTGRES_CONNECT_TIMEOUT_SECONDS",
            default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        )
        question = _required_input("QUESTION")
        expected_intent = _required_input("EXPECTED_INTENT")
        confirmed_target_version = _required_input(
            "CONFIRM_TARGET_VERSION"
        )
        confirmed_action = _required_input("CONFIRM_ACTION")

        if source_version == target_version:
            raise ValueError(
                "SOURCE_AGENT_VERSION e TARGET_AGENT_VERSION "
                "devem ser diferentes."
            )
        if confirmed_target_version != target_version:
            raise ValueError(
                "CONFIRM_TARGET_VERSION não corresponde à versão "
                "de destino."
            )
        if confirmed_action != CONFIRM_ACTION:
            raise ValueError(
                "CONFIRM_ACTION inválido. A clonagem foi cancelada."
            )
        if len(expected_fingerprint) != 64:
            raise ValueError(
                "EXPECTED_CONTEXT_FINGERPRINT deve possuir "
                "64 caracteres hexadecimais."
            )
        try:
            int(expected_fingerprint, 16)
        except ValueError as error:
            raise ValueError(
                "EXPECTED_CONTEXT_FINGERPRINT deve ser hexadecimal."
            ) from error

        print()
        print("=" * 70)
        print("ARTEFATO_LOCAL")
        print("=" * 70)
        print(f"- catalog_version={catalog_version}")
        print(f"- catalog_definitions={len(definitions)}")
        print(f"- catalog_sha256={catalog_sha256}")
        print(f"- source_version={source_version}")
        print(f"- target_version={target_version}")
        print(f"- expected_fingerprint={expected_fingerprint}")
        print("- confirmation=VALID")

        dsn = make_conninfo(
            host=host,
            port=port,
            dbname=database,
            user=user,
            password=password,
            sslmode=SSL_MODE,
        )

        if not _connection_preflight(
            host=host,
            port=port,
            dsn=dsn,
            connect_timeout_seconds=connect_timeout_seconds,
        ):
            return 3

        connection = psycopg.connect(
            dsn,
            connect_timeout=connect_timeout_seconds,
            row_factory=dict_row,
        )
        connection.autocommit = False

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT pg_advisory_xact_lock(hashtext(%(key)s))",
                {"key": target_version},
            )
            cursor.execute("SET LOCAL lock_timeout = '5s'")
            cursor.execute("SET LOCAL statement_timeout = '120s'")

            source_counts = _collect_counts(
                cursor,
                agent_version=source_version,
            )
            target_before = _collect_counts(
                cursor,
                agent_version=target_version,
            )

            source_total = sum(
                item["total"] for item in source_counts.values()
            )
            target_total_before = sum(
                item["total"] for item in target_before.values()
            )

            print()
            print("=" * 70)
            print("PRECONDICOES")
            print("=" * 70)
            print(f"- source_total_records={source_total}")
            print(
                "- target_total_records_before="
                f"{target_total_before}"
            )
            print(f"- source_version_exists={source_total > 0}")
            print(
                "- target_version_is_empty="
                f"{target_total_before == 0}"
            )

            if source_total == 0:
                raise ValueError(
                    "A versão de origem não possui registros."
                )
            if target_total_before != 0:
                raise ValueError(
                    "A versão de destino não está vazia."
                )

            print()
            print("=" * 70)
            print("CLONAGEM_DEFINITIVA_PRE_COMMIT")
            print("=" * 70)

            for table_name in TABLE_SPECS:
                inserted = _clone_table(
                    cursor,
                    table_name=table_name,
                    source_version=source_version,
                    target_version=target_version,
                )
                print(f"- {table_name}: cloned={inserted}")

            catalog_inserted = _insert_catalog_definitions(
                cursor,
                definitions=definitions,
                target_version=target_version,
            )
            print(
                "- ai_ducklake_entity_aliases: "
                f"catalog_inserted={catalog_inserted}"
            )

            expected_counts = {
                table_name: values["total"]
                for table_name, values in source_counts.items()
            }
            expected_counts["ai_ducklake_entity_aliases"] += (
                len(definitions)
            )

            target_during = _collect_counts(
                cursor,
                agent_version=target_version,
            )

            print()
            print("=" * 70)
            print("CONTAGEM_PRE_COMMIT")
            print("=" * 70)

            counts_match = True
            for table_name, values in target_during.items():
                expected_total = expected_counts[table_name]
                match = values["total"] == expected_total
                counts_match = counts_match and match
                print(
                    f"- {table_name}: "
                    f"expected={expected_total} "
                    f"actual={values['total']} "
                    f"active={values['active']} "
                    f"match={match}"
                )

            if not counts_match:
                raise ValueError(
                    "As contagens pré-commit não correspondem ao "
                    "resultado esperado."
                )

            _validate_snapshot(
                cursor,
                target_version=target_version,
                expected_fingerprint=expected_fingerprint,
                question=question,
                expected_intent=expected_intent,
                stage_label="VALIDACAO_PRE_COMMIT",
            )
            precommit_passed = True

        if not precommit_passed:
            raise ValueError(
                "A validação pré-commit não foi aprovada."
            )

        connection.commit()
        committed = True
        connection.close()
        connection = None

        print()
        print("COMMIT: OK")

        postcommit_passed = _verify_persisted_target(
            dsn=dsn,
            target_version=target_version,
            expected_counts=expected_counts,
            expected_fingerprint=expected_fingerprint,
            question=question,
            expected_intent=expected_intent,
            connect_timeout_seconds=connect_timeout_seconds,
        )

        return_code = 0

    except (
        ContextNormalizationError,
        IntentResolverInputError,
        ValueError,
    ) as error:
        print(f"VALIDACAO: ERRO — {error}")
        return_code = 4

    except psycopg.Error as error:
        print("POSTGRES: ERRO")
        print(f"TIPO_TECNICO: {type(error).__name__}")
        print(f"SQLSTATE: {getattr(error, 'sqlstate', None) or '-'}")
        return_code = 5

    except KeyboardInterrupt:
        print()
        print("APLICACAO: CANCELADA")
        return_code = 130

    except Exception:
        print()
        print(
            "APLICACAO: ERRO INESPERADO. "
            "Detalhes sensíveis foram omitidos."
        )
        return_code = 6

    finally:
        if connection is not None:
            try:
                if not committed:
                    connection.rollback()
                    print()
                    print("ROLLBACK: OK")
            except Exception:
                print()
                print("ROLLBACK: ERRO")
            finally:
                connection.close()

        final_ok = (
            return_code == 0
            and committed
            and precommit_passed
            and postcommit_passed
        )

        print()
        print(
            "FINAL_RESULT: "
            + ("APPROVED" if final_ok else "FAILED")
        )
        print(f"COMMITTED={committed}")
        print(f"PRECOMMIT_VALIDATION={precommit_passed}")
        print(f"POSTCOMMIT_VALIDATION={postcommit_passed}")
        print(
            "PERSISTENT_TARGET_VERSION="
            + (target_version if committed else "NONE")
        )

        if not final_ok and return_code == 0:
            return_code = 7

    return return_code


if __name__ == "__main__":
    sys.exit(main())
