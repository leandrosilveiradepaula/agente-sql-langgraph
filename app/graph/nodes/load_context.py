from collections.abc import Callable

from app.graph.state import AgentError, GraphState
from app.ports.context_repository import (
    ContextRepository,
    ContextRepositoryError,
)


def create_load_context_node(
    repository: ContextRepository,
) -> Callable[[GraphState], GraphState]:
    """
    Cria o node load_context com seu repositório injetado.

    O node não conhece Supabase, Postgres ou arquivos.
    Ele conhece somente o contrato ContextRepository.
    """

    def load_context(state: GraphState) -> GraphState:
        """
        Carrega e valida o contexto ativo do agente.
        """

        user = state.get("user", {})
        user_profile = user.get("profile", "")

        try:
            context = repository.load_active_context(
                user_profile=user_profile,
            )

        except ContextRepositoryError as error:
            agent_error: AgentError = {
                "code": "CONTEXT_LOAD_FAILED",
                "message": str(error),
                "source": "context_repository",
                "stage": "load_context",
                "repairable": False,
                "details": {},
            }

            return {
                "errors": [
                    *state.get("errors", []),
                    agent_error,
                ],
                "current_stage": "load_context",
                "final_status": "infrastructure_error",
                "failure_stage": "load_context",
            }

        except Exception as error:
            agent_error = {
                "code": "UNEXPECTED_CONTEXT_LOAD_ERROR",
                "message": (
                    "Ocorreu um erro inesperado ao carregar "
                    "o contexto do agente."
                ),
                "source": "context_repository",
                "stage": "load_context",
                "repairable": False,
                "details": {
                    "exception_type": type(error).__name__,
                },
            }

            return {
                "errors": [
                    *state.get("errors", []),
                    agent_error,
                ],
                "current_stage": "load_context",
                "final_status": "infrastructure_error",
                "failure_stage": "load_context",
            }

        context_version = context.get("version", "")
        allowed_schemas = context.get(
            "allowed_schemas",
            [],
        )
        tables = context.get("tables", [])

        missing_fields: list[str] = []

        if not context_version:
            missing_fields.append("version")

        if not isinstance(allowed_schemas, list):
            missing_fields.append("allowed_schemas")

        elif not allowed_schemas:
            missing_fields.append("allowed_schemas")

        if not isinstance(tables, list):
            missing_fields.append("tables")

        elif not tables:
            missing_fields.append("tables")

        if missing_fields:
            agent_error = {
                "code": "INVALID_CONTEXT_SNAPSHOT",
                "message": (
                    "O contexto carregado está incompleto "
                    "ou possui formato inválido."
                ),
                "source": "context_repository",
                "stage": "load_context",
                "repairable": False,
                "details": {
                    "missing_or_invalid_fields": (
                        missing_fields
                    ),
                },
            }

            return {
                "errors": [
                    *state.get("errors", []),
                    agent_error,
                ],
                "current_stage": "load_context",
                "final_status": "infrastructure_error",
                "failure_stage": "load_context",
            }

        return {
            "context": context,
            "context_version": context_version,
            "current_stage": "load_context",
            "final_status": "processing",
            "failure_stage": "",
        }

    return load_context