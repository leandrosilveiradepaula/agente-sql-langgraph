from __future__ import annotations

import sys
from collections.abc import Mapping
from typing import Any

from psycopg.conninfo import make_conninfo

from app.bootstrap import create_postgres_context_graph
from app.config.postgres_context import RuntimeConfigError
from app.graph.state import GraphState
from testar_postgres_context_live import (
    DEFAULT_CONNECT_TIMEOUT_SECONDS,
    DEFAULT_DATABASE,
    DEFAULT_PORT,
    LIVE_TEST_USER_PROFILE,
    SSL_MODE,
    _connection_preflight,
    _hidden_required_input,
    _positive_integer_input,
    _required_input,
    _text_input_with_default,
)


LIVE_TEST_USER_ID = "runtime-intent-validation"
LIVE_TEST_USER_EMAIL = "runtime-intent-validation@example.invalid"


def _candidate_summary(
    candidate: Any,
) -> str:
    if not isinstance(candidate, Mapping):
        return "nenhum"

    intent_name = candidate.get("intent_name", "")
    score = candidate.get("score", "")
    priority = candidate.get("best_priority", "")

    return (
        f"intent={intent_name or '-'} "
        f"score={score if score != '' else '-'} "
        f"priority={priority if priority != '' else '-'}"
    )


def _print_safe_graph_summary(
    result: Mapping[str, Any],
) -> None:
    context = result.get("context")
    context_version = result.get("context_version", "")
    context_fingerprint = ""

    if isinstance(context, Mapping):
        context_fingerprint = str(
            context.get("fingerprint", "")
        )

    resolution = result.get("intent_resolution_result")
    reason = ""
    resolver_version = ""
    best_candidate: Any = None
    second_candidate: Any = None
    token_fallback_used = False
    catalog_available = False
    catalog_entries_evaluated = 0
    catalog_used_for_selected_intent = False
    catalog_contributed_score = False

    if isinstance(resolution, Mapping):
        reason = str(resolution.get("reason", ""))
        resolver_version = str(
            resolution.get("resolver_version", "")
        )
        best_candidate = resolution.get("best_candidate")
        second_candidate = resolution.get(
            "second_candidate"
        )

        token_fallback = resolution.get("token_fallback")
        if isinstance(token_fallback, Mapping):
            token_fallback_used = bool(
                token_fallback.get(
                    "used_for_selected_intent",
                    False,
                )
            )

        intent_catalog = resolution.get("intent_catalog")
        if isinstance(intent_catalog, Mapping):
            catalog_available = bool(
                intent_catalog.get("available", False)
            )
            raw_entries = intent_catalog.get(
                "entries_evaluated",
                0,
            )
            if (
                isinstance(raw_entries, int)
                and not isinstance(raw_entries, bool)
            ):
                catalog_entries_evaluated = raw_entries
            catalog_used_for_selected_intent = bool(
                intent_catalog.get(
                    "used_for_selected_intent",
                    False,
                )
            )
            catalog_contributed_score = bool(
                intent_catalog.get(
                    "contributed_score_to_selected_intent",
                    False,
                )
            )

    print()
    print("=" * 70)
    print("POSTGRES INTENT GRAPH LIVE CHECK — RESULTADO")
    print("=" * 70)
    print(
        f"FINAL_STATUS: {result.get('final_status', '')}"
    )
    print(
        f"CURRENT_STAGE: {result.get('current_stage', '')}"
    )
    print(
        f"FAILURE_STAGE: "
        f"{result.get('failure_stage', '') or '-'}"
    )
    print(f"CONTEXTO_VERSAO: {context_version or '-'}")
    print(
        "CONTEXTO_FINGERPRINT: "
        f"{context_fingerprint or '-'}"
    )
    print(f"INTENT: {result.get('intent') or '-'}")

    confidence = result.get("intent_confidence")
    if isinstance(confidence, (int, float)) and not isinstance(
        confidence,
        bool,
    ):
        print(
            "INTENT_CONFIDENCE: "
            f"{float(confidence):.6f}"
        )
    else:
        print("INTENT_CONFIDENCE: -")

    print(f"RESOLUTION_REASON: {reason or '-'}")
    print(
        f"RESOLVER_VERSION: {resolver_version or '-'}"
    )
    print(
        "TOKEN_FALLBACK_USED: "
        f"{'sim' if token_fallback_used else 'nao'}"
    )
    print(
        "BEST_CANDIDATE: "
        f"{_candidate_summary(best_candidate)}"
    )
    print(
        "SECOND_CANDIDATE: "
        f"{_candidate_summary(second_candidate)}"
    )
    print(
        "INTENT_CATALOG_AVAILABLE: "
        f"{'sim' if catalog_available else 'nao'}"
    )
    print(
        "INTENT_CATALOG_ENTRIES_EVALUATED: "
        f"{catalog_entries_evaluated}"
    )
    print(
        "INTENT_CATALOG_USED_FOR_SELECTED_INTENT: "
        f"{'sim' if catalog_used_for_selected_intent else 'nao'}"
    )
    print(
        "INTENT_CATALOG_CONTRIBUTED_SCORE: "
        f"{'sim' if catalog_contributed_score else 'nao'}"
    )

    errors = result.get("errors", [])
    if isinstance(errors, list) and errors:
        print("ERROS:")
        for error in errors:
            if not isinstance(error, Mapping):
                continue

            code = error.get("code", "UNKNOWN")
            stage = error.get("stage", "-")
            message = error.get("message", "")

            print(
                f"- {code} stage={stage}: {message}"
            )


def _result_exit_code(
    result: Mapping[str, Any],
    *,
    expected_context_version: str,
    expected_context_fingerprint: str,
    expected_intent: str,
    expected_catalog_entries: int,
) -> int:
    final_status = result.get("final_status")
    current_stage = result.get("current_stage")
    intent = result.get("intent")
    confidence = result.get("intent_confidence")
    context_version = str(
        result.get("context_version", "")
    )

    context = result.get("context")
    context_fingerprint = ""
    normalized_catalog_entries = -1

    if isinstance(context, Mapping):
        context_fingerprint = str(
            context.get("fingerprint", "")
        )
        intent_resolution = context.get("intent_resolution")
        if isinstance(intent_resolution, Mapping):
            intent_catalog = intent_resolution.get(
                "intent_catalog"
            )
            if isinstance(intent_catalog, list):
                normalized_catalog_entries = len(
                    intent_catalog
                )

    resolution = result.get("intent_resolution_result")
    catalog_available = False
    catalog_entries_evaluated = -1
    catalog_used = False
    catalog_contributed_score = False

    if isinstance(resolution, Mapping):
        catalog_diagnostic = resolution.get(
            "intent_catalog"
        )
        if isinstance(catalog_diagnostic, Mapping):
            catalog_available = bool(
                catalog_diagnostic.get("available", False)
            )
            raw_entries = catalog_diagnostic.get(
                "entries_evaluated",
                -1,
            )
            if (
                isinstance(raw_entries, int)
                and not isinstance(raw_entries, bool)
            ):
                catalog_entries_evaluated = raw_entries
            catalog_used = bool(
                catalog_diagnostic.get(
                    "used_for_selected_intent",
                    False,
                )
            )
            catalog_contributed_score = bool(
                catalog_diagnostic.get(
                    "contributed_score_to_selected_intent",
                    False,
                )
            )

    checks = {
        "final_status_processing": (
            final_status == "processing"
        ),
        "current_stage_classify_intent": (
            current_stage == "classify_intent"
        ),
        "intent_matches": intent == expected_intent,
        "confidence_present": (
            isinstance(confidence, (int, float))
            and not isinstance(confidence, bool)
        ),
        "context_version_matches": (
            context_version == expected_context_version
        ),
        "context_fingerprint_matches": (
            context_fingerprint
            == expected_context_fingerprint
        ),
        "normalized_catalog_entries_match": (
            normalized_catalog_entries
            == expected_catalog_entries
        ),
        "catalog_available": catalog_available,
        "catalog_entries_evaluated_match": (
            catalog_entries_evaluated
            == expected_catalog_entries
        ),
        "catalog_used_for_selected_intent": (
            catalog_used
        ),
        "catalog_contributed_score": (
            catalog_contributed_score
        ),
    }

    print()
    print("=" * 70)
    print("ASSERTIONS")
    print("=" * 70)

    for name, passed in checks.items():
        print(f"- {name}={passed}")

    if all(checks.values()):
        print("LANGGRAPH_POSTGRES_INTENT_CATALOG: OK")
        return 0

    print("LANGGRAPH_POSTGRES_INTENT_CATALOG: FALHOU")
    return 8


def main() -> int:
    print("=" * 70)
    print(
        "POSTGRES INTENT GRAPH LIVE CHECK — CAMPOS SEPARADOS"
    )
    print("=" * 70)
    print(
        "Teste somente leitura. "
        "A senha e a conexão completa não serão exibidas."
    )
    print(
        "O grafo será executado somente até classify_intent. "
        "Nenhuma SQL será gerada ou executada."
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
        expected_context_fingerprint = _required_input(
            "EXPECTED_CONTEXT_FINGERPRINT"
        )
        expected_intent = _required_input(
            "EXPECTED_INTENT"
        )
        expected_catalog_entries = _positive_integer_input(
            "EXPECTED_INTENT_CATALOG_ENTRIES",
            default=1,
        )

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
            connect_timeout_seconds=(
                connect_timeout_seconds
            ),
        ):
            return 3

        runtime_environment = {
            "POSTGRES_DSN": dsn,
            "SEMANTIC_AGENT_VERSION": (
                semantic_agent_version
            ),
            "POSTGRES_CONNECT_TIMEOUT_SECONDS": str(
                connect_timeout_seconds
            ),
        }

        graph = create_postgres_context_graph(
            runtime_environment
        )

        initial_state: GraphState = {
            "question": question,
            "user": {
                "id": LIVE_TEST_USER_ID,
                "email": LIVE_TEST_USER_EMAIL,
                "profile": LIVE_TEST_USER_PROFILE,
            },
            "options": {
                "use_cache": False,
                "max_repair_attempts": 2,
                "shadow_mode": True,
            },
        }

        result = graph.invoke(
            initial_state,
            config={
                "recursion_limit": 10,
            },
        )

        _print_safe_graph_summary(result)

        return _result_exit_code(
            result,
            expected_context_version=(
                semantic_agent_version
            ),
            expected_context_fingerprint=(
                expected_context_fingerprint
            ),
            expected_intent=expected_intent,
            expected_catalog_entries=(
                expected_catalog_entries
            ),
        )

    except RuntimeConfigError as error:
        print()
        print(f"CONFIGURACAO: ERRO — {error}")
        return 2

    except ValueError as error:
        print()
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
