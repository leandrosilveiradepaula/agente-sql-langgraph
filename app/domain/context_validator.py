from __future__ import annotations

import math
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, TypedDict

from app.domain.search_text import normalize_search_text


class ContextValidationIssue(TypedDict):
    """
    Erro ou aviso produzido pela validação do snapshot canônico.
    """

    code: str
    message: str
    path: str
    details: dict[str, Any]


class ContextValidationResult(TypedDict):
    """
    Resultado estruturado da validação do contexto.
    """

    status: Literal["valid", "invalid"]
    errors: list[ContextValidationIssue]
    warnings: list[ContextValidationIssue]


_COLLECTIONS = (
    "rules",
    "entities",
    "dre_mappings",
    "query_patterns",
    "table_catalog",
)

_COUNT_KEYS = {
    "rules": "rules",
    "entities": "entities",
    "dre_mappings": "dre_mappings",
    "query_patterns": "query_patterns",
    "table_catalog": "table_catalog",
}

_FINGERPRINT_PATTERN = re.compile(r"^[0-9a-f]{64}$")

_INTENT_MATCH_MODES = {
    "exact",
    "contains",
    "starts_with",
    "ends_with",
    "all_tokens",
    "any_token",
    "regex",
}

_INTENT_SIGNAL_POLARITIES = {
    "positive",
    "negative",
}

_INTENT_CATALOG_RULE_EFFECTS = {
    "positive_score",
    "negative_score",
    "require",
    "exclude",
}


def validate_context_snapshot(
    snapshot: Mapping[str, Any],
) -> ContextValidationResult:
    """
    Valida invariantes estruturais e referências inequívocas do snapshot.

    Esta etapa não conhece banco de dados, cliente, benchmark ou intenções
    específicas. A identificação canônica de required_rules permanece fora
    deste incremento até que o contrato físico correspondente seja definido.
    """

    errors: list[ContextValidationIssue] = []
    warnings: list[ContextValidationIssue] = []

    if not isinstance(snapshot, Mapping):
        _add_issue(
            errors,
            code="CONTEXT_NOT_MAPPING",
            message="O snapshot deve ser um objeto de chave e valor.",
            path="$",
            details={"received_type": type(snapshot).__name__},
        )
        return {
            "status": "invalid",
            "errors": errors,
            "warnings": warnings,
        }

    _validate_identification(snapshot, errors)
    collections = _validate_collections(snapshot, errors)

    table_index = _validate_table_catalog(
        collections["table_catalog"],
        errors,
    )
    intent_names = _validate_query_patterns(
        collections["query_patterns"],
        table_index,
        errors,
    )
    intent_definitions = _validate_entities(
        collections["entities"],
        intent_names,
        errors,
    )

    _validate_priorities(collections, errors)
    _validate_counts(snapshot, collections, errors)
    _validate_allowed_schemas(
        snapshot,
        collections["table_catalog"],
        errors,
        warnings,
    )
    _validate_component_configs(snapshot, errors)
    _validate_intent_resolution(
        snapshot,
        intent_names,
        intent_definitions,
        errors,
    )

    return {
        "status": "valid" if not errors else "invalid",
        "errors": errors,
        "warnings": warnings,
    }


def _validate_identification(
    snapshot: Mapping[str, Any],
    errors: list[ContextValidationIssue],
) -> None:
    version = snapshot.get("version")
    source = snapshot.get("source")
    fingerprint = snapshot.get("fingerprint")

    if not _is_non_empty_text(version):
        _add_issue(
            errors,
            code="CONTEXT_VERSION_REQUIRED",
            message="version deve ser um texto não vazio.",
            path="version",
            details={"received_value": version},
        )

    if not _is_non_empty_text(source):
        _add_issue(
            errors,
            code="CONTEXT_SOURCE_REQUIRED",
            message="source deve ser um texto não vazio.",
            path="source",
            details={"received_value": source},
        )

    if not isinstance(fingerprint, str) or not _FINGERPRINT_PATTERN.fullmatch(
        fingerprint
    ):
        _add_issue(
            errors,
            code="CONTEXT_FINGERPRINT_INVALID",
            message=(
                "fingerprint deve ser um SHA-256 hexadecimal minúsculo "
                "com 64 caracteres."
            ),
            path="fingerprint",
            details={"received_value": fingerprint},
        )


def _validate_collections(
    snapshot: Mapping[str, Any],
    errors: list[ContextValidationIssue],
) -> dict[str, list[Any]]:
    collections: dict[str, list[Any]] = {}

    for collection_name in _COLLECTIONS:
        value = snapshot.get(collection_name)
        if not isinstance(value, list):
            _add_issue(
                errors,
                code="CONTEXT_COLLECTION_INVALID",
                message=f"{collection_name} deve ser uma lista.",
                path=collection_name,
                details={"received_type": type(value).__name__},
            )
            collections[collection_name] = []
            continue

        collections[collection_name] = value

        for index, item in enumerate(value):
            if not isinstance(item, Mapping):
                _add_issue(
                    errors,
                    code="CONTEXT_RECORD_INVALID",
                    message=(
                        f"Cada item de {collection_name} deve ser um objeto."
                    ),
                    path=f"{collection_name}[{index}]",
                    details={"received_type": type(item).__name__},
                )

    return collections


def _validate_entities(
    entities: list[Any],
    intent_names: set[str],
    errors: list[ContextValidationIssue],
) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}

    for index, entity in enumerate(entities):
        if not isinstance(entity, Mapping):
            continue

        entity_type = entity.get("entity_type")
        if not (
            _is_non_empty_text(entity_type)
            and entity_type.strip().casefold() == "intent_definition"
        ):
            continue

        path = f"entities[{index}]"
        definition_name = entity.get("user_term")
        intent_name = entity.get("canonical_value")

        if not _is_non_empty_text(definition_name):
            _add_issue(
                errors,
                code="INTENT_DEFINITION_NAME_REQUIRED",
                message="user_term deve identificar a definição.",
                path=f"{path}.user_term",
                details={"received_value": definition_name},
            )

        intent_key: str | None = None
        if not _is_non_empty_text(intent_name):
            _add_issue(
                errors,
                code="INTENT_DEFINITION_INTENT_REQUIRED",
                message="canonical_value deve identificar a intenção.",
                path=f"{path}.canonical_value",
                details={"received_value": intent_name},
            )
        else:
            intent_key = intent_name.strip().casefold()
            if intent_key not in intent_names:
                _add_issue(
                    errors,
                    code="INTENT_DEFINITION_UNKNOWN_INTENT",
                    message=(
                        "A definição aponta para uma intenção inexistente "
                        "entre os padrões ativos."
                    ),
                    path=f"{path}.canonical_value",
                    details={"intent_name": intent_name},
                )

            if intent_key in definitions:
                _add_issue(
                    errors,
                    code="INTENT_DEFINITION_DUPLICATE",
                    message=(
                        "Deve existir no máximo uma definição ativa por "
                        "intenção."
                    ),
                    path=path,
                    details={
                        "intent_name": intent_name,
                        "first_occurrence": definitions[intent_key]["path"],
                    },
                )
            else:
                definitions[intent_key] = {
                    "path": path,
                    "definition_name": definition_name,
                    "intent_name": intent_name,
                    "priority": entity.get("priority"),
                    "expected_catalog": None,
                }

        for field_name in ("target_table", "target_column"):
            value = entity.get(field_name)
            if value is not None:
                _add_issue(
                    errors,
                    code="INTENT_DEFINITION_PHYSICAL_TARGET_INVALID",
                    message=(
                        "Definições de intenção não podem apontar para "
                        "tabela ou coluna física."
                    ),
                    path=f"{path}.{field_name}",
                    details={"received_value": value},
                )

        hint = entity.get("sql_filter_hint")
        if isinstance(hint, Mapping) and "resolver" in hint:
            _add_issue(
                errors,
                code="INTENT_DEFINITION_RESOLVER_HINT_FORBIDDEN",
                message=(
                    "intent_definition não pode conter "
                    "sql_filter_hint.resolver."
                ),
                path=f"{path}.sql_filter_hint.resolver",
                details={"received_value": hint.get("resolver")},
            )

        business_rule = entity.get("business_rule")
        if not isinstance(business_rule, Mapping):
            _add_issue(
                errors,
                code="INTENT_DEFINITION_BUSINESS_RULE_INVALID",
                message="business_rule deve ser um objeto.",
                path=f"{path}.business_rule",
                details={
                    "received_type": type(business_rule).__name__,
                },
            )
            continue

        catalog_payload = business_rule.get("intent_catalog")
        if not isinstance(catalog_payload, Mapping):
            _add_issue(
                errors,
                code="INTENT_DEFINITION_CATALOG_PAYLOAD_INVALID",
                message="business_rule.intent_catalog deve ser um objeto.",
                path=f"{path}.business_rule.intent_catalog",
                details={
                    "received_type": type(catalog_payload).__name__,
                },
            )
            continue

        if intent_key is not None and intent_key in definitions:
            definition = definitions[intent_key]
            if definition.get("path") == path:
                definition["expected_catalog"] = {
                    "intent_name": intent_name,
                    "definition_name": definition_name,
                    "semantic_description": catalog_payload.get(
                        "semantic_description"
                    ),
                    "rules": catalog_payload.get("rules"),
                    "priority": entity.get("priority"),
                }

    return definitions


def _validate_table_catalog(
    table_catalog: list[Any],
    errors: list[ContextValidationIssue],
) -> dict[str, Any]:
    if not table_catalog:
        _add_issue(
            errors,
            code="TABLE_CATALOG_EMPTY",
            message="table_catalog deve possuir ao menos uma tabela.",
            path="table_catalog",
            details={},
        )

    full_names: dict[str, str] = {}
    bare_names: dict[str, list[str]] = {}

    for index, item in enumerate(table_catalog):
        if not isinstance(item, Mapping):
            continue

        schema_name = item.get("schema_name")
        table_name = item.get("table_name")
        path = f"table_catalog[{index}]"

        if not _is_non_empty_text(schema_name):
            _add_issue(
                errors,
                code="TABLE_SCHEMA_REQUIRED",
                message="schema_name deve ser um texto não vazio.",
                path=f"{path}.schema_name",
                details={"received_value": schema_name},
            )

        if not _is_non_empty_text(table_name):
            _add_issue(
                errors,
                code="TABLE_NAME_REQUIRED",
                message="table_name deve ser um texto não vazio.",
                path=f"{path}.table_name",
                details={"received_value": table_name},
            )

        if not (
            _is_non_empty_text(schema_name)
            and _is_non_empty_text(table_name)
        ):
            continue

        qualified_name = f"{schema_name.strip()}.{table_name.strip()}"
        qualified_key = qualified_name.casefold()
        bare_key = table_name.strip().casefold()

        if qualified_key in full_names:
            _add_issue(
                errors,
                code="TABLE_CATALOG_DUPLICATE",
                message=(
                    "A combinação schema_name + table_name deve ser única."
                ),
                path=path,
                details={
                    "table": qualified_name,
                    "first_occurrence": full_names[qualified_key],
                },
            )
        else:
            full_names[qualified_key] = path

        bare_names.setdefault(bare_key, []).append(qualified_name)

    return {
        "full_names": set(full_names),
        "bare_names": bare_names,
    }


def _validate_query_patterns(
    query_patterns: list[Any],
    table_index: dict[str, Any],
    errors: list[ContextValidationIssue],
) -> set[str]:
    if not query_patterns:
        _add_issue(
            errors,
            code="QUERY_PATTERNS_EMPTY",
            message="query_patterns deve possuir ao menos um padrão.",
            path="query_patterns",
            details={},
        )

    pattern_keys: dict[str, str] = {}
    intent_names: set[str] = set()

    for index, item in enumerate(query_patterns):
        if not isinstance(item, Mapping):
            continue

        path = f"query_patterns[{index}]"
        intent_name = item.get("intent_name")
        pattern_name = item.get("pattern_name")

        if not _is_non_empty_text(intent_name):
            _add_issue(
                errors,
                code="PATTERN_INTENT_REQUIRED",
                message="intent_name deve ser um texto não vazio.",
                path=f"{path}.intent_name",
                details={"received_value": intent_name},
            )

        if not _is_non_empty_text(pattern_name):
            _add_issue(
                errors,
                code="PATTERN_NAME_REQUIRED",
                message="pattern_name deve ser um texto não vazio.",
                path=f"{path}.pattern_name",
                details={"received_value": pattern_name},
            )

        if _is_non_empty_text(intent_name):
            intent_names.add(intent_name.strip().casefold())

        if (
            _is_non_empty_text(intent_name)
            and _is_non_empty_text(pattern_name)
        ):
            pattern_key = (
                f"{intent_name.strip()}\0{pattern_name.strip()}".casefold()
            )
            if pattern_key in pattern_keys:
                _add_issue(
                    errors,
                    code="QUERY_PATTERN_DUPLICATE",
                    message=(
                        "A combinação intent_name + pattern_name "
                        "deve ser única."
                    ),
                    path=path,
                    details={
                        "intent_name": intent_name,
                        "pattern_name": pattern_name,
                        "first_occurrence": pattern_keys[pattern_key],
                    },
                )
            else:
                pattern_keys[pattern_key] = path

        _validate_required_tables(
            item.get("required_tables"),
            path=f"{path}.required_tables",
            table_index=table_index,
            errors=errors,
        )
        _validate_string_reference_list(
            item.get("required_rules"),
            path=f"{path}.required_rules",
            code="REQUIRED_RULES_INVALID",
            errors=errors,
        )

    return intent_names


def _validate_required_tables(
    value: Any,
    *,
    path: str,
    table_index: dict[str, Any],
    errors: list[ContextValidationIssue],
) -> None:
    if not isinstance(value, list):
        _add_issue(
            errors,
            code="REQUIRED_TABLES_INVALID",
            message="required_tables deve ser uma lista de textos.",
            path=path,
            details={"received_type": type(value).__name__},
        )
        return

    full_names: set[str] = table_index["full_names"]
    bare_names: dict[str, list[str]] = table_index["bare_names"]

    for index, reference in enumerate(value):
        reference_path = f"{path}[{index}]"
        if not _is_non_empty_text(reference):
            _add_issue(
                errors,
                code="REQUIRED_TABLE_REFERENCE_INVALID",
                message="A referência de tabela deve ser um texto não vazio.",
                path=reference_path,
                details={"received_value": reference},
            )
            continue

        normalized_reference = reference.strip().casefold()

        if "." in normalized_reference:
            if normalized_reference not in full_names:
                _add_issue(
                    errors,
                    code="REQUIRED_TABLE_NOT_ALLOWED",
                    message=(
                        "A tabela requerida não existe no catálogo "
                        "autorizado."
                    ),
                    path=reference_path,
                    details={"required_table": reference},
                )
            continue

        candidates = bare_names.get(normalized_reference, [])
        if not candidates:
            _add_issue(
                errors,
                code="REQUIRED_TABLE_NOT_ALLOWED",
                message=(
                    "A tabela requerida não existe no catálogo autorizado."
                ),
                path=reference_path,
                details={"required_table": reference},
            )
        elif len(candidates) > 1:
            _add_issue(
                errors,
                code="REQUIRED_TABLE_AMBIGUOUS",
                message=(
                    "A referência sem schema corresponde a mais de uma "
                    "tabela autorizada."
                ),
                path=reference_path,
                details={
                    "required_table": reference,
                    "candidates": sorted(candidates, key=str.casefold),
                },
            )


def _validate_string_reference_list(
    value: Any,
    *,
    path: str,
    code: str,
    errors: list[ContextValidationIssue],
) -> None:
    if not isinstance(value, list):
        _add_issue(
            errors,
            code=code,
            message=f"{path} deve ser uma lista de textos.",
            path=path,
            details={"received_type": type(value).__name__},
        )
        return

    for index, item in enumerate(value):
        if not _is_non_empty_text(item):
            _add_issue(
                errors,
                code=code,
                message="Cada referência deve ser um texto não vazio.",
                path=f"{path}[{index}]",
                details={"received_value": item},
            )


def _validate_priorities(
    collections: dict[str, list[Any]],
    errors: list[ContextValidationIssue],
) -> None:
    priority_fields = {
        "rules": "priority",
        "entities": "priority",
        "dre_mappings": "sort_order",
        "query_patterns": "priority",
        "table_catalog": "priority",
    }

    for collection_name, field_name in priority_fields.items():
        for index, item in enumerate(collections[collection_name]):
            if not isinstance(item, Mapping) or field_name not in item:
                continue

            value = item.get(field_name)
            if value is None:
                continue

            if not _is_finite_number(value):
                _add_issue(
                    errors,
                    code="CONTEXT_PRIORITY_INVALID",
                    message=(
                        f"{field_name} deve ser numérico, finito e "
                        "não booleano."
                    ),
                    path=f"{collection_name}[{index}].{field_name}",
                    details={"received_value": value},
                )


def _validate_counts(
    snapshot: Mapping[str, Any],
    collections: dict[str, list[Any]],
    errors: list[ContextValidationIssue],
) -> None:
    counts = snapshot.get("counts")
    if not isinstance(counts, Mapping):
        _add_issue(
            errors,
            code="CONTEXT_COUNTS_INVALID",
            message="counts deve ser um objeto.",
            path="counts",
            details={"received_type": type(counts).__name__},
        )
        return

    for count_name, collection_name in _COUNT_KEYS.items():
        value = counts.get(count_name)
        expected = len(collections[collection_name])

        if not _is_non_negative_integer(value):
            _add_issue(
                errors,
                code="CONTEXT_COUNT_INVALID",
                message=(
                    f"counts.{count_name} deve ser um inteiro "
                    "não negativo."
                ),
                path=f"counts.{count_name}",
                details={"received_value": value},
            )
            continue

        if value != expected:
            _add_issue(
                errors,
                code="CONTEXT_COUNT_MISMATCH",
                message=(
                    "A contagem informada não corresponde ao tamanho "
                    "da coleção normalizada."
                ),
                path=f"counts.{count_name}",
                details={
                    "received_count": value,
                    "normalized_count": expected,
                    "collection": collection_name,
                },
            )


def _validate_allowed_schemas(
    snapshot: Mapping[str, Any],
    table_catalog: list[Any],
    errors: list[ContextValidationIssue],
    warnings: list[ContextValidationIssue],
) -> None:
    allowed_schemas = snapshot.get("allowed_schemas")
    if not isinstance(allowed_schemas, list):
        _add_issue(
            errors,
            code="ALLOWED_SCHEMAS_INVALID",
            message="allowed_schemas deve ser uma lista de textos.",
            path="allowed_schemas",
            details={"received_type": type(allowed_schemas).__name__},
        )
        return

    valid_values: list[str] = []
    for index, value in enumerate(allowed_schemas):
        if not _is_non_empty_text(value):
            _add_issue(
                errors,
                code="ALLOWED_SCHEMA_INVALID",
                message="Cada schema autorizado deve ser um texto não vazio.",
                path=f"allowed_schemas[{index}]",
                details={"received_value": value},
            )
            continue
        valid_values.append(value.strip())

    normalized_values = [value.casefold() for value in valid_values]
    if len(normalized_values) != len(set(normalized_values)):
        _add_issue(
            errors,
            code="ALLOWED_SCHEMA_DUPLICATE",
            message="allowed_schemas não pode conter duplicidades.",
            path="allowed_schemas",
            details={"received_value": valid_values},
        )

    expected_schemas = sorted(
        {
            str(item.get("schema_name")).strip()
            for item in table_catalog
            if isinstance(item, Mapping)
            and _is_non_empty_text(item.get("schema_name"))
        },
        key=str.casefold,
    )

    if set(normalized_values) != {
        value.casefold() for value in expected_schemas
    }:
        _add_issue(
            errors,
            code="ALLOWED_SCHEMAS_MISMATCH",
            message=(
                "allowed_schemas deve corresponder aos schemas derivados "
                "de table_catalog."
            ),
            path="allowed_schemas",
            details={
                "received": valid_values,
                "expected": expected_schemas,
            },
        )
    elif valid_values != sorted(valid_values, key=str.casefold):
        _add_issue(
            warnings,
            code="ALLOWED_SCHEMAS_NOT_SORTED",
            message="allowed_schemas deveria possuir ordenação estável.",
            path="allowed_schemas",
            details={"received": valid_values},
        )


def _validate_component_configs(
    snapshot: Mapping[str, Any],
    errors: list[ContextValidationIssue],
) -> None:
    component_configs = snapshot.get("component_configs")
    if not isinstance(component_configs, Mapping):
        _add_issue(
            errors,
            code="COMPONENT_CONFIGS_INVALID",
            message="component_configs deve ser um objeto.",
            path="component_configs",
            details={"received_type": type(component_configs).__name__},
        )
        return

    for component_name, config in component_configs.items():
        if not _is_non_empty_text(component_name):
            _add_issue(
                errors,
                code="COMPONENT_NAME_INVALID",
                message="O nome do componente deve ser um texto não vazio.",
                path="component_configs",
                details={"received_value": component_name},
            )
        if not isinstance(config, Mapping):
            _add_issue(
                errors,
                code="COMPONENT_CONFIG_INVALID",
                message="Cada configuração de componente deve ser um objeto.",
                path=f"component_configs.{component_name}",
                details={"received_type": type(config).__name__},
            )
            continue
        if component_name == "semantic_defaults":
            _validate_semantic_defaults_config(config, errors)


def _validate_intent_resolution(
    snapshot: Mapping[str, Any],
    intent_names: set[str],
    intent_definitions: dict[str, dict[str, Any]],
    errors: list[ContextValidationIssue],
) -> None:
    intent_resolution = snapshot.get("intent_resolution")
    if not isinstance(intent_resolution, Mapping):
        _add_issue(
            errors,
            code="INTENT_RESOLUTION_INVALID",
            message="intent_resolution deve ser um objeto.",
            path="intent_resolution",
            details={"received_type": type(intent_resolution).__name__},
        )
        return

    config = intent_resolution.get("config")
    if not isinstance(config, Mapping):
        _add_issue(
            errors,
            code="INTENT_RESOLUTION_CONFIG_INVALID",
            message="intent_resolution.config deve ser um objeto.",
            path="intent_resolution.config",
            details={"received_type": type(config).__name__},
        )
    else:
        _validate_intent_resolver_config(config, errors)

    signals = intent_resolution.get("signals")
    if not isinstance(signals, list):
        _add_issue(
            errors,
            code="INTENT_SIGNALS_INVALID",
            message="intent_resolution.signals deve ser uma lista.",
            path="intent_resolution.signals",
            details={"received_type": type(signals).__name__},
        )
        return

    for index, signal in enumerate(signals):
        _validate_intent_signal(
            signal,
            index=index,
            intent_names=intent_names,
            errors=errors,
        )

    intent_catalog = intent_resolution.get("intent_catalog")
    if not isinstance(intent_catalog, list):
        _add_issue(
            errors,
            code="INTENT_CATALOG_INVALID",
            message="intent_resolution.intent_catalog deve ser uma lista.",
            path="intent_resolution.intent_catalog",
            details={
                "received_type": type(intent_catalog).__name__,
            },
        )
        return

    catalog_index: dict[str, dict[str, Any]] = {}
    for index, entry in enumerate(intent_catalog):
        intent_key = _validate_intent_catalog_entry(
            entry,
            index=index,
            intent_names=intent_names,
            errors=errors,
        )
        if intent_key is None:
            continue

        path = f"intent_resolution.intent_catalog[{index}]"
        if intent_key in catalog_index:
            _add_issue(
                errors,
                code="INTENT_CATALOG_DUPLICATE",
                message=(
                    "Deve existir no máximo uma entrada de catálogo por "
                    "intenção."
                ),
                path=path,
                details={
                    "intent_name": entry.get("intent_name")
                    if isinstance(entry, Mapping)
                    else None,
                    "first_occurrence": catalog_index[intent_key]["path"],
                },
            )
        else:
            catalog_index[intent_key] = {
                "path": path,
                "definition_name": entry.get("definition_name")
                if isinstance(entry, Mapping)
                else None,
                "entry": entry,
            }

    for intent_key, definition in intent_definitions.items():
        catalog_entry = catalog_index.get(intent_key)
        if catalog_entry is None:
            _add_issue(
                errors,
                code="INTENT_CATALOG_PROJECTION_MISSING",
                message=(
                    "Cada intent_definition deve gerar uma entrada em "
                    "intent_resolution.intent_catalog."
                ),
                path="intent_resolution.intent_catalog",
                details={
                    "definition_path": definition["path"],
                    "intent_name": intent_key,
                },
            )
            continue

        expected_catalog = definition.get("expected_catalog")
        received_catalog = catalog_entry.get("entry")
        if (
            isinstance(expected_catalog, Mapping)
            and isinstance(received_catalog, Mapping)
            and dict(received_catalog) != dict(expected_catalog)
        ):
            _add_issue(
                errors,
                code="INTENT_CATALOG_PROJECTION_MISMATCH",
                message=(
                    "A entrada canônica deve corresponder integralmente "
                    "à entidade intent_definition de origem."
                ),
                path=catalog_entry["path"],
                details={
                    "definition_path": definition["path"],
                },
            )

    for intent_key, catalog_entry in catalog_index.items():
        if intent_key not in intent_definitions:
            _add_issue(
                errors,
                code="INTENT_CATALOG_ORPHAN_ENTRY",
                message=(
                    "Toda entrada do catálogo deve ser derivada de uma "
                    "entidade intent_definition."
                ),
                path=catalog_entry["path"],
                details={"intent_name": intent_key},
            )


def _validate_intent_catalog_entry(
    entry: Any,
    *,
    index: int,
    intent_names: set[str],
    errors: list[ContextValidationIssue],
) -> str | None:
    path = f"intent_resolution.intent_catalog[{index}]"
    if not isinstance(entry, Mapping):
        _add_issue(
            errors,
            code="INTENT_CATALOG_ENTRY_INVALID",
            message="Cada entrada do catálogo deve ser um objeto.",
            path=path,
            details={"received_type": type(entry).__name__},
        )
        return None

    intent_name = entry.get("intent_name")
    intent_key: str | None = None
    if not _is_non_empty_text(intent_name):
        _add_issue(
            errors,
            code="INTENT_CATALOG_INTENT_REQUIRED",
            message="intent_name deve ser um texto não vazio.",
            path=f"{path}.intent_name",
            details={"received_value": intent_name},
        )
    else:
        intent_key = intent_name.strip().casefold()
        if intent_key not in intent_names:
            _add_issue(
                errors,
                code="INTENT_CATALOG_UNKNOWN_INTENT",
                message=(
                    "A entrada aponta para uma intenção inexistente entre "
                    "os padrões ativos."
                ),
                path=f"{path}.intent_name",
                details={"intent_name": intent_name},
            )

    if not _is_non_empty_text(entry.get("definition_name")):
        _add_issue(
            errors,
            code="INTENT_CATALOG_DEFINITION_NAME_REQUIRED",
            message="definition_name deve ser um texto não vazio.",
            path=f"{path}.definition_name",
            details={"received_value": entry.get("definition_name")},
        )

    if not _is_non_empty_text(entry.get("semantic_description")):
        _add_issue(
            errors,
            code="INTENT_CATALOG_DESCRIPTION_REQUIRED",
            message="semantic_description deve ser um texto não vazio.",
            path=f"{path}.semantic_description",
            details={
                "received_value": entry.get("semantic_description"),
            },
        )

    _validate_optional_non_negative_number(
        entry.get("priority"),
        path=f"{path}.priority",
        errors=errors,
        code="INTENT_CATALOG_PRIORITY_INVALID",
    )

    rules = entry.get("rules")
    if not isinstance(rules, list) or not rules:
        _add_issue(
            errors,
            code="INTENT_CATALOG_RULES_INVALID",
            message="rules deve ser uma lista não vazia.",
            path=f"{path}.rules",
            details={"received_type": type(rules).__name__},
        )
        return intent_key

    rule_names: dict[str, str] = {}
    for rule_index, rule in enumerate(rules):
        rule_name = _validate_intent_catalog_rule(
            rule,
            path=f"{path}.rules[{rule_index}]",
            errors=errors,
        )
        if rule_name is None:
            continue

        rule_key = rule_name.casefold()
        rule_path = f"{path}.rules[{rule_index}]"
        if rule_key in rule_names:
            _add_issue(
                errors,
                code="INTENT_CATALOG_RULE_DUPLICATE",
                message="rule_name deve ser único dentro da intenção.",
                path=rule_path,
                details={
                    "rule_name": rule_name,
                    "first_occurrence": rule_names[rule_key],
                },
            )
        else:
            rule_names[rule_key] = rule_path

    return intent_key


def _validate_intent_catalog_rule(
    rule: Any,
    *,
    path: str,
    errors: list[ContextValidationIssue],
) -> str | None:
    if not isinstance(rule, Mapping):
        _add_issue(
            errors,
            code="INTENT_CATALOG_RULE_INVALID",
            message="Cada regra do catálogo deve ser um objeto.",
            path=path,
            details={"received_type": type(rule).__name__},
        )
        return None

    rule_name = rule.get("rule_name")
    normalized_rule_name = (
        rule_name.strip() if _is_non_empty_text(rule_name) else None
    )
    if normalized_rule_name is None:
        _add_issue(
            errors,
            code="INTENT_CATALOG_RULE_NAME_REQUIRED",
            message="rule_name deve ser um texto não vazio.",
            path=f"{path}.rule_name",
            details={"received_value": rule_name},
        )

    effect = rule.get("effect")
    if effect not in _INTENT_CATALOG_RULE_EFFECTS:
        _add_issue(
            errors,
            code="INTENT_CATALOG_RULE_EFFECT_INVALID",
            message="effect não pertence ao contrato suportado.",
            path=f"{path}.effect",
            details={
                "received_value": effect,
                "allowed_values": sorted(_INTENT_CATALOG_RULE_EFFECTS),
            },
        )

    score = rule.get("score")
    if effect in {"positive_score", "negative_score"}:
        if not _is_finite_number(score) or float(score) < 0:
            _add_issue(
                errors,
                code="INTENT_CATALOG_RULE_SCORE_INVALID",
                message=(
                    "Regras de pontuação exigem score numérico, finito "
                    "e não negativo."
                ),
                path=f"{path}.score",
                details={"received_value": score},
            )
    elif effect in {"require", "exclude"} and score is not None:
        _add_issue(
            errors,
            code="INTENT_CATALOG_RULE_SCORE_FORBIDDEN",
            message="Regras require e exclude não podem possuir score.",
            path=f"{path}.score",
            details={"received_value": score},
        )

    _validate_optional_non_negative_number(
        rule.get("priority"),
        path=f"{path}.priority",
        errors=errors,
        code="INTENT_CATALOG_RULE_PRIORITY_INVALID",
    )

    concepts = rule.get("concepts")
    if not isinstance(concepts, list) or not concepts:
        _add_issue(
            errors,
            code="INTENT_CATALOG_CONCEPTS_INVALID",
            message="concepts deve ser uma lista não vazia.",
            path=f"{path}.concepts",
            details={"received_type": type(concepts).__name__},
        )
        return normalized_rule_name

    minimum_concept_matches = rule.get("minimum_concept_matches")
    if (
        not isinstance(minimum_concept_matches, int)
        or isinstance(minimum_concept_matches, bool)
        or minimum_concept_matches <= 0
        or minimum_concept_matches > len(concepts)
    ):
        _add_issue(
            errors,
            code="INTENT_CATALOG_MINIMUM_CONCEPT_MATCHES_INVALID",
            message=(
                "minimum_concept_matches deve ser inteiro positivo e "
                "não superar a quantidade de conceitos."
            ),
            path=f"{path}.minimum_concept_matches",
            details={
                "received_value": minimum_concept_matches,
                "concept_count": len(concepts),
            },
        )

    concept_names: dict[str, str] = {}
    for concept_index, concept in enumerate(concepts):
        concept_name = _validate_intent_catalog_concept(
            concept,
            path=f"{path}.concepts[{concept_index}]",
            errors=errors,
        )
        if concept_name is None:
            continue

        concept_key = concept_name.casefold()
        concept_path = f"{path}.concepts[{concept_index}]"
        if concept_key in concept_names:
            _add_issue(
                errors,
                code="INTENT_CATALOG_CONCEPT_DUPLICATE",
                message="concept_name deve ser único dentro da regra.",
                path=concept_path,
                details={
                    "concept_name": concept_name,
                    "first_occurrence": concept_names[concept_key],
                },
            )
        else:
            concept_names[concept_key] = concept_path

    return normalized_rule_name


def _validate_intent_catalog_concept(
    concept: Any,
    *,
    path: str,
    errors: list[ContextValidationIssue],
) -> str | None:
    if not isinstance(concept, Mapping):
        _add_issue(
            errors,
            code="INTENT_CATALOG_CONCEPT_INVALID",
            message="Cada conceito do catálogo deve ser um objeto.",
            path=path,
            details={"received_type": type(concept).__name__},
        )
        return None

    concept_name = concept.get("concept_name")
    normalized_concept_name = (
        concept_name.strip()
        if _is_non_empty_text(concept_name)
        else None
    )
    if normalized_concept_name is None:
        _add_issue(
            errors,
            code="INTENT_CATALOG_CONCEPT_NAME_REQUIRED",
            message="concept_name deve ser um texto não vazio.",
            path=f"{path}.concept_name",
            details={"received_value": concept_name},
        )

    match_mode = concept.get("match_mode")
    if match_mode not in _INTENT_MATCH_MODES:
        _add_issue(
            errors,
            code="INTENT_CATALOG_MATCH_MODE_INVALID",
            message="match_mode não pertence ao contrato suportado.",
            path=f"{path}.match_mode",
            details={
                "received_value": match_mode,
                "allowed_values": sorted(_INTENT_MATCH_MODES),
            },
        )

    terms = concept.get("terms")
    normalized_terms = concept.get("normalized_terms")
    if not isinstance(terms, list) or not terms:
        _add_issue(
            errors,
            code="INTENT_CATALOG_TERMS_INVALID",
            message="terms deve ser uma lista não vazia de textos.",
            path=f"{path}.terms",
            details={"received_type": type(terms).__name__},
        )
        terms = []

    if not isinstance(normalized_terms, list):
        _add_issue(
            errors,
            code="INTENT_CATALOG_NORMALIZED_TERMS_INVALID",
            message="normalized_terms deve ser uma lista.",
            path=f"{path}.normalized_terms",
            details={
                "received_type": type(normalized_terms).__name__,
            },
        )
        normalized_terms = []

    if len(terms) != len(normalized_terms):
        _add_issue(
            errors,
            code="INTENT_CATALOG_TERM_COUNT_MISMATCH",
            message="terms e normalized_terms devem possuir o mesmo tamanho.",
            path=f"{path}.normalized_terms",
            details={
                "term_count": len(terms),
                "normalized_term_count": len(normalized_terms),
            },
        )

    seen_terms: dict[str, str] = {}
    for term_index, raw_term in enumerate(terms):
        term_path = f"{path}.terms[{term_index}]"
        normalized_term = (
            normalized_terms[term_index]
            if term_index < len(normalized_terms)
            else None
        )
        if not _is_non_empty_text(raw_term):
            _add_issue(
                errors,
                code="INTENT_CATALOG_TERM_INVALID",
                message="Cada termo deve ser um texto não vazio.",
                path=term_path,
                details={"received_value": raw_term},
            )
            continue

        if not _is_non_empty_text(normalized_term):
            _add_issue(
                errors,
                code="INTENT_CATALOG_NORMALIZED_TERM_INVALID",
                message="Cada termo normalizado deve ser texto não vazio.",
                path=f"{path}.normalized_terms[{term_index}]",
                details={"received_value": normalized_term},
            )
            continue

        expected = (
            raw_term.strip()
            if match_mode == "regex"
            else normalize_search_text(raw_term)
        )
        if normalized_term != expected:
            _add_issue(
                errors,
                code="INTENT_CATALOG_TERM_NORMALIZATION_INVALID",
                message=(
                    "normalized_terms deve corresponder à normalização "
                    "canônica de terms."
                ),
                path=f"{path}.normalized_terms[{term_index}]",
                details={
                    "received_value": normalized_term,
                    "expected_value": expected,
                },
            )

        normalized_key = normalized_term.casefold()
        if normalized_key in seen_terms:
            _add_issue(
                errors,
                code="INTENT_CATALOG_TERM_DUPLICATE",
                message=(
                    "Um conceito não pode conter termos duplicados após "
                    "normalização."
                ),
                path=term_path,
                details={
                    "normalized_term": normalized_term,
                    "first_occurrence": seen_terms[normalized_key],
                },
            )
        else:
            seen_terms[normalized_key] = term_path

    minimum_term_matches = concept.get("minimum_term_matches")
    if (
        not isinstance(minimum_term_matches, int)
        or isinstance(minimum_term_matches, bool)
        or minimum_term_matches <= 0
        or minimum_term_matches > len(terms)
    ):
        _add_issue(
            errors,
            code="INTENT_CATALOG_MINIMUM_TERM_MATCHES_INVALID",
            message=(
                "minimum_term_matches deve ser inteiro positivo e não "
                "superar a quantidade de termos."
            ),
            path=f"{path}.minimum_term_matches",
            details={
                "received_value": minimum_term_matches,
                "term_count": len(terms),
            },
        )

    return normalized_concept_name


def _validate_optional_non_negative_number(
    value: Any,
    *,
    path: str,
    errors: list[ContextValidationIssue],
    code: str,
) -> None:
    if value is None:
        return
    if not _is_finite_number(value) or float(value) < 0:
        _add_issue(
            errors,
            code=code,
            message=(
                "O valor deve ser numérico, finito, não booleano, "
                "não negativo, nulo ou ausente."
            ),
            path=path,
            details={"received_value": value},
        )


def _validate_intent_resolver_config(
    config: Mapping[str, Any],
    errors: list[ContextValidationIssue],
) -> None:
    path = "intent_resolution.config"

    component = config.get("component")
    if component != "intent_resolver":
        _add_issue(
            errors,
            code="INTENT_RESOLVER_COMPONENT_INVALID",
            message=(
                "component deve identificar o componente "
                "intent_resolver."
            ),
            path=f"{path}.component",
            details={"received_value": component},
        )

    _validate_required_non_negative_number(
        config,
        field_name="minimum_score",
        path=path,
        errors=errors,
        code="INTENT_RESOLVER_MINIMUM_SCORE_INVALID",
    )
    _validate_required_non_negative_number(
        config,
        field_name="ambiguity_margin",
        path=path,
        errors=errors,
        code="INTENT_RESOLVER_AMBIGUITY_MARGIN_INVALID",
    )
    _validate_required_ratio(
        config,
        field_name="applied_confidence",
        path=path,
        errors=errors,
        code="INTENT_RESOLVER_CONFIDENCE_INVALID",
    )

    fallback = config.get("fallback_to_previous_intent")
    if not isinstance(fallback, bool):
        _add_issue(
            errors,
            code="INTENT_RESOLVER_FALLBACK_FLAG_INVALID",
            message=(
                "fallback_to_previous_intent deve ser booleano."
            ),
            path=f"{path}.fallback_to_previous_intent",
            details={"received_value": fallback},
        )

    token_fallback = config.get("token_fallback")
    if token_fallback is not None:
        _validate_token_fallback_config(
            token_fallback,
            errors,
        )


def _validate_semantic_defaults_config(
    config: Mapping[str, Any],
    errors: list[ContextValidationIssue],
) -> None:
    path = "component_configs.semantic_defaults"

    component = config.get("component")
    if component != "semantic_defaults":
        _add_issue(
            errors,
            code="SEMANTIC_DEFAULTS_COMPONENT_INVALID",
            message=(
                "component deve identificar o componente "
                "semantic_defaults."
            ),
            path=f"{path}.component",
            details={"received_value": component},
        )

    rules = config.get("rules")
    if not isinstance(rules, list):
        _add_issue(
            errors,
            code="SEMANTIC_DEFAULTS_RULES_INVALID",
            message="rules deve ser uma lista.",
            path=f"{path}.rules",
            details={"received_type": type(rules).__name__},
        )
        return

    names: dict[str, str] = {}
    edges: dict[str, set[str]] = {}
    for index, rule in enumerate(rules):
        rule_path = f"{path}.rules[{index}]"
        if not isinstance(rule, Mapping):
            _add_issue(
                errors,
                code="SEMANTIC_DEFAULTS_RULE_INVALID",
                message="Cada regra de default deve ser um objeto.",
                path=rule_path,
                details={"received_type": type(rule).__name__},
            )
            continue

        rule_name = rule.get("rule_name")
        if not _is_non_empty_text(rule_name):
            _add_issue(
                errors,
                code="SEMANTIC_DEFAULT_RULE_NAME_REQUIRED",
                message="rule_name deve ser um texto não vazio.",
                path=f"{rule_path}.rule_name",
                details={"received_value": rule_name},
            )
            normalized_name = f"__invalid_{index}"
        else:
            normalized_name = str(rule_name).strip()
            name_key = normalized_name.casefold()
            if name_key in names:
                _add_issue(
                    errors,
                    code="SEMANTIC_DEFAULT_RULE_DUPLICATE",
                    message="rule_name deve ser único.",
                    path=f"{rule_path}.rule_name",
                    details={
                        "rule_name": normalized_name,
                        "first_occurrence": names[name_key],
                    },
                )
            else:
                names[name_key] = f"{rule_path}.rule_name"

        present = _semantic_default_concepts(
            rule,
            field_name="when_present",
            path=rule_path,
            errors=errors,
            allow_empty=False,
        )
        absent = _semantic_default_concepts(
            rule,
            field_name="when_absent",
            path=rule_path,
            errors=errors,
            allow_empty=True,
        )
        produce = _semantic_default_concepts(
            rule,
            field_name="produce",
            path=rule_path,
            errors=errors,
            allow_empty=False,
        )

        overlap = present & absent
        if overlap:
            _add_issue(
                errors,
                code="SEMANTIC_DEFAULT_PRESENT_ABSENT_CONFLICT",
                message=(
                    "Um conceito não pode aparecer simultaneamente em "
                    "when_present e when_absent."
                ),
                path=rule_path,
                details={"concepts": sorted(overlap)},
            )

        priority = rule.get("priority")
        if (
            not isinstance(priority, int)
            or isinstance(priority, bool)
            or priority < 0
        ):
            _add_issue(
                errors,
                code="SEMANTIC_DEFAULT_PRIORITY_INVALID",
                message="priority deve ser inteiro não negativo.",
                path=f"{rule_path}.priority",
                details={"received_value": priority},
            )

        for produced in produce:
            edges.setdefault(produced, set()).update(present)

    cycle = _semantic_default_cycle(edges)
    if cycle:
        _add_issue(
            errors,
            code="SEMANTIC_DEFAULT_CYCLE",
            message="semantic_defaults não pode conter ciclos.",
            path=f"{path}.rules",
            details={"cycle": cycle},
        )


def _semantic_default_concepts(
    rule: Mapping[str, Any],
    *,
    field_name: str,
    path: str,
    errors: list[ContextValidationIssue],
    allow_empty: bool,
) -> set[str]:
    value = rule.get(field_name)
    if not isinstance(value, list):
        _add_issue(
            errors,
            code=f"SEMANTIC_DEFAULT_{field_name.upper()}_INVALID",
            message=f"{field_name} deve ser uma lista de textos.",
            path=f"{path}.{field_name}",
            details={"received_type": type(value).__name__},
        )
        return set()

    concepts: set[str] = set()
    invalid_values = [
        item for item in value if not _is_non_empty_text(item)
    ]
    if (not allow_empty and not value) or invalid_values:
        _add_issue(
            errors,
            code=f"SEMANTIC_DEFAULT_{field_name.upper()}_INVALID",
            message=f"{field_name} deve conter textos não vazios.",
            path=f"{path}.{field_name}",
            details={
                "received_value": value,
                "invalid_values": invalid_values,
            },
        )
    for item in value:
        if _is_non_empty_text(item):
            concepts.add(str(item).strip().casefold())
    if len(concepts) != len(
        [item for item in value if _is_non_empty_text(item)]
    ):
        _add_issue(
            errors,
            code=f"SEMANTIC_DEFAULT_{field_name.upper()}_DUPLICATE",
            message=f"{field_name} não pode conter conceitos duplicados.",
            path=f"{path}.{field_name}",
            details={"received_value": value},
        )
    return concepts


def _semantic_default_cycle(
    edges: Mapping[str, set[str]],
) -> list[str] | None:
    visiting: set[str] = set()
    visited: set[str] = set()
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        if node in visiting:
            start = stack.index(node)
            return stack[start:] + [node]
        if node in visited:
            return None
        visiting.add(node)
        stack.append(node)
        for dependency in sorted(edges.get(node, set())):
            cycle = visit(dependency)
            if cycle:
                return cycle
        stack.pop()
        visiting.remove(node)
        visited.add(node)
        return None

    for node in sorted(edges):
        cycle = visit(node)
        if cycle:
            return cycle
    return None


def _validate_token_fallback_config(
    config: Any,
    errors: list[ContextValidationIssue],
) -> None:
    path = "intent_resolution.config.token_fallback"

    if not isinstance(config, Mapping):
        _add_issue(
            errors,
            code="INTENT_TOKEN_FALLBACK_INVALID",
            message="token_fallback deve ser um objeto ou nulo.",
            path=path,
            details={"received_type": type(config).__name__},
        )
        return

    enabled = config.get("enabled")
    if not isinstance(enabled, bool):
        _add_issue(
            errors,
            code="INTENT_TOKEN_FALLBACK_ENABLED_INVALID",
            message="token_fallback.enabled deve ser booleano.",
            path=f"{path}.enabled",
            details={"received_value": enabled},
        )
        return

    if not enabled:
        return

    _validate_allowed_text_list(
        config,
        field_name="apply_to_polarities",
        path=path,
        allowed_values=_INTENT_SIGNAL_POLARITIES,
        errors=errors,
        code="INTENT_TOKEN_FALLBACK_POLARITIES_INVALID",
        allow_empty=False,
    )
    _validate_allowed_text_list(
        config,
        field_name="apply_to_match_modes",
        path=path,
        allowed_values=_INTENT_MATCH_MODES,
        errors=errors,
        code="INTENT_TOKEN_FALLBACK_MATCH_MODES_INVALID",
        allow_empty=False,
    )
    _validate_text_list(
        config,
        field_name="ignored_tokens",
        path=path,
        errors=errors,
        code="INTENT_TOKEN_FALLBACK_IGNORED_TOKENS_INVALID",
        allow_empty=True,
    )

    for field_name, code in (
        (
            "minimum_pattern_tokens",
            "INTENT_TOKEN_FALLBACK_MINIMUM_PATTERN_TOKENS_INVALID",
        ),
        (
            "minimum_matched_tokens",
            "INTENT_TOKEN_FALLBACK_MINIMUM_MATCHED_TOKENS_INVALID",
        ),
        (
            "minimum_prefix_length",
            "INTENT_TOKEN_FALLBACK_MINIMUM_PREFIX_LENGTH_INVALID",
        ),
    ):
        _validate_required_positive_integer(
            config,
            field_name=field_name,
            path=path,
            errors=errors,
            code=code,
        )

    _validate_required_non_negative_integer(
        config,
        field_name="maximum_unmatched_pattern_tokens",
        path=path,
        errors=errors,
        code=(
            "INTENT_TOKEN_FALLBACK_MAXIMUM_UNMATCHED_TOKENS_INVALID"
        ),
    )

    for field_name, code in (
        (
            "minimum_pattern_coverage",
            "INTENT_TOKEN_FALLBACK_COVERAGE_INVALID",
        ),
        (
            "minimum_prefix_ratio",
            "INTENT_TOKEN_FALLBACK_PREFIX_RATIO_INVALID",
        ),
    ):
        _validate_required_ratio(
            config,
            field_name=field_name,
            path=path,
            errors=errors,
            code=code,
        )

    allow_prefix = config.get("allow_prefix_equivalence")
    if not isinstance(allow_prefix, bool):
        _add_issue(
            errors,
            code="INTENT_TOKEN_FALLBACK_PREFIX_FLAG_INVALID",
            message=(
                "allow_prefix_equivalence deve ser booleano."
            ),
            path=f"{path}.allow_prefix_equivalence",
            details={"received_value": allow_prefix},
        )


def _validate_intent_signal(
    signal: Any,
    *,
    index: int,
    intent_names: set[str],
    errors: list[ContextValidationIssue],
) -> None:
    path = f"intent_resolution.signals[{index}]"
    if not isinstance(signal, Mapping):
        _add_issue(
            errors,
            code="INTENT_SIGNAL_INVALID",
            message="Cada sinal de intenção deve ser um objeto.",
            path=path,
            details={"received_type": type(signal).__name__},
        )
        return

    intent_name = signal.get("intent_name")
    if not _is_non_empty_text(intent_name):
        _add_issue(
            errors,
            code="INTENT_SIGNAL_NAME_REQUIRED",
            message="intent_name deve ser um texto não vazio.",
            path=f"{path}.intent_name",
            details={"received_value": intent_name},
        )
    elif intent_name.strip().casefold() not in intent_names:
        _add_issue(
            errors,
            code="INTENT_SIGNAL_UNKNOWN_INTENT",
            message=(
                "O sinal aponta para uma intenção inexistente entre "
                "os padrões ativos."
            ),
            path=f"{path}.intent_name",
            details={"intent_name": intent_name},
        )

    for field_name in ("raw_pattern", "normalized_pattern"):
        value = signal.get(field_name)
        if not _is_non_empty_text(value):
            _add_issue(
                errors,
                code="INTENT_SIGNAL_PATTERN_REQUIRED",
                message=f"{field_name} deve ser um texto não vazio.",
                path=f"{path}.{field_name}",
                details={"received_value": value},
            )

    match_mode = signal.get("match_mode")
    if match_mode not in _INTENT_MATCH_MODES:
        _add_issue(
            errors,
            code="INTENT_SIGNAL_MATCH_MODE_INVALID",
            message="match_mode não pertence ao contrato suportado.",
            path=f"{path}.match_mode",
            details={
                "received_value": match_mode,
                "allowed_values": sorted(_INTENT_MATCH_MODES),
            },
        )
    elif (
        match_mode == "regex"
        and signal.get("normalized_pattern")
        != signal.get("raw_pattern")
    ):
        _add_issue(
            errors,
            code="INTENT_SIGNAL_REGEX_PATTERN_CHANGED",
            message=(
                "Padrões regex devem preservar o conteúdo bruto em "
                "normalized_pattern."
            ),
            path=f"{path}.normalized_pattern",
            details={
                "raw_pattern": signal.get("raw_pattern"),
                "normalized_pattern": signal.get(
                    "normalized_pattern"
                ),
            },
        )

    polarity = signal.get("polarity")
    if polarity not in _INTENT_SIGNAL_POLARITIES:
        _add_issue(
            errors,
            code="INTENT_SIGNAL_POLARITY_INVALID",
            message="polarity deve ser positive ou negative.",
            path=f"{path}.polarity",
            details={
                "received_value": polarity,
                "allowed_values": sorted(_INTENT_SIGNAL_POLARITIES),
            },
        )

    score = signal.get("score")
    if not _is_finite_number(score) or float(score) < 0:
        _add_issue(
            errors,
            code="INTENT_SIGNAL_SCORE_INVALID",
            message=(
                "score deve ser numérico, finito, não booleano e "
                "não negativo."
            ),
            path=f"{path}.score",
            details={"received_value": score},
        )

    priority = signal.get("priority")
    if (
        priority is not None
        and (
            not _is_finite_number(priority)
            or float(priority) < 0
        )
    ):
        _add_issue(
            errors,
            code="INTENT_SIGNAL_PRIORITY_INVALID",
            message=(
                "priority deve ser numérico, finito, não negativo, "
                "nulo ou ausente."
            ),
            path=f"{path}.priority",
            details={"received_value": priority},
        )


def _validate_required_non_negative_number(
    config: Mapping[str, Any],
    *,
    field_name: str,
    path: str,
    errors: list[ContextValidationIssue],
    code: str,
) -> None:
    value = config.get(field_name)
    if not _is_finite_number(value) or float(value) < 0:
        _add_issue(
            errors,
            code=code,
            message=(
                f"{field_name} deve ser numérico, finito, "
                "não booleano e não negativo."
            ),
            path=f"{path}.{field_name}",
            details={"received_value": value},
        )


def _validate_required_ratio(
    config: Mapping[str, Any],
    *,
    field_name: str,
    path: str,
    errors: list[ContextValidationIssue],
    code: str,
) -> None:
    value = config.get(field_name)
    if (
        not _is_finite_number(value)
        or float(value) < 0
        or float(value) > 1
    ):
        _add_issue(
            errors,
            code=code,
            message=f"{field_name} deve estar entre 0 e 1.",
            path=f"{path}.{field_name}",
            details={"received_value": value},
        )


def _validate_required_positive_integer(
    config: Mapping[str, Any],
    *,
    field_name: str,
    path: str,
    errors: list[ContextValidationIssue],
    code: str,
) -> None:
    value = config.get(field_name)
    if (
        not isinstance(value, int)
        or isinstance(value, bool)
        or value <= 0
    ):
        _add_issue(
            errors,
            code=code,
            message=f"{field_name} deve ser um inteiro positivo.",
            path=f"{path}.{field_name}",
            details={"received_value": value},
        )


def _validate_required_non_negative_integer(
    config: Mapping[str, Any],
    *,
    field_name: str,
    path: str,
    errors: list[ContextValidationIssue],
    code: str,
) -> None:
    value = config.get(field_name)
    if not _is_non_negative_integer(value):
        _add_issue(
            errors,
            code=code,
            message=(
                f"{field_name} deve ser um inteiro não negativo."
            ),
            path=f"{path}.{field_name}",
            details={"received_value": value},
        )


def _validate_allowed_text_list(
    config: Mapping[str, Any],
    *,
    field_name: str,
    path: str,
    allowed_values: set[str],
    errors: list[ContextValidationIssue],
    code: str,
    allow_empty: bool,
) -> None:
    value = config.get(field_name)
    if not isinstance(value, list):
        _add_issue(
            errors,
            code=code,
            message=f"{field_name} deve ser uma lista.",
            path=f"{path}.{field_name}",
            details={"received_type": type(value).__name__},
        )
        return

    invalid_values = [
        item
        for item in value
        if item not in allowed_values
    ]
    if (not allow_empty and not value) or invalid_values:
        _add_issue(
            errors,
            code=code,
            message=(
                f"{field_name} deve conter somente valores "
                "suportados pelo contrato."
            ),
            path=f"{path}.{field_name}",
            details={
                "received_value": value,
                "invalid_values": invalid_values,
                "allowed_values": sorted(allowed_values),
            },
        )


def _validate_text_list(
    config: Mapping[str, Any],
    *,
    field_name: str,
    path: str,
    errors: list[ContextValidationIssue],
    code: str,
    allow_empty: bool,
) -> None:
    value = config.get(field_name)
    if not isinstance(value, list):
        _add_issue(
            errors,
            code=code,
            message=f"{field_name} deve ser uma lista de textos.",
            path=f"{path}.{field_name}",
            details={"received_type": type(value).__name__},
        )
        return

    invalid_values = [
        item
        for item in value
        if not _is_non_empty_text(item)
    ]
    if (not allow_empty and not value) or invalid_values:
        _add_issue(
            errors,
            code=code,
            message=(
                f"{field_name} deve conter somente textos não vazios."
            ),
            path=f"{path}.{field_name}",
            details={
                "received_value": value,
                "invalid_values": invalid_values,
            },
        )

def _is_non_empty_text(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _is_non_negative_integer(value: Any) -> bool:
    return (
        isinstance(value, int)
        and not isinstance(value, bool)
        and value >= 0
    )


def _is_finite_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if isinstance(value, Decimal):
        return value.is_finite()
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def _add_issue(
    target: list[ContextValidationIssue],
    *,
    code: str,
    message: str,
    path: str,
    details: dict[str, Any],
) -> None:
    target.append(
        {
            "code": code,
            "message": message,
            "path": path,
            "details": details,
        }
    )
