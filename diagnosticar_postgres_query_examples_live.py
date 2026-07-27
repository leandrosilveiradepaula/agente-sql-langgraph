from __future__ import annotations

import sys
from collections import defaultdict
from collections.abc import Mapping
from typing import Any, TypedDict

from psycopg.conninfo import make_conninfo

from app.adapters.postgres.context_repository import (
    PostgresContextRepository,
)
from app.domain.context_validator import (
    validate_context_snapshot,
)
from app.domain.search_text import (
    normalize_search_text,
    tokenize_search_text,
)
from app.ports.context_repository import ContextRepositoryError
from testar_postgres_context_live import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_DATABASE,
    DEFAULT_PORT,
    LIVE_TEST_USER_PROFILE,
    SSL_MODE,
    _connection_preflight,
    _hidden_required_input,
    _positive_integer_input,
    _print_safe_psycopg_diagnostic,
    _required_input,
    _root_cause,
    _text_input_with_default,
)


MAX_EXAMPLES_PER_PATTERN = 3
MAX_TOP_MATCHES = 10


class ExampleRecord(TypedDict):
    intent_name: str
    pattern_name: str
    example: str
    normalized_example: str
    tokens: list[str]


class ExampleSimilarity(TypedDict):
    intent_name: str
    pattern_name: str
    example: str
    normalized_example: str
    exact_match: bool
    shared_tokens: int
    question_coverage: float
    example_coverage: float
    jaccard: float


def _non_empty_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []

    output: list[str] = []
    for item in value:
        text = _non_empty_text(item)
        if text:
            output.append(text)

    return output


def _collect_examples(
    query_patterns: list[Any],
) -> tuple[
    list[ExampleRecord],
    dict[str, int],
    list[str],
]:
    records: list[ExampleRecord] = []
    counts_by_intent: dict[str, int] = defaultdict(int)
    intents_without_examples: list[str] = []

    for pattern in query_patterns:
        if not isinstance(pattern, Mapping):
            continue

        intent_name = _non_empty_text(
            pattern.get("intent_name")
        )
        pattern_name = _non_empty_text(
            pattern.get("pattern_name")
        )
        examples = _string_list(
            pattern.get("business_question_examples")
        )

        if not intent_name:
            continue

        if not examples:
            intents_without_examples.append(intent_name)

        for example in examples:
            normalized_example = normalize_search_text(
                example
            )
            records.append(
                {
                    "intent_name": intent_name,
                    "pattern_name": pattern_name,
                    "example": example,
                    "normalized_example": normalized_example,
                    "tokens": tokenize_search_text(
                        normalized_example
                    ),
                }
            )
            counts_by_intent[intent_name] += 1

    return (
        records,
        dict(counts_by_intent),
        sorted(set(intents_without_examples)),
    )


def _duplicate_groups(
    records: list[ExampleRecord],
) -> list[tuple[str, list[ExampleRecord]]]:
    grouped: dict[str, list[ExampleRecord]] = defaultdict(list)

    for record in records:
        normalized = record["normalized_example"]
        if normalized:
            grouped[normalized].append(record)

    duplicates = [
        (normalized, items)
        for normalized, items in grouped.items()
        if len(items) > 1
    ]
    duplicates.sort(
        key=lambda item: (
            -len(item[1]),
            item[0],
        )
    )
    return duplicates


def _similarities(
    question: str,
    records: list[ExampleRecord],
) -> tuple[str, list[ExampleSimilarity]]:
    normalized_question = normalize_search_text(question)
    question_tokens = set(
        tokenize_search_text(normalized_question)
    )
    similarities: list[ExampleSimilarity] = []

    for record in records:
        example_tokens = set(record["tokens"])
        shared_tokens = len(
            question_tokens.intersection(example_tokens)
        )
        union_tokens = len(
            question_tokens.union(example_tokens)
        )

        question_coverage = (
            shared_tokens / len(question_tokens)
            if question_tokens
            else 0.0
        )
        example_coverage = (
            shared_tokens / len(example_tokens)
            if example_tokens
            else 0.0
        )
        jaccard = (
            shared_tokens / union_tokens
            if union_tokens
            else 0.0
        )

        similarities.append(
            {
                "intent_name": record["intent_name"],
                "pattern_name": record["pattern_name"],
                "example": record["example"],
                "normalized_example": (
                    record["normalized_example"]
                ),
                "exact_match": (
                    normalized_question
                    == record["normalized_example"]
                ),
                "shared_tokens": shared_tokens,
                "question_coverage": question_coverage,
                "example_coverage": example_coverage,
                "jaccard": jaccard,
            }
        )

    similarities.sort(
        key=lambda item: (
            not item["exact_match"],
            -item["jaccard"],
            -item["example_coverage"],
            -item["question_coverage"],
            item["intent_name"],
            item["pattern_name"],
            item["normalized_example"],
        )
    )

    return normalized_question, similarities


def _print_pattern_summary(
    query_patterns: list[Any],
    counts_by_intent: dict[str, int],
    records: list[ExampleRecord],
) -> None:
    examples_by_pattern: dict[
        tuple[str, str],
        list[ExampleRecord],
    ] = defaultdict(list)

    for record in records:
        key = (
            record["intent_name"],
            record["pattern_name"],
        )
        examples_by_pattern[key].append(record)

    print("PADROES_E_EXEMPLOS:")

    for pattern in query_patterns:
        if not isinstance(pattern, Mapping):
            continue

        intent_name = _non_empty_text(
            pattern.get("intent_name")
        )
        pattern_name = _non_empty_text(
            pattern.get("pattern_name")
        )
        priority = pattern.get("priority")
        key = (intent_name, pattern_name)
        pattern_examples = examples_by_pattern.get(
            key,
            [],
        )

        print(
            f"- intent={intent_name or '-'} "
            f"pattern={pattern_name or '-'} "
            f"priority={priority if priority is not None else '-'} "
            f"examples={len(pattern_examples)}"
        )

        for record in pattern_examples[
            :MAX_EXAMPLES_PER_PATTERN
        ]:
            print(f"  - {record['example']}")

        remaining = (
            len(pattern_examples)
            - MAX_EXAMPLES_PER_PATTERN
        )
        if remaining > 0:
            print(
                f"  - ... mais {remaining} exemplo(s)"
            )

    print()
    print("CONTAGEM_POR_INTENCAO:")
    for intent_name in sorted(counts_by_intent):
        print(
            f"- {intent_name}: "
            f"{counts_by_intent[intent_name]}"
        )


def _print_duplicates(
    duplicates: list[tuple[str, list[ExampleRecord]]],
) -> None:
    print()
    print(
        f"EXEMPLOS_NORMALIZADOS_DUPLICADOS: "
        f"{len(duplicates)}"
    )

    for normalized, items in duplicates:
        intents = sorted(
            {
                item["intent_name"]
                for item in items
            }
        )
        patterns = sorted(
            {
                item["pattern_name"]
                for item in items
            }
        )

        print(
            f"- normalized={normalized} "
            f"occurrences={len(items)} "
            f"intents={','.join(intents)} "
            f"patterns={','.join(patterns)}"
        )


def _print_top_matches(
    normalized_question: str,
    similarities: list[ExampleSimilarity],
) -> None:
    print()
    print("COMPARACAO_COM_A_PERGUNTA:")
    print(
        f"- normalized_question={normalized_question}"
    )
    print(
        f"- evaluated_examples={len(similarities)}"
    )

    for index, item in enumerate(
        similarities[:MAX_TOP_MATCHES],
        start=1,
    ):
        print(
            f"  MATCH {index}: "
            f"intent={item['intent_name']} "
            f"pattern={item['pattern_name']} "
            f"exact={item['exact_match']} "
            f"shared_tokens={item['shared_tokens']} "
            f"question_coverage="
            f"{item['question_coverage']:.6f} "
            f"example_coverage="
            f"{item['example_coverage']:.6f} "
            f"jaccard={item['jaccard']:.6f}"
        )
        print(f"    example={item['example']}")


def main() -> int:
    print("=" * 70)
    print("POSTGRES QUERY PATTERN EXAMPLES — LIVE DIAGNOSTIC")
    print("=" * 70)
    print(
        "Teste somente leitura. Credenciais e DSN não serão exibidos."
    )
    print(
        "O diagnóstico mede cobertura e colisões dos exemplos "
        "já existentes no contexto versionado."
    )
    print()

    try:
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
        password = _hidden_required_input(
            "POSTGRES_PASSWORD"
        )
        semantic_agent_version = _required_input(
            "SEMANTIC_AGENT_VERSION"
        )
        connect_timeout_seconds = _positive_integer_input(
            "POSTGRES_CONNECT_TIMEOUT_SECONDS",
            default=DEFAULT_CONNECT_TIMEOUT_SECONDS,
        )
        question = _required_input("QUESTION")

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

        repository = PostgresContextRepository(
            dsn=dsn,
            semantic_agent_version=semantic_agent_version,
            connect_timeout_seconds=connect_timeout_seconds,
        )
        snapshot = repository.load_active_context(
            user_profile=LIVE_TEST_USER_PROFILE,
        )

        validation = validate_context_snapshot(snapshot)
        if validation["status"] != "valid":
            print("VALIDACAO_CONTEXTO: INVALIDA")
            for error in validation["errors"]:
                print(
                    f"- {error.get('code', 'UNKNOWN')}: "
                    f"{error.get('message', '')}"
                )
            return 4

        query_patterns = snapshot.get(
            "query_patterns",
            [],
        )
        if not isinstance(query_patterns, list):
            print("QUERY_PATTERNS: INVALIDOS")
            return 4

        (
            records,
            counts_by_intent,
            intents_without_examples,
        ) = _collect_examples(query_patterns)
        duplicates = _duplicate_groups(records)
        (
            normalized_question,
            similarities,
        ) = _similarities(question, records)

        print()
        print("=" * 70)
        print("DIAGNOSTICO")
        print("=" * 70)
        print(
            f"CONTEXTO_VERSAO: {snapshot.get('version', '-')}"
        )
        print(
            "CONTEXTO_FINGERPRINT: "
            f"{snapshot.get('fingerprint', '-')}"
        )
        print(
            f"QUERY_PATTERNS: {len(query_patterns)}"
        )
        print(
            f"TOTAL_EXEMPLOS: {len(records)}"
        )
        print(
            "INTENCOES_SEM_EXEMPLOS: "
            f"{len(intents_without_examples)}"
        )
        for intent_name in intents_without_examples:
            print(f"- {intent_name}")

        print()
        _print_pattern_summary(
            query_patterns,
            counts_by_intent,
            records,
        )
        _print_duplicates(duplicates)
        _print_top_matches(
            normalized_question,
            similarities,
        )

        print()
        print("DIAGNOSTICO_CONCLUIDO: OK")
        return 0

    except ContextRepositoryError as error:
        print("CONSULTA_CONTEXTO: ERRO")
        print(f"REPOSITORIO: {error}")

        cause = _root_cause(error)
        _print_safe_psycopg_diagnostic(cause)
        return 4

    except ValueError as error:
        print(f"CONFIGURACAO: ERRO — {error}")
        return 2

    except KeyboardInterrupt:
        print()
        print("TESTE: CANCELADO")
        return 130

    except Exception:
        print()
        print(
            "TESTE: ERRO INESPERADO. "
            "Detalhes sensíveis foram omitidos."
        )
        return 6


if __name__ == "__main__":
    sys.exit(main())
