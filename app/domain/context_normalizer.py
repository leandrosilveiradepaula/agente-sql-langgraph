from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from app.domain.context import ContextSnapshot
from app.domain.search_text import normalize_search_text


class ContextNormalizationError(ValueError):
    """
    Falha estrutural ao transformar o contrato físico em snapshot canônico.
    """

    def __init__(self, field_name: str, message: str) -> None:
        self.field_name = field_name
        self.message = message
        super().__init__(f"{field_name}: {message}")


def normalize_context_snapshot(raw_snapshot: Mapping[str, Any]) -> ContextSnapshot:
    """
    Converte o snapshot físico do PostgreSQL/n8n para o contrato canônico.

    Esta função é pura: não acessa banco, variáveis de ambiente ou serviços
    externos e não altera o objeto recebido.
    """

    if not isinstance(raw_snapshot, Mapping):
        raise ContextNormalizationError(
            "snapshot",
            "o valor recebido deve ser um objeto de chave e valor.",
        )

    version = _normalize_text(
        _first_present(raw_snapshot, "semantic_agent_version", "version")
    )
    source = _normalize_text(
        _first_present(raw_snapshot, "semantic_context_source", "source")
    )

    rules = _normalize_rules(
        _first_present(raw_snapshot, "regras", "rules", default=[])
    )
    entities = _normalize_entities(
        _first_present(raw_snapshot, "entidades", "entities", default=[])
    )
    dre_mappings = _normalize_dre_mappings(
        _first_present(raw_snapshot, "dre", "dre_mappings", default=[])
    )
    query_patterns = _normalize_query_patterns(
        _first_present(raw_snapshot, "padroes", "query_patterns", default=[])
    )
    table_catalog = _normalize_table_catalog(
        _first_present(raw_snapshot, "catalogo", "table_catalog", default=[])
    )

    rules.sort(
        key=lambda item: _record_sort_key(
            item,
            "priority",
            "rule_group",
            "rule_name",
        )
    )
    entities.sort(
        key=lambda item: _record_sort_key(
            item,
            "priority",
            "entity_type",
            "user_term",
            "canonical_value",
        )
    )
    dre_mappings.sort(
        key=lambda item: _record_sort_key(
            item,
            "sort_order",
            "dre_code",
            "nivel_1_bi",
        )
    )
    query_patterns.sort(
        key=lambda item: _record_sort_key(
            item,
            "priority",
            "intent_name",
            "pattern_name",
        )
    )
    table_catalog.sort(
        key=lambda item: _record_sort_key(
            item,
            "priority",
            "schema_name",
            "table_name",
        )
    )

    allowed_schemas = sorted(
        {
            schema
            for item in table_catalog
            if (schema := _normalize_text(item.get("schema_name")))
        },
        key=str.casefold,
    )

    component_configs = _derive_component_configs(rules)
    intent_resolution = {
        "config": _derive_intent_resolution_config(
            component_configs.get("intent_resolver", {})
        ),
        "signals": _derive_intent_resolution_signals(entities),
        "intent_catalog": _derive_intent_catalog(entities),
    }

    counts = _normalize_counts(
        _first_present(raw_snapshot, "context_counts", "counts", default={}),
        rules=rules,
        entities=entities,
        dre_mappings=dre_mappings,
        query_patterns=query_patterns,
        table_catalog=table_catalog,
    )

    legacy_versions = _normalize_mapping(
        _first_present(raw_snapshot, "versions", default={}),
        "versions",
    )
    legacy_tables = [
        {
            "schema": item.get("schema_name", ""),
            "name": item.get("table_name", ""),
            "description": item.get("description"),
            "columns": deepcopy(item.get("columns", [])),
        }
        for item in table_catalog
    ]
    legacy_aliases = _derive_legacy_aliases(entities)
    legacy_sql_patterns = deepcopy(query_patterns)

    canonical_without_fingerprint: dict[str, Any] = {
        "version": version,
        "source": source,
        "counts": counts,
        "rules": rules,
        "entities": entities,
        "dre_mappings": dre_mappings,
        "query_patterns": query_patterns,
        "table_catalog": table_catalog,
        "allowed_schemas": allowed_schemas,
        "component_configs": component_configs,
        "intent_resolution": intent_resolution,
    }

    fingerprint = _calculate_fingerprint(canonical_without_fingerprint)

    snapshot: ContextSnapshot = {
        **canonical_without_fingerprint,
        "fingerprint": fingerprint,
        "versions": legacy_versions,
        "tables": legacy_tables,
        "aliases": legacy_aliases,
        "sql_patterns": legacy_sql_patterns,
    }
    return snapshot


def _first_present(
    values: Mapping[str, Any],
    *keys: str,
    default: Any = None,
) -> Any:
    for key in keys:
        if key in values:
            return values[key]
    return default


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    return str(value).strip()


def _normalize_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    return _normalize_text(value)


def _parse_json_like(value: Any, field_name: str) -> Any:
    if not isinstance(value, str):
        return deepcopy(value)

    stripped = value.strip()
    if not stripped:
        return value

    if stripped[0] not in "[{":
        return value

    try:
        return json.loads(stripped)
    except json.JSONDecodeError as exc:
        raise ContextNormalizationError(
            field_name,
            f"contém JSON inválido: {exc.msg}.",
        ) from exc


def _normalize_mapping(value: Any, field_name: str) -> dict[str, Any]:
    parsed = _parse_json_like(value, field_name)
    if parsed is None:
        return {}
    if not isinstance(parsed, Mapping):
        raise ContextNormalizationError(field_name, "deve ser um objeto JSON.")
    return {str(key): deepcopy(item) for key, item in parsed.items()}


def _normalize_record_list(value: Any, field_name: str) -> list[dict[str, Any]]:
    parsed = _parse_json_like(value, field_name)
    if parsed is None:
        return []
    if not isinstance(parsed, list):
        raise ContextNormalizationError(field_name, "deve ser uma lista JSON.")

    records: list[dict[str, Any]] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, Mapping):
            raise ContextNormalizationError(
                f"{field_name}[{index}]",
                "deve ser um objeto JSON.",
            )
        records.append(
            {
                str(key): deepcopy(record_value)
                for key, record_value in item.items()
            }
        )
    return records


def _normalize_string_list(value: Any, field_name: str) -> list[str]:
    parsed = _parse_json_like(value, field_name)
    if parsed is None:
        return []
    if isinstance(parsed, str):
        text = parsed.strip()
        return [text] if text else []
    if not isinstance(parsed, (list, tuple)):
        raise ContextNormalizationError(
            field_name,
            "deve ser uma lista de textos.",
        )

    result: list[str] = []
    for index, item in enumerate(parsed):
        if not isinstance(item, str):
            raise ContextNormalizationError(
                f"{field_name}[{index}]",
                "deve ser texto.",
            )
        text = item.strip()
        if text:
            result.append(text)
    return result


def _normalize_integer(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value
    if isinstance(value, float) and math.isfinite(value) and value.is_integer():
        return int(value)
    if isinstance(value, Decimal) and value == value.to_integral_value():
        return int(value)
    if isinstance(value, str):
        stripped = value.strip()
        if re.fullmatch(r"[+-]?\d+", stripped):
            return int(stripped)
    return value


def _normalize_number(value: Any) -> Any:
    if value is None or isinstance(value, bool):
        return value
    if isinstance(value, (int, float, Decimal)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip().replace(",", ".")
        try:
            return float(stripped)
        except ValueError:
            return value
    return value


def _normalize_boolean(value: Any) -> Any:
    if isinstance(value, bool) or value is None:
        return value
    if value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "t", "1", "yes", "sim"}:
            return True
        if normalized in {"false", "f", "0", "no", "nao", "não"}:
            return False
    return value


def _normalize_rules(value: Any) -> list[dict[str, Any]]:
    records = _normalize_record_list(value, "regras")
    normalized: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        item = deepcopy(record)
        item["rule_group"] = _normalize_text(record.get("rule_group"))
        item["rule_name"] = _normalize_text(record.get("rule_name"))
        item["rule_content"] = _parse_json_like(
            record.get("rule_content"),
            f"regras[{index}].rule_content",
        )
        item["applies_to_intents"] = _normalize_string_list(
            record.get("applies_to_intents"),
            f"regras[{index}].applies_to_intents",
        )
        item["validation_hint"] = _parse_json_like(
            record.get("validation_hint"),
            f"regras[{index}].validation_hint",
        )
        item["severity"] = _normalize_text(record.get("severity"))
        item["priority"] = _normalize_integer(record.get("priority"))
        normalized.append(item)

    return normalized


def _normalize_entities(value: Any) -> list[dict[str, Any]]:
    records = _normalize_record_list(value, "entidades")
    normalized: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        item = deepcopy(record)
        item["entity_type"] = _normalize_text(record.get("entity_type"))
        item["user_term"] = _normalize_text(record.get("user_term"))
        item["canonical_value"] = _normalize_text(
            record.get("canonical_value")
        )
        item["target_table"] = _normalize_optional_text(
            record.get("target_table")
        )
        item["target_column"] = _normalize_optional_text(
            record.get("target_column")
        )
        item["sql_filter_hint"] = _parse_json_like(
            record.get("sql_filter_hint"),
            f"entidades[{index}].sql_filter_hint",
        )
        item["business_rule"] = _parse_json_like(
            record.get("business_rule"),
            f"entidades[{index}].business_rule",
        )
        if item["entity_type"].casefold() == "intent_definition":
            item["business_rule"] = (
                _normalize_intent_definition_business_rule(
                    item.get("business_rule"),
                    entity_index=index,
                )
            )
        item["priority"] = _normalize_integer(record.get("priority"))
        normalized.append(item)

    return normalized


def _normalize_intent_definition_business_rule(
    value: Any,
    *,
    entity_index: int,
) -> Any:
    if not isinstance(value, Mapping):
        return deepcopy(value)

    business_rule = {
        str(key): deepcopy(item)
        for key, item in value.items()
    }
    if "intent_catalog" not in business_rule:
        return business_rule

    field_name = (
        f"entidades[{entity_index}].business_rule.intent_catalog"
    )
    parsed_catalog = _parse_json_like(
        business_rule.get("intent_catalog"),
        field_name,
    )
    if not isinstance(parsed_catalog, Mapping):
        business_rule["intent_catalog"] = deepcopy(parsed_catalog)
        return business_rule

    normalized_catalog = {
        str(key): deepcopy(item)
        for key, item in parsed_catalog.items()
    }
    normalized_catalog["semantic_description"] = _normalize_text(
        parsed_catalog.get("semantic_description")
    )
    normalized_catalog["rules"] = _normalize_intent_catalog_rules(
        parsed_catalog.get("rules"),
        field_name=f"{field_name}.rules",
    )
    business_rule["intent_catalog"] = normalized_catalog
    return business_rule


def _normalize_dre_mappings(value: Any) -> list[dict[str, Any]]:
    records = _normalize_record_list(value, "dre")
    normalized: list[dict[str, Any]] = []

    boolean_fields = (
        "is_revenue",
        "is_deduction",
        "is_cost",
        "is_opex",
        "is_financial_result",
    )

    for index, record in enumerate(records):
        item = deepcopy(record)
        item["dre_code"] = _normalize_text(record.get("dre_code"))
        item["nivel_1_bi"] = _normalize_text(record.get("nivel_1_bi"))
        item["business_description"] = _normalize_text(
            record.get("business_description")
        )
        item["sign_convention"] = _parse_json_like(
            record.get("sign_convention"),
            f"dre[{index}].sign_convention",
        )
        item["category"] = _normalize_text(record.get("category"))
        for field_name in boolean_fields:
            item[field_name] = _normalize_boolean(record.get(field_name))
        item["sql_filter_hint"] = _parse_json_like(
            record.get("sql_filter_hint"),
            f"dre[{index}].sql_filter_hint",
        )
        item["sort_order"] = _normalize_integer(record.get("sort_order"))
        normalized.append(item)

    return normalized


def _normalize_query_patterns(value: Any) -> list[dict[str, Any]]:
    records = _normalize_record_list(value, "padroes")
    normalized: list[dict[str, Any]] = []

    for index, record in enumerate(records):
        item = deepcopy(record)
        item["intent_name"] = _normalize_text(record.get("intent_name"))
        item["pattern_name"] = _normalize_text(record.get("pattern_name"))
        item["business_question_examples"] = _normalize_string_list(
            record.get("business_question_examples"),
            f"padroes[{index}].business_question_examples",
        )
        item["required_tables"] = _normalize_string_list(
            record.get("required_tables"),
            f"padroes[{index}].required_tables",
        )
        item["required_rules"] = _normalize_string_list(
            record.get("required_rules"),
            f"padroes[{index}].required_rules",
        )
        item["sql_pattern"] = _normalize_text(record.get("sql_pattern"))
        item["notes"] = _normalize_optional_text(record.get("notes"))
        item["priority"] = _normalize_integer(record.get("priority"))
        normalized.append(item)

    return normalized


def _normalize_table_catalog(value: Any) -> list[dict[str, Any]]:
    records = _normalize_record_list(value, "catalogo")
    normalized: list[dict[str, Any]] = []

    json_fields = (
        "grain",
        "primary_key",
        "key_columns",
        "metric_columns",
        "date_columns",
        "join_rules",
        "ai_hint",
        "columns",
    )

    for index, record in enumerate(records):
        item = deepcopy(record)
        item["table_name"] = _normalize_text(record.get("table_name"))
        item["schema_name"] = _normalize_text(record.get("schema_name"))
        item["table_type"] = _normalize_text(record.get("table_type"))
        item["description"] = _normalize_optional_text(
            record.get("description")
        )
        for field_name in json_fields:
            item[field_name] = _parse_json_like(
                record.get(field_name),
                f"catalogo[{index}].{field_name}",
            )
        if item.get("columns") is None:
            item["columns"] = []
        item["priority"] = _normalize_integer(record.get("priority"))
        normalized.append(item)

    return normalized


def _normalize_counts(
    value: Any,
    *,
    rules: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    dre_mappings: list[dict[str, Any]],
    query_patterns: list[dict[str, Any]],
    table_catalog: list[dict[str, Any]],
) -> dict[str, Any]:
    raw_counts = _normalize_mapping(value, "context_counts")

    source_and_fallback = {
        "rules": ("regras", len(rules)),
        "entities": ("entidades", len(entities)),
        "dre_mappings": ("dre", len(dre_mappings)),
        "query_patterns": ("padroes", len(query_patterns)),
        "table_catalog": ("catalogo", len(table_catalog)),
    }

    counts: dict[str, Any] = {}
    for canonical_name, (physical_name, fallback) in (
        source_and_fallback.items()
    ):
        raw_value = _first_present(
            raw_counts,
            canonical_name,
            physical_name,
            default=fallback,
        )
        counts[canonical_name] = _normalize_integer(raw_value)

    return counts


def _record_sort_key(
    record: Mapping[str, Any],
    *fields: str,
) -> tuple[Any, ...]:
    priority_value = record.get(fields[0]) if fields else None
    priority = _numeric_sort_value(priority_value)
    text_values = tuple(
        _normalize_text(record.get(field_name)).casefold()
        for field_name in fields[1:]
    )
    return (priority, *text_values)


def _numeric_sort_value(value: Any) -> float:
    if value is None or isinstance(value, bool):
        return math.inf
    try:
        number = float(value)
    except (TypeError, ValueError):
        return math.inf
    return number if math.isfinite(number) else math.inf


def _derive_component_configs(
    rules: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    configs: dict[str, dict[str, Any]] = {}

    for rule in rules:
        content = rule.get("rule_content")
        if not isinstance(content, Mapping):
            continue

        component_name = _normalize_text(content.get("component"))
        if not component_name:
            continue

        configs.setdefault(
            component_name,
            {
                str(key): deepcopy(value)
                for key, value in content.items()
            },
        )

    return configs


def _derive_intent_resolution_config(
    raw_config: Any,
) -> dict[str, Any]:
    if not isinstance(raw_config, Mapping):
        return {}

    config = {
        str(key): deepcopy(value)
        for key, value in raw_config.items()
    }

    if "component" in config:
        config["component"] = _normalize_text(
            config.get("component")
        )

    for field_name in (
        "minimum_score",
        "ambiguity_margin",
        "applied_confidence",
    ):
        if field_name in config:
            config[field_name] = _normalize_number(
                config.get(field_name)
            )

    if "fallback_to_previous_intent" in config:
        config["fallback_to_previous_intent"] = (
            _normalize_boolean(
                config.get("fallback_to_previous_intent")
            )
        )

    if "token_fallback" in config:
        config["token_fallback"] = (
            _normalize_token_fallback_config(
                config.get("token_fallback")
            )
        )

    return config


def _normalize_token_fallback_config(
    raw_config: Any,
) -> Any:
    parsed = _parse_json_like(
        raw_config,
        "intent_resolution.config.token_fallback",
    )
    if parsed is None or not isinstance(parsed, Mapping):
        return parsed

    config = {
        str(key): deepcopy(value)
        for key, value in parsed.items()
    }

    if "enabled" in config:
        config["enabled"] = _normalize_boolean(
            config.get("enabled")
        )

    for field_name in (
        "apply_to_polarities",
        "apply_to_match_modes",
    ):
        if field_name in config:
            config[field_name] = _normalize_config_text_set(
                config.get(field_name),
                field_name=(
                    "intent_resolution.config.token_fallback."
                    f"{field_name}"
                ),
                normalize_search=False,
            )

    if "ignored_tokens" in config:
        config["ignored_tokens"] = _normalize_config_text_set(
            config.get("ignored_tokens"),
            field_name=(
                "intent_resolution.config.token_fallback."
                "ignored_tokens"
            ),
            normalize_search=True,
        )

    for field_name in (
        "minimum_pattern_tokens",
        "minimum_matched_tokens",
        "maximum_unmatched_pattern_tokens",
        "minimum_prefix_length",
    ):
        if field_name in config:
            config[field_name] = _normalize_integer(
                config.get(field_name)
            )

    for field_name in (
        "minimum_pattern_coverage",
        "minimum_prefix_ratio",
    ):
        if field_name in config:
            config[field_name] = _normalize_number(
                config.get(field_name)
            )

    if "allow_prefix_equivalence" in config:
        config["allow_prefix_equivalence"] = (
            _normalize_boolean(
                config.get("allow_prefix_equivalence")
            )
        )

    return config


def _normalize_config_text_set(
    value: Any,
    *,
    field_name: str,
    normalize_search: bool,
) -> Any:
    parsed = _parse_json_like(value, field_name)
    if not isinstance(parsed, (list, tuple)):
        return parsed

    normalized_values: set[str] = set()
    for item in parsed:
        if not isinstance(item, str):
            return deepcopy(parsed)

        text = (
            normalize_search_text(item)
            if normalize_search
            else _normalize_text(item).casefold()
        )
        if text:
            normalized_values.add(text)

    return sorted(normalized_values, key=str.casefold)


def _derive_intent_catalog(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    catalog: list[dict[str, Any]] = []

    for entity_index, entity in enumerate(entities):
        entity_type = _normalize_text(
            entity.get("entity_type")
        ).casefold()
        if entity_type != "intent_definition":
            continue

        business_rule = entity.get("business_rule")
        raw_catalog = (
            business_rule.get("intent_catalog")
            if isinstance(business_rule, Mapping)
            else None
        )
        parsed_catalog = _parse_json_like(
            raw_catalog,
            (
                f"entidades[{entity_index}].business_rule."
                "intent_catalog"
            ),
        )

        if isinstance(parsed_catalog, Mapping):
            semantic_description = _normalize_text(
                parsed_catalog.get("semantic_description")
            )
            rules = _normalize_intent_catalog_rules(
                parsed_catalog.get("rules"),
                field_name=(
                    f"entidades[{entity_index}].business_rule."
                    "intent_catalog.rules"
                ),
            )
        else:
            semantic_description = ""
            rules = deepcopy(parsed_catalog)

        catalog.append(
            {
                "intent_name": _normalize_text(
                    entity.get("canonical_value")
                ),
                "definition_name": _normalize_text(
                    entity.get("user_term")
                ),
                "semantic_description": semantic_description,
                "rules": rules,
                "priority": _normalize_number(
                    entity.get("priority")
                ),
            }
        )

    catalog.sort(
        key=lambda item: (
            _numeric_sort_value(item.get("priority")),
            _normalize_text(item.get("intent_name")).casefold(),
            _normalize_text(item.get("definition_name")).casefold(),
        )
    )
    return catalog


def _normalize_intent_catalog_rules(
    value: Any,
    *,
    field_name: str,
) -> Any:
    parsed = _parse_json_like(value, field_name)
    if not isinstance(parsed, (list, tuple)):
        return deepcopy(parsed)

    rules: list[Any] = []
    for rule_index, raw_rule in enumerate(parsed):
        if not isinstance(raw_rule, Mapping):
            rules.append(deepcopy(raw_rule))
            continue

        rule_path = f"{field_name}[{rule_index}]"
        rule = {
            "rule_name": _normalize_text(
                raw_rule.get("rule_name")
            ),
            "effect": _normalize_text(
                raw_rule.get("effect")
            ).casefold(),
            "concepts": _normalize_intent_catalog_concepts(
                raw_rule.get("concepts"),
                field_name=f"{rule_path}.concepts",
            ),
            "minimum_concept_matches": _normalize_integer(
                raw_rule.get("minimum_concept_matches")
            ),
            "score": _normalize_number(raw_rule.get("score")),
            "priority": _normalize_number(
                raw_rule.get("priority")
            ),
        }
        rules.append(rule)

    if all(isinstance(item, Mapping) for item in rules):
        rules.sort(
            key=lambda item: (
                _numeric_sort_value(item.get("priority")),
                _normalize_text(item.get("rule_name")).casefold(),
            )
        )

    return rules


def _normalize_intent_catalog_concepts(
    value: Any,
    *,
    field_name: str,
) -> Any:
    parsed = _parse_json_like(value, field_name)
    if not isinstance(parsed, (list, tuple)):
        return deepcopy(parsed)

    concepts: list[Any] = []
    for concept_index, raw_concept in enumerate(parsed):
        if not isinstance(raw_concept, Mapping):
            concepts.append(deepcopy(raw_concept))
            continue

        concept_path = f"{field_name}[{concept_index}]"
        match_mode = _normalize_text(
            raw_concept.get("match_mode")
        ).casefold()
        terms, normalized_terms = _normalize_intent_catalog_terms(
            raw_concept.get("terms"),
            match_mode=match_mode,
            field_name=f"{concept_path}.terms",
        )
        concept = {
            "concept_name": _normalize_text(
                raw_concept.get("concept_name")
            ),
            "terms": terms,
            "normalized_terms": normalized_terms,
            "match_mode": match_mode,
            "minimum_term_matches": _normalize_integer(
                raw_concept.get("minimum_term_matches")
            ),
        }
        concepts.append(concept)

    if all(isinstance(item, Mapping) for item in concepts):
        concepts.sort(
            key=lambda item: _normalize_text(
                item.get("concept_name")
            ).casefold()
        )

    return concepts


def _normalize_intent_catalog_terms(
    value: Any,
    *,
    match_mode: str,
    field_name: str,
) -> tuple[Any, Any]:
    parsed = _parse_json_like(value, field_name)
    if not isinstance(parsed, (list, tuple)):
        copied = deepcopy(parsed)
        return copied, deepcopy(copied)

    pairs: list[tuple[Any, Any]] = []
    for raw_term in parsed:
        if isinstance(raw_term, str):
            term = _normalize_text(raw_term)
            normalized_term = (
                term
                if match_mode == "regex"
                else normalize_search_text(term)
            )
        else:
            term = deepcopy(raw_term)
            normalized_term = deepcopy(raw_term)
        pairs.append((term, normalized_term))

    if all(
        isinstance(term, str) and isinstance(normalized, str)
        for term, normalized in pairs
    ):
        pairs.sort(
            key=lambda pair: (
                pair[1].casefold(),
                pair[0].casefold(),
            )
        )

    return (
        [term for term, _ in pairs],
        [normalized for _, normalized in pairs],
    )


def _derive_intent_resolution_signals(
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    signals: list[dict[str, Any]] = []

    for entity in entities:
        entity_type = _normalize_text(
            entity.get("entity_type")
        ).casefold()
        if entity_type == "intent_definition":
            continue

        hint = entity.get("sql_filter_hint")
        if not isinstance(hint, Mapping):
            continue

        resolver = hint.get("resolver")
        if not isinstance(resolver, Mapping):
            continue

        intent_name = _normalize_text(entity.get("canonical_value"))
        raw_pattern = _normalize_text(entity.get("user_term"))
        if not intent_name or not raw_pattern:
            continue

        match_mode = _normalize_text(
            resolver.get("match_mode")
        ).casefold()
        polarity = _normalize_text(
            resolver.get("polarity")
        ).casefold()

        priority = _normalize_number(
            _first_present(
                resolver,
                "priority",
                default=entity.get("priority"),
            )
        )

        signal: dict[str, Any] = {
            "intent_name": intent_name,
            "raw_pattern": raw_pattern,
            "normalized_pattern": (
                raw_pattern
                if match_mode == "regex"
                else normalize_search_text(raw_pattern)
            ),
            "match_mode": match_mode,
            "polarity": polarity,
            "score": _normalize_number(resolver.get("score")),
            "priority": priority,
            "entity_type": _normalize_optional_text(
                entity.get("entity_type")
            ),
            "target_table": _normalize_optional_text(
                entity.get("target_table")
            ),
            "target_column": _normalize_optional_text(
                entity.get("target_column")
            ),
        }
        signals.append(signal)

    signals.sort(
        key=lambda item: (
            _numeric_sort_value(item.get("priority")),
            _normalize_text(item.get("intent_name")).casefold(),
            _normalize_text(item.get("normalized_pattern")).casefold(),
        )
    )
    return signals



def _derive_legacy_aliases(
    entities: list[dict[str, Any]],
) -> dict[str, str]:
    aliases: dict[str, str] = {}

    for entity in entities:
        entity_type = _normalize_text(
            entity.get("entity_type")
        ).casefold()
        if entity_type == "intent_definition":
            continue

        user_term = _normalize_text(entity.get("user_term"))
        canonical_value = _normalize_text(entity.get("canonical_value"))
        if user_term and canonical_value:
            aliases.setdefault(user_term, canonical_value)

    return aliases


def _calculate_fingerprint(payload: Mapping[str, Any]) -> str:
    try:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
            default=_json_default,
        )
    except (TypeError, ValueError) as exc:
        raise ContextNormalizationError(
            "fingerprint",
            (
                "não foi possível serializar o snapshot canônico: "
                f"{exc}."
            ),
        ) from exc

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, tuple):
        return list(value)
    raise TypeError(f"tipo não serializável: {type(value).__name__}")
