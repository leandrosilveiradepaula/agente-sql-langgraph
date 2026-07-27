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
) -> int:
    final_status = result.get("final_status")
    current_stage = result.get("current_stage")
    intent = result.get("intent")
    confidence = result.get("intent_confidence")

    if (
        final_status == "processing"
        and current_stage == "classify_intent"
        and isinstance(intent, str)
        and bool(intent.strip())
        and isinstance(confidence, (int, float))
        and not isinstance(confidence, bool)
    ):
        print("CLASSIFICACAO_INTENCAO: OK")
        return 0

    if (
        final_status == "rejected"
        and current_stage == "classify_intent"
    ):
        print("CLASSIFICACAO_INTENCAO: NAO_RESOLVIDA")
        return 7

    if final_status == "invalid_request":
        print("CLASSIFICACAO_INTENCAO: ENTRADA_INVALIDA")
        return 5

    if final_status == "infrastructure_error":
        print(
            "CLASSIFICACAO_INTENCAO: "
            "ERRO_DE_INFRAESTRUTURA"
        )
        return 4

    print("CLASSIFICACAO_INTENCAO: RESULTADO_INESPERADO")
    return 6


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

        return _result_exit_code(result)

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
