from __future__ import annotations

import math
import re
from collections.abc import Mapping
from decimal import Decimal
from typing import Any, Literal, TypedDict


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


def _validate_intent_resolution(
    snapshot: Mapping[str, Any],
    intent_names: set[str],
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
        path = f"intent_resolution.signals[{index}]"
        if not isinstance(signal, Mapping):
            _add_issue(
                errors,
                code="INTENT_SIGNAL_INVALID",
                message="Cada sinal de intenção deve ser um objeto.",
                path=path,
                details={"received_type": type(signal).__name__},
            )
            continue

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

        score = signal.get("score")
        if not _is_finite_number(score):
            _add_issue(
                errors,
                code="INTENT_SIGNAL_SCORE_INVALID",
                message="score deve ser numérico, finito e não booleano.",
                path=f"{path}.score",
                details={"received_value": score},
            )

        priority = signal.get("priority")
        if priority is not None and not _is_finite_number(priority):
            _add_issue(
                errors,
                code="INTENT_SIGNAL_PRIORITY_INVALID",
                message=(
                    "priority deve ser numérico, finito, nulo ou ausente."
                ),
                path=f"{path}.priority",
                details={"received_value": priority},
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
