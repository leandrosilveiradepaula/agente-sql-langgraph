from __future__ import annotations

from copy import deepcopy

from app.application.sql_agent_service import (
    build_initial_graph_state,
    default_application_request_options,
    default_application_service_limits,
    validate_application_request,
)


def _valid_request(**overrides):
    request = {
        "question": "  Pergunta generica valida?  ",
        "request_id": "request-1",
        "run_id": "run-1",
        "user": {
            "id": "user-1",
            "email": "user@example.invalid",
            "profile": "admin",
        },
        "options": {
            "use_cache": False,
            "max_repair_attempts": 2,
            "shadow_mode": False,
        },
        "correlation_id": "corr-1",
        "client_request_id": "client-1",
        "metadata": {"source": "local-test", "attempt": 1},
    }
    request.update(overrides)
    return request


def _codes(request):
    return [item["code"] for item in validate_application_request(request)]


def test_request_valida_minima() -> None:
    assert validate_application_request({"question": "Pergunta valida"}) == []


def test_request_valida_completa() -> None:
    assert validate_application_request(_valid_request()) == []


def test_pergunta_ausente_vazia_e_whitespace() -> None:
    assert "APPLICATION_REQUEST_QUESTION_REQUIRED" in _codes({})
    assert "APPLICATION_REQUEST_QUESTION_REQUIRED" in _codes(
        {"question": ""}
    )
    assert "APPLICATION_REQUEST_QUESTION_REQUIRED" in _codes(
        {"question": "   "}
    )


def test_pergunta_acima_do_limite_e_multibyte_no_limite() -> None:
    limits = {**default_application_service_limits(), "max_question_bytes": 4}
    assert validate_application_request(
        {"question": "áá"},
        limits=limits,
    ) == []
    assert "APPLICATION_REQUEST_QUESTION_TOO_LARGE" in [
        item["code"]
        for item in validate_application_request(
            {"question": "ááa"},
            limits=limits,
        )
    ]


def test_caractere_de_controle() -> None:
    assert "APPLICATION_REQUEST_CONTROL_CHARACTER" in _codes(
        {"question": "texto\nquebrado"}
    )


def test_request_id_e_run_id_validos_e_invalidos() -> None:
    assert validate_application_request(
        {"question": "Pergunta", "request_id": "req-1", "run_id": "run-1"}
    ) == []
    assert "APPLICATION_REQUEST_ID_INVALID" in _codes(
        {"question": "Pergunta", "request_id": "req com espaco"}
    )
    assert "APPLICATION_REQUEST_ID_INVALID" in _codes(
        {"question": "Pergunta", "run_id": "run/com/barra"}
    )


def test_user_valido_invalido_e_email_estrutural() -> None:
    assert validate_application_request(
        {
            "question": "Pergunta",
            "user": {
                "id": "user-1",
                "email": "user@example.invalid",
                "profile": "viewer",
                "organization_id": "org-1",
            },
        }
    ) == []
    assert "APPLICATION_REQUEST_USER_INVALID" in _codes(
        {"question": "Pergunta", "user": {"token": "secret"}}
    )
    assert "APPLICATION_REQUEST_USER_INVALID" in _codes(
        {"question": "Pergunta", "user": {"email": "invalid"}}
    )


def test_options_validas_tipo_invalido_faixa_invalida() -> None:
    assert validate_application_request(
        {
            "question": "Pergunta",
            "options": {
                "use_cache": True,
                "max_repair_attempts": 1,
                "shadow_mode": False,
                "execution_attempt": 1,
                "timeout_seconds": 2,
            },
        }
    ) == []
    assert "APPLICATION_REQUEST_OPTIONS_INVALID" in _codes(
        {"question": "Pergunta", "options": {"use_cache": "sim"}}
    )
    assert "APPLICATION_REQUEST_OPTIONS_INVALID" in _codes(
        {"question": "Pergunta", "options": {"max_repair_attempts": 3}}
    )
    assert "APPLICATION_REQUEST_OPTIONS_INVALID" in _codes(
        {
            "question": "Pergunta",
            "options": {
                "sql_execution_limits": {
                    "timeout_seconds": 10,
                    "max_rows": 0,
                    "max_response_bytes": 4096,
                    "max_cell_bytes": 128,
                }
            },
        }
    )
    assert "APPLICATION_REQUEST_OPTIONS_INVALID" in _codes(
        {
            "question": "Pergunta",
            "options": {
                "sql_execution_limits": {
                    "timeout_seconds": 10,
                    "max_rows": 5,
                    "max_response_bytes": 4096,
                    "max_cell_bytes": 128,
                    "extra": 1,
                }
            },
        }
    )
    assert "APPLICATION_REQUEST_OPTIONS_INVALID" in _codes(
        {
            "question": "Pergunta",
            "options": {
                "result_normalization_limits": {
                    "max_rows": 1,
                    "max_columns": 1,
                    "max_total_cells": 1,
                    "max_nesting_depth": 1,
                    "max_collection_items": 1,
                    "max_serialized_bytes": 1,
                    "max_diagnostic_entries": False,
                }
            },
        }
    )


def test_campo_desconhecido() -> None:
    assert "APPLICATION_REQUEST_INVALID" in _codes(
        {"question": "Pergunta", "context": {}}
    )


def test_metadata_valida_excessiva_e_objeto_arbitrario() -> None:
    assert validate_application_request(
        {"question": "Pergunta", "metadata": {"safe_key": "safe-value"}}
    ) == []
    limits = {**default_application_service_limits(), "max_metadata_entries": 1}
    assert "APPLICATION_REQUEST_INVALID" in [
        item["code"]
        for item in validate_application_request(
            {"question": "Pergunta", "metadata": {"a": 1, "b": 2}},
            limits=limits,
        )
    ]
    assert "APPLICATION_REQUEST_INVALID" in _codes(
        {"question": "Pergunta", "metadata": {"obj": object()}}
    )
    limits = {
        **default_application_service_limits(),
        "max_metadata_value_length": 4,
    }
    assert validate_application_request(
        {"question": "Pergunta", "metadata": {"safe_key": "áá"}},
        limits=limits,
    ) == []
    assert "APPLICATION_REQUEST_INVALID" in [
        item["code"]
        for item in validate_application_request(
            {"question": "Pergunta", "metadata": {"safe_key": "ááa"}},
            limits=limits,
        )
    ]


def test_nao_mutacao_copia_independente_e_determinismo() -> None:
    request = _valid_request()
    before = deepcopy(request)
    first = validate_application_request(request)
    second = validate_application_request(request)
    assert request == before
    assert first == second
    options = default_application_request_options()
    user = deepcopy(request["user"])
    state = build_initial_graph_state(
        request,
        request_id="request-1",
        run_id="run-1",
        options=options,
        user=user,
    )
    user["id"] = "changed"
    options["max_repair_attempts"] = 0
    assert state["user"]["id"] == "user-1"
    assert state["options"]["max_repair_attempts"] == 2


def main() -> None:
    tests = [
        test_request_valida_minima,
        test_request_valida_completa,
        test_pergunta_ausente_vazia_e_whitespace,
        test_pergunta_acima_do_limite_e_multibyte_no_limite,
        test_caractere_de_controle,
        test_request_id_e_run_id_validos_e_invalidos,
        test_user_valido_invalido_e_email_estrutural,
        test_options_validas_tipo_invalido_faixa_invalida,
        test_campo_desconhecido,
        test_metadata_valida_excessiva_e_objeto_arbitrario,
        test_nao_mutacao_copia_independente_e_determinismo,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
