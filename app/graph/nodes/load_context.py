from collections.abc import Callable

from app.domain.context_validator import (
    ContextValidationIssue,
    validate_context_snapshot,
)
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
    Ele recebe um snapshot canônico pelo ContextRepository e valida
    esse snapshot antes de disponibilizá-lo aos próximos estágios.
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

        validation_result = validate_context_snapshot(context)

        validation_errors = [
            _validation_issue_to_agent_error(issue)
            for issue in validation_result["errors"]
        ]
        validation_warnings = [
            _validation_issue_to_agent_error(issue)
            for issue in validation_result["warnings"]
        ]

        if validation_result["status"] == "invalid":
            return {
                "errors": [
                    *state.get("errors", []),
                    *validation_errors,
                ],
                "warnings": [
                    *state.get("warnings", []),
                    *validation_warnings,
                ],
                "current_stage": "load_context",
                "final_status": "infrastructure_error",
                "failure_stage": "load_context",
            }

        context_version = context["version"]

        return {
            "context": context,
            "context_version": context_version,
            "warnings": [
                *state.get("warnings", []),
                *validation_warnings,
            ],
            "current_stage": "load_context",
            "final_status": "processing",
            "failure_stage": "",
        }

    return load_context


def _validation_issue_to_agent_error(
    issue: ContextValidationIssue,
) -> AgentError:
    """
    Converte uma ocorrência do validador para o formato comum do grafo.
    """

    return {
        "code": issue["code"],
        "message": issue["message"],
        "source": "context_validator",
        "stage": "load_context",
        "repairable": False,
        "details": {
            "validation_path": issue["path"],
            **issue["details"],
        },
    }
