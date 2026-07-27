from __future__ import annotations

import sys
from collections import Counter, defaultdict
from collections.abc import Mapping
from typing import Any

from psycopg.conninfo import make_conninfo

from app.adapters.postgres.context_repository import (
    PostgresContextRepository,
)
from app.domain.context_validator import (
    validate_context_snapshot,
)
from app.domain.intent_resolver import (
    IntentResolverInputError,
    resolve_intent,
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


def _non_empty_text(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    return value.strip()


def _signal_coverage(
    signals: list[Any],
) -> tuple[
    dict[str, Counter[str]],
    dict[str, list[Mapping[str, Any]]],
]:
    counts: dict[str, Counter[str]] = defaultdict(Counter)
    grouped: dict[str, list[Mapping[str, Any]]] = defaultdict(list)

    for signal in signals:
        if not isinstance(signal, Mapping):
            continue

        intent_name = _non_empty_text(
            signal.get("intent_name")
        )
        polarity = _non_empty_text(
            signal.get("polarity")
        )

        if not intent_name:
            continue

        counts[intent_name][polarity or "unknown"] += 1
        grouped[intent_name].append(signal)

    return dict(counts), dict(grouped)


def _pattern_intents(
    query_patterns: list[Any],
) -> set[str]:
    output: set[str] = set()

    for pattern in query_patterns:
        if not isinstance(pattern, Mapping):
            continue

        intent_name = _non_empty_text(
            pattern.get("intent_name")
        )
        if intent_name:
            output.add(intent_name)

    return output


def _print_configuration(
    config: Mapping[str, Any],
) -> None:
    token_fallback = config.get("token_fallback")
    token_fallback_enabled = False

    if isinstance(token_fallback, Mapping):
        token_fallback_enabled = bool(
            token_fallback.get("enabled", False)
        )

    print("CONFIGURACAO_RESOLVEDOR:")
    print(
        f"- minimum_score={config.get('minimum_score', '-')}"
    )
    print(
        "- ambiguity_margin="
        f"{config.get('ambiguity_margin', '-')}"
    )
    print(
        "- applied_confidence="
        f"{config.get('applied_confidence', '-')}"
    )
    print(
        "- fallback_to_previous_intent="
        f"{config.get('fallback_to_previous_intent', '-')}"
    )
    print(
        "- token_fallback.enabled="
        f"{token_fallback_enabled}"
    )


def _print_coverage(
    pattern_intents: set[str],
    coverage: dict[str, Counter[str]],
) -> None:
    signal_intents = set(coverage)
    without_signals = sorted(
        pattern_intents - signal_intents
    )
    only_negative = sorted(
        intent_name
        for intent_name, polarity_counts in coverage.items()
        if polarity_counts.get("negative", 0) > 0
        and polarity_counts.get("positive", 0) == 0
    )

    print()
    print("COBERTURA_DE_INTENCOES:")
    print(
        f"- query_pattern_intents={len(pattern_intents)}"
    )
    print(f"- signal_intents={len(signal_intents)}")
    print(
        "- intents_without_signals="
        f"{len(without_signals)}"
    )
    for intent_name in without_signals:
        print(f"  - {intent_name}")

    print(
        "- intents_only_negative_signals="
        f"{len(only_negative)}"
    )
    for intent_name in only_negative:
        print(f"  - {intent_name}")

    print()
    print("CONTAGEM_DE_SINAIS_POR_INTENCAO:")
    for intent_name in sorted(coverage):
        polarity_counts = coverage[intent_name]
        print(
            f"- {intent_name}: "
            f"positive={polarity_counts.get('positive', 0)} "
            f"negative={polarity_counts.get('negative', 0)} "
            f"unknown={polarity_counts.get('unknown', 0)}"
        )


def _print_resolution(
    result: Mapping[str, Any],
) -> None:
    print()
    print("RESOLUCAO_DA_PERGUNTA:")
    print(f"- applied={result.get('applied', False)}")
    print(f"- reason={result.get('reason', '-')}")
    print(f"- intent={result.get('intent') or '-'}")
    print(
        "- intent_confidence="
        f"{result.get('intent_confidence') or '-'}"
    )
    print(
        "- normalized_question="
        f"{result.get('normalized_question', '-')}"
    )
    print(
        "- resolver_version="
        f"{result.get('resolver_version', '-')}"
    )

    candidates = result.get("candidates", [])
    if not isinstance(candidates, list):
        candidates = []

    print(f"- candidate_count={len(candidates)}")

    for candidate_index, candidate in enumerate(
        candidates,
        start=1,
    ):
        if not isinstance(candidate, Mapping):
            continue

        print(
            f"  CANDIDATO {candidate_index}: "
            f"intent={candidate.get('intent_name', '-')} "
            f"score={candidate.get('score', '-')} "
            f"positive={candidate.get('positive_score', '-')} "
            f"negative={candidate.get('negative_score', '-')} "
            f"priority={candidate.get('best_priority', '-')}"
        )

        matches = candidate.get("matches", [])
        if not isinstance(matches, list):
            continue

        for match_index, match in enumerate(
            matches,
            start=1,
        ):
            if not isinstance(match, Mapping):
                continue

            print(
                f"    MATCH {match_index}: "
                f"pattern={match.get('pattern', '-')} | "
                f"mode={match.get('match_mode', '-')} | "
                f"strategy={match.get('match_strategy', '-')} | "
                f"polarity={match.get('polarity', '-')} | "
                f"score={match.get('score', '-')}"
            )


def main() -> int:
    print("=" * 70)
    print("POSTGRES INTENT RESOLUTION DIAGNOSTIC — LIVE")
    print("=" * 70)
    print(
        "Teste somente leitura. Credenciais e DSN não serão exibidos."
    )
    print(
        "O diagnóstico mostra apenas cobertura semântica, "
        "candidatos e sinais correspondentes."
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

        intent_resolution = snapshot.get(
            "intent_resolution",
            {},
        )
        if not isinstance(intent_resolution, Mapping):
            print("INTENT_RESOLUTION: INVALIDO")
            return 4

        config = intent_resolution.get("config", {})
        signals = intent_resolution.get("signals", [])
        query_patterns = snapshot.get("query_patterns", [])

        if not isinstance(config, Mapping):
            print("INTENT_RESOLUTION_CONFIG: INVALIDA")
            return 4
        if not isinstance(signals, list):
            print("INTENT_RESOLUTION_SIGNALS: INVALIDOS")
            return 4
        if not isinstance(query_patterns, list):
            print("QUERY_PATTERNS: INVALIDOS")
            return 4

        coverage, _ = _signal_coverage(signals)
        pattern_intents = _pattern_intents(query_patterns)

        result = resolve_intent(
            question,
            intent_resolution,
        )

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

        _print_configuration(config)
        _print_coverage(pattern_intents, coverage)
        _print_resolution(result)

        print()
        print("DIAGNOSTICO_CONCLUIDO: OK")
        return 0

    except ContextRepositoryError as error:
        print("CONSULTA_CONTEXTO: ERRO")
        print(f"REPOSITORIO: {error}")

        cause = _root_cause(error)
        if isinstance(cause, BaseException):
            _print_safe_psycopg_diagnostic(cause)
        return 4

    except IntentResolverInputError as error:
        print(f"RESOLVEDOR: ERRO_DE_CONTRATO — {error}")
        return 5

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
