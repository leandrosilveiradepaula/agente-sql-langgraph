from uuid import uuid4

from app.graph.state import AgentError, GraphState


def receive_question(state: GraphState) -> GraphState:
    """
    Recebe e prepara a entrada inicial do grafo.

    Este node:
    - normaliza somente o texto;
    - cria os identificadores da execução;
    - inicializa os controles;
    - valida pergunta e limite de repairs.

    Não interpreta regras financeiras.
    Não gera SQL.
    Não chama inteligência artificial.
    """

    raw_question = state.get("question", "")
    errors: list[AgentError] = []

    if not isinstance(raw_question, str):
        question = ""
        normalized_question = ""

        errors.append(
            {
                "code": "INVALID_QUESTION_TYPE",
                "message": "A pergunta deve ser um texto.",
                "source": "langgraph",
                "stage": "receive_question",
                "repairable": False,
                "details": {
                    "received_type": type(raw_question).__name__,
                },
            }
        )
    else:
        question = raw_question.strip()
        normalized_question = " ".join(question.split())

    if not normalized_question:
        errors.append(
            {
                "code": "EMPTY_QUESTION",
                "message": "A pergunta não pode estar vazia.",
                "source": "langgraph",
                "stage": "receive_question",
                "repairable": False,
                "details": {},
            }
        )

    received_options = state.get("options", {})

    use_cache = received_options.get("use_cache", False)
    shadow_mode = received_options.get("shadow_mode", False)
    sql_execution_limits = received_options.get("sql_execution_limits")
    result_normalization_limits = received_options.get(
        "result_normalization_limits"
    )
    execution_attempt = received_options.get("execution_attempt", 1)
    max_repair_attempts = received_options.get(
        "max_repair_attempts",
        2,
    )

    if (
        not isinstance(max_repair_attempts, int)
        or isinstance(max_repair_attempts, bool)
        or max_repair_attempts < 0
        or max_repair_attempts > 2
    ):
        errors.append(
            {
                "code": "INVALID_MAX_REPAIR_ATTEMPTS",
                "message": (
                    "max_repair_attempts deve ser um número "
                    "inteiro entre 0 e 2."
                ),
                "source": "langgraph",
                "stage": "receive_question",
                "repairable": False,
                "details": {
                    "received_value": max_repair_attempts,
                },
            }
        )

        max_repair_attempts = 2

    has_errors = len(errors) > 0

    return {
        "request_id": state.get(
            "request_id",
            str(uuid4()),
        ),
        "run_id": state.get(
            "run_id",
            str(uuid4()),
        ),
        "question": question,
        "normalized_question": normalized_question,
        "options": {
            "use_cache": bool(use_cache),
            "max_repair_attempts": max_repair_attempts,
            "shadow_mode": bool(shadow_mode),
            **(
                {"sql_execution_limits": sql_execution_limits}
                if isinstance(sql_execution_limits, dict)
                else {}
            ),
            **(
                {"result_normalization_limits": result_normalization_limits}
                if isinstance(result_normalization_limits, dict)
                else {}
            ),
            **(
                {"execution_attempt": execution_attempt}
                if isinstance(execution_attempt, int)
                and not isinstance(execution_attempt, bool)
                else {}
            ),
        },
        "repair_attempts": 0,
        "max_repair_attempts": max_repair_attempts,
        "repair_history": [],
        "security_result": {
            "status": "not_run",
            "errors": [],
            "warnings": [],
        },
        "contract_result": {
            "status": "not_run",
            "errors": [],
            "warnings": [],
        },
        "engine_preflight_result": {
            "status": "not_run",
            "errors": [],
            "warnings": [],
        },
        "sql_execution_result": None,
        "normalized_result": None,
        "serialized_result": None,
        "errors": errors,
        "warnings": [],
        "current_stage": "receive_question",
        "final_status": (
            "invalid_request"
            if has_errors
            else "processing"
        ),
        "failure_stage": (
            "receive_question"
            if has_errors
            else ""
        ),
    }
