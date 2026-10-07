from __future__ import annotations

import getpass
import json
import socket
import sys
from collections import defaultdict
from collections.abc import Mapping
from copy import deepcopy
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
CATALOG_PATH = (
    Path(__file__).resolve().parent
    / "semantic_context"
    / "intent_catalog_curado_v1.json"
)


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
        normalized_definitions.append(deepcopy(dict(item)))

    return catalog_version.strip(), normalized_definitions


def _load_raw_snapshot(
    *,
    dsn: str,
    semantic_agent_version: str,
    connect_timeout_seconds: int,
) -> dict[str, Any]:
    with psycopg.connect(
        dsn,
        connect_timeout=connect_timeout_seconds,
        row_factory=dict_row,
    ) as connection:
        connection.read_only = True
        with connection.cursor() as cursor:
            cursor.execute(
                LOAD_SEMANTIC_CONTEXT_SQL,
                {"agent_version": semantic_agent_version},
            )
            row = cursor.fetchone()

    if row is None:
        raise ValueError(
            "A consulta não retornou snapshot para a versão informada."
        )

    return deepcopy(dict(row))


def _overlay_definitions(
    raw_snapshot: dict[str, Any],
    definitions: list[dict[str, Any]],
) -> dict[str, Any]:
    output = deepcopy(raw_snapshot)

    entities = output.get("entidades")
    if not isinstance(entities, list):
        raise ValueError("A coleção física entidades não é uma lista.")

    existing_definition_keys: set[tuple[str, str, str]] = set()
    for entity in entities:
        if not isinstance(entity, Mapping):
            continue
        if str(entity.get("entity_type") or "").strip().casefold() != (
            "intent_definition"
        ):
            continue
        existing_definition_keys.add(
            (
                str(entity.get("entity_type") or "").strip().casefold(),
                str(entity.get("user_term") or "").strip().casefold(),
                str(entity.get("canonical_value") or "").strip().casefold(),
            )
        )

    for definition in definitions:
        key = (
            str(definition.get("entity_type") or "").strip().casefold(),
            str(definition.get("user_term") or "").strip().casefold(),
            str(definition.get("canonical_value") or "").strip().casefold(),
        )
        if key in existing_definition_keys:
            raise ValueError(
                "A versão selecionada já contém uma definição com a "
                "mesma chave lógica do catálogo local."
            )
        entities.append(deepcopy(definition))
        existing_definition_keys.add(key)

    counts = output.get("context_counts")
    if not isinstance(counts, Mapping):
        raise ValueError("context_counts não é um objeto.")

    updated_counts = deepcopy(dict(counts))
    updated_counts["entidades"] = len(entities)
    output["context_counts"] = updated_counts
    output["entidades"] = entities
    return output


def _catalog_coverage(
    snapshot: Mapping[str, Any],
) -> tuple[set[str], set[str], set[str]]:
    query_patterns = snapshot.get("query_patterns")
    intent_resolution = snapshot.get("intent_resolution")

    pattern_intents: set[str] = set()
    if isinstance(query_patterns, list):
        for pattern in query_patterns:
            if not isinstance(pattern, Mapping):
                continue
            intent_name = str(
                pattern.get("intent_name") or ""
            ).strip()
            if intent_name:
                pattern_intents.add(intent_name)

    catalog_intents: set[str] = set()
    if isinstance(intent_resolution, Mapping):
        raw_catalog = intent_resolution.get("intent_catalog")
        if isinstance(raw_catalog, list):
            for entry in raw_catalog:
                if not isinstance(entry, Mapping):
                    continue
                intent_name = str(
                    entry.get("intent_name") or ""
                ).strip()
                if intent_name:
                    catalog_intents.add(intent_name)

    missing = pattern_intents - catalog_intents
    extra = catalog_intents - pattern_intents
    return pattern_intents, catalog_intents, missing | extra


def _print_catalog_coverage(
    snapshot: Mapping[str, Any],
) -> bool:
    pattern_intents, catalog_intents, _ = _catalog_coverage(snapshot)
    missing = sorted(pattern_intents - catalog_intents)
    extra = sorted(catalog_intents - pattern_intents)

    print()
    print("COBERTURA_DO_CATALOGO_DE_INTENCOES:")
    print(f"- query_pattern_intents={len(pattern_intents)}")
    print(f"- intent_catalog_intents={len(catalog_intents)}")
    print(f"- missing_catalog_definitions={len(missing)}")
    for intent_name in missing:
        print(f"  - {intent_name}")
    print(f"- catalog_without_query_pattern={len(extra)}")
    for intent_name in extra:
        print(f"  - {intent_name}")

    return not missing


def _intent_semantic_inventory(
    snapshot: Mapping[str, Any],
) -> list[dict[str, Any]]:
    """Resume cobertura estrutural por intenção sem expor termos ou exemplos."""

    query_patterns = snapshot.get("query_patterns")
    intent_resolution = snapshot.get("intent_resolution")

    patterns_by_intent: dict[str, int] = defaultdict(int)
    if isinstance(query_patterns, list):
        for pattern in query_patterns:
            if not isinstance(pattern, Mapping):
                continue
            intent_name = str(pattern.get("intent_name") or "").strip()
            if intent_name:
                patterns_by_intent[intent_name] += 1

    catalog_by_intent: dict[str, list[Mapping[str, Any]]] = defaultdict(list)
    if isinstance(intent_resolution, Mapping):
        raw_catalog = intent_resolution.get("intent_catalog")
        if isinstance(raw_catalog, list):
            for entry in raw_catalog:
                if not isinstance(entry, Mapping):
                    continue
                intent_name = str(entry.get("intent_name") or "").strip()
                if intent_name:
                    catalog_by_intent[intent_name].append(entry)

    intent_names = sorted(
        set(patterns_by_intent) | set(catalog_by_intent),
        key=str.casefold,
    )
    inventory: list[dict[str, Any]] = []

    for intent_name in intent_names:
        definitions = catalog_by_intent.get(intent_name, [])
        concept_names: set[str] = set()
        effect_counts: dict[str, int] = defaultdict(int)
        rule_count = 0

        for definition in definitions:
            rules = definition.get("rules")
            if not isinstance(rules, list):
                continue
            for rule in rules:
                if not isinstance(rule, Mapping):
                    continue
                rule_count += 1
                effect = str(rule.get("effect") or "").strip()
                if effect:
                    effect_counts[effect] += 1
                concepts = rule.get("concepts")
                if not isinstance(concepts, list):
                    continue
                for concept in concepts:
                    if not isinstance(concept, Mapping):
                        continue
                    concept_name = str(
                        concept.get("concept_name") or ""
                    ).strip()
                    if concept_name:
                        concept_names.add(concept_name)

        inventory.append(
            {
                "intent_name": intent_name,
                "pattern_count": patterns_by_intent.get(intent_name, 0),
                "definition_count": len(definitions),
                "rule_count": rule_count,
                "concept_names": sorted(concept_names, key=str.casefold),
                "effect_counts": dict(sorted(effect_counts.items())),
            }
        )

    return inventory


def _print_intent_semantic_inventory(
    snapshot: Mapping[str, Any],
) -> None:
    print()
    print("INVENTARIO_SEMANTICO_POR_INTENCAO:")
    for item in _intent_semantic_inventory(snapshot):
        concepts = ",".join(item["concept_names"]) or "-"
        effects = ",".join(
            f"{name}:{count}"
            for name, count in item["effect_counts"].items()
        ) or "-"
        print(
            f"- {item['intent_name']}: "
            f"patterns={item['pattern_count']} "
            f"definitions={item['definition_count']} "
            f"rules={item['rule_count']} "
            f"concepts={concepts} "
            f"effects={effects}"
        )


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
    question: str,
) -> None:
    if not question:
        return

    intent_resolution = snapshot.get("intent_resolution")
    if not isinstance(intent_resolution, Mapping):
        raise ValueError("intent_resolution não é um objeto.")

    result = resolve_intent(question, intent_resolution)

    print()
    print("PERGUNTA_CUSTOMIZADA:")
    print(f"- applied={result.get('applied')}")
    print(f"- reason={result.get('reason')}")
    print(f"- intent={result.get('intent') or '-'}")
    print(
        f"- best_candidate="
        f"{_candidate_summary(result.get('best_candidate'))}"
    )
    print(
        f"- second_candidate="
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


def main() -> int:
    print("=" * 70)
    print("POSTGRES INTENT CATALOG CURATION — READ ONLY")
    print("=" * 70)
    print(
        "O catálogo local será sobreposto apenas em memória. "
        "Nenhum registro será alterado no PostgreSQL."
    )
    print()

    try:
        catalog_version, definitions = _load_catalog_file()

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
        semantic_agent_version = _required_input(
            "SEMANTIC_AGENT_VERSION"
        )
        connect_timeout_seconds = _positive_integer_input(
            "POSTGRES_CONNECT_TIMEOUT_SECONDS",
            default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        )
        custom_question = _optional_input("QUESTION")

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

        raw_snapshot = _load_raw_snapshot(
            dsn=dsn,
            semantic_agent_version=semantic_agent_version,
            connect_timeout_seconds=connect_timeout_seconds,
        )
        overlaid_snapshot = _overlay_definitions(
            raw_snapshot,
            definitions,
        )
        snapshot = normalize_context_snapshot(overlaid_snapshot)
        validation = validate_context_snapshot(snapshot)

        print()
        print("=" * 70)
        print("DIAGNOSTICO")
        print("=" * 70)
        print(f"CATALOG_VERSION: {catalog_version}")
        print(f"LOCAL_DEFINITIONS: {len(definitions)}")
        print(f"CONTEXT_VERSION: {snapshot.get('version', '-')}")
        print(
            f"CONTEXT_FINGERPRINT_SIMULATED: "
            f"{snapshot.get('fingerprint', '-')}"
        )
        print(f"VALIDATION_STATUS: {validation['status']}")

        if validation["status"] != "valid":
            print(f"VALIDATION_ERRORS: {len(validation['errors'])}")
            for error in validation["errors"]:
                print(
                    f"- {error.get('code', 'UNKNOWN')}: "
                    f"{error.get('message', '')} "
                    f"path={error.get('path', '-')}"
                )
            return 4

        catalog_coverage_ok = _print_catalog_coverage(snapshot)
        _print_intent_semantic_inventory(snapshot)
        passed, total = _evaluate_examples(snapshot)
        _evaluate_custom_question(snapshot, custom_question)

        approved = passed == total and catalog_coverage_ok

        print()
        print(
            "CURATION_RESULT: "
            + ("APPROVED" if approved else "REVIEW_REQUIRED")
        )
        print("DIAGNOSTICO_CONCLUIDO: OK")
        return 0 if approved else 5

    except (
        ContextNormalizationError,
        IntentResolverInputError,
        ValueError,
    ) as error:
        print(f"VALIDACAO: ERRO — {error}")
        return 4

    except psycopg.Error as error:
        print("POSTGRES: ERRO")
        print(f"TIPO_TECNICO: {type(error).__name__}")
        print(f"SQLSTATE: {getattr(error, 'sqlstate', None) or '-'}")
        return 4

    except KeyboardInterrupt:
        print()
        print("DIAGNOSTICO: CANCELADO")
        return 130

    except Exception:
        print()
        print(
            "DIAGNOSTICO: ERRO INESPERADO. "
            "Detalhes sensíveis foram omitidos."
        )
        return 6


if __name__ == "__main__":
    sys.exit(main())
