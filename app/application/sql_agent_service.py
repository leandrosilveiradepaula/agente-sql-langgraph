from __future__ import annotations

from collections.abc import Callable, Mapping
from copy import deepcopy
from typing import Any

from app.application.application_request_types import (
    APPLICATION_REQUEST_CONTRACT_VERSION,
    ApplicationRequest,
    ApplicationRequestDiagnostic,
    ApplicationRequestOptions,
    ApplicationRequestUser,
    ApplicationServiceLimits,
)
from app.domain.application_response import (
    default_application_response_limits,
)
from app.domain.application_response_types import (
    APPLICATION_RESPONSE_CONTRACT_VERSION,
    ApplicationResponse,
    ApplicationResponseError,
    ApplicationResponseStatus,
)
from app.domain.result_normalization import stable_fingerprint
from app.domain.run_record import default_finalization_limits
from app.ports.graph_runtime import GraphRuntime


IdGenerator = Callable[[], str]

_TOP_LEVEL_KEYS = {
    "contract_version",
    "question",
    "request_id",
    "run_id",
    "user",
    "options",
    "correlation_id",
    "client_request_id",
    "metadata",
}
_USER_KEYS = {"id", "email", "profile", "organization_id"}
_OPTIONS_KEYS = {
    "use_cache",
    "max_repair_attempts",
    "shadow_mode",
    "sql_execution_limits",
    "result_normalization_limits",
    "run_finalization_limits",
    "application_response_limits",
    "execution_attempt",
    "timeout_seconds",
}
_SAFE_TEXT_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._:@/+ -"
)
_SAFE_ID_CHARS = set(
    "abcdefghijklmnopqrstuvwxyz"
    "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    "0123456789"
    "._:-"
)


def default_application_service_limits() -> ApplicationServiceLimits:
    return {
        "max_question_bytes": 16_384,
        "max_user_id_length": 128,
        "max_email_length": 254,
        "max_profile_length": 64,
        "max_organization_id_length": 128,
        "max_metadata_entries": 16,
        "max_metadata_key_length": 64,
        "max_metadata_value_length": 256,
        "max_request_id_length": 128,
        "max_run_id_length": 128,
        "max_correlation_id_length": 128,
        "max_client_request_id_length": 128,
    }


def validate_application_service_limits(
    limits: Mapping[str, Any],
) -> ApplicationServiceLimits:
    defaults = default_application_service_limits()
    output: dict[str, int] = {}
    for key, maximum in {
        "max_question_bytes": 1_000_000,
        "max_user_id_length": 512,
        "max_email_length": 512,
        "max_profile_length": 256,
        "max_organization_id_length": 512,
        "max_metadata_entries": 100,
        "max_metadata_key_length": 256,
        "max_metadata_value_length": 2_000,
        "max_request_id_length": 512,
        "max_run_id_length": 512,
        "max_correlation_id_length": 512,
        "max_client_request_id_length": 512,
    }.items():
        value = limits.get(key, defaults[key])
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError(f"Limite {key} deve ser inteiro.")
        if value <= 0 or value > maximum:
            raise ValueError(f"Limite {key} fora da faixa permitida.")
        output[key] = value
    return output  # type: ignore[return-value]


def default_application_request_options() -> ApplicationRequestOptions:
    return {
        "use_cache": False,
        "max_repair_attempts": 2,
        "shadow_mode": False,
        "sql_execution_limits": {
            "timeout_seconds": 10,
            "max_rows": 5,
            "max_response_bytes": 4096,
            "max_cell_bytes": 128,
        },
        "run_finalization_limits": default_finalization_limits(),
        "application_response_limits": default_application_response_limits(),
        "execution_attempt": 1,
    }


def build_initial_graph_state(
    request: ApplicationRequest,
    *,
    request_id: str,
    run_id: str,
    options: ApplicationRequestOptions,
    user: ApplicationRequestUser,
) -> dict[str, object]:
    return {
        "question": str(request["question"]),
        "request_id": request_id,
        "run_id": run_id,
        "user": deepcopy(user),
        "options": deepcopy(options),
    }


def validate_application_request(
    request: object,
    *,
    limits: Mapping[str, Any] | None = None,
) -> list[ApplicationRequestDiagnostic]:
    safe_limits = validate_application_service_limits(limits or {})
    return deepcopy(_validate_request(request, safe_limits))


class SqlAgentApplicationService:
    def __init__(
        self,
        *,
        runtime: GraphRuntime,
        id_generator: IdGenerator,
        limits: Mapping[str, Any] | None = None,
    ) -> None:
        if runtime is None or not callable(getattr(runtime, "invoke", None)):
            raise RuntimeError("runtime deve ser injetado explicitamente.")
        if id_generator is None or not callable(id_generator):
            raise RuntimeError("id_generator deve ser injetado explicitamente.")
        self._runtime = runtime
        self._id_generator = id_generator
        self._limits = validate_application_service_limits(limits or {})

    def execute(
        self,
        request: ApplicationRequest,
    ) -> ApplicationResponse:
        request_id = ""
        run_id = ""
        try:
            copied_request = deepcopy(request)
            validation = _validate_request(copied_request, self._limits)
            request_id = _resolve_id_for_response(
                copied_request.get("request_id"),
                self._id_generator,
                self._limits["max_request_id_length"],
            )
            run_id = _resolve_id_for_response(
                copied_request.get("run_id"),
                self._id_generator,
                self._limits["max_run_id_length"],
            )
            if request_id == run_id:
                validation.append(
                    _diagnostic(
                        "APPLICATION_REQUEST_ID_INVALID",
                        "run_id",
                        "Identificadores invalidos.",
                    )
                )
            if validation:
                return _minimal_response(
                    request_id=request_id,
                    run_id=run_id,
                    status="rejected",
                    code=validation[0]["code"],
                    field=validation[0].get("field", "request"),
                )
            options = _validated_options(copied_request.get("options", {}))
            user = _validated_user(copied_request.get("user", {}), self._limits)
            initial_state = build_initial_graph_state(
                copied_request,
                request_id=request_id,
                run_id=run_id,
                options=options,
                user=user,
            )
            final_state = self._runtime.invoke(deepcopy(initial_state))
            response = _extract_application_response(
                final_state,
                request_id=request_id,
                run_id=run_id,
            )
            return deepcopy(response)
        except ApplicationServiceGraphResultError:
            return _minimal_response(
                request_id=request_id,
                run_id=run_id,
                status="infrastructure_error",
                code="APPLICATION_SERVICE_INVALID_GRAPH_RESULT",
                field="runtime",
            )
        except Exception:
            return _minimal_response(
                request_id=request_id,
                run_id=run_id,
                status="infrastructure_error",
                code="APPLICATION_SERVICE_RUNTIME_FAILED",
                field="runtime",
            )


class ApplicationServiceGraphResultError(ValueError):
    pass


def _validate_request(
    request: object,
    limits: ApplicationServiceLimits,
) -> list[ApplicationRequestDiagnostic]:
    diagnostics: list[ApplicationRequestDiagnostic] = []
    if not isinstance(request, Mapping):
        return [
            _diagnostic(
                "APPLICATION_REQUEST_INVALID",
                "request",
                "Requisicao invalida.",
            )
        ]
    for key in request:
        if key not in _TOP_LEVEL_KEYS:
            diagnostics.append(
                _diagnostic(
                    "APPLICATION_REQUEST_INVALID",
                    str(key),
                    "Campo desconhecido.",
                )
            )
    question = request.get("question")
    if not isinstance(question, str):
        diagnostics.append(
            _diagnostic(
                "APPLICATION_REQUEST_QUESTION_REQUIRED",
                "question",
                "Pergunta obrigatoria.",
            )
        )
    elif not question.strip():
        diagnostics.append(
            _diagnostic(
                "APPLICATION_REQUEST_QUESTION_REQUIRED",
                "question",
                "Pergunta obrigatoria.",
            )
        )
    elif len(question.encode("utf-8")) > limits["max_question_bytes"]:
        diagnostics.append(
            _diagnostic(
                "APPLICATION_REQUEST_QUESTION_TOO_LARGE",
                "question",
                "Pergunta excede limite.",
            )
        )
    elif _has_control_character(question):
        diagnostics.append(
            _diagnostic(
                "APPLICATION_REQUEST_CONTROL_CHARACTER",
                "question",
                "Pergunta contem caractere de controle.",
            )
        )
    for field, max_length in [
        ("request_id", limits["max_request_id_length"]),
        ("run_id", limits["max_run_id_length"]),
        ("correlation_id", limits["max_correlation_id_length"]),
        ("client_request_id", limits["max_client_request_id_length"]),
    ]:
        value = request.get(field)
        if value is not None and not _valid_identifier(value, max_length):
            diagnostics.append(
                _diagnostic(
                    "APPLICATION_REQUEST_ID_INVALID",
                    field,
                    "Identificador invalido.",
                )
            )
    try:
        _validated_user(request.get("user", {}), limits)
    except ValueError:
        diagnostics.append(
            _diagnostic(
                "APPLICATION_REQUEST_USER_INVALID",
                "user",
                "Usuario invalido.",
            )
        )
    try:
        _validated_options(request.get("options", {}))
    except ValueError:
        diagnostics.append(
            _diagnostic(
                "APPLICATION_REQUEST_OPTIONS_INVALID",
                "options",
                "Opcoes invalidas.",
            )
        )
    try:
        _validated_metadata(request.get("metadata", {}), limits)
    except ValueError:
        diagnostics.append(
            _diagnostic(
                "APPLICATION_REQUEST_INVALID",
                "metadata",
                "Metadata invalida.",
            )
        )
    return diagnostics


def _validated_user(
    user: object,
    limits: ApplicationServiceLimits,
) -> ApplicationRequestUser:
    if user is None:
        return {}
    if not isinstance(user, Mapping):
        raise ValueError("Usuario invalido.")
    output: ApplicationRequestUser = {}
    for key in user:
        if key not in _USER_KEYS:
            raise ValueError("Campo de usuario desconhecido.")
    for key, max_length in [
        ("id", limits["max_user_id_length"]),
        ("profile", limits["max_profile_length"]),
        ("organization_id", limits["max_organization_id_length"]),
    ]:
        value = user.get(key)
        if value is None:
            continue
        if not _valid_safe_text(value, max_length):
            raise ValueError("Campo de usuario invalido.")
        output[key] = str(value)  # type: ignore[literal-required]
    email = user.get("email")
    if email is not None:
        if not _valid_email(email, limits["max_email_length"]):
            raise ValueError("Email invalido.")
        output["email"] = str(email)
    return output


def _validated_options(options: object) -> ApplicationRequestOptions:
    if options is None:
        return default_application_request_options()
    if not isinstance(options, Mapping):
        raise ValueError("Opcoes invalidas.")
    for key in options:
        if key not in _OPTIONS_KEYS:
            raise ValueError("Opcao desconhecida.")
    output = default_application_request_options()
    for key in ("use_cache", "shadow_mode"):
        if key in options:
            value = options[key]
            if not isinstance(value, bool):
                raise ValueError("Opcao booleana invalida.")
            output[key] = value  # type: ignore[literal-required]
    if "max_repair_attempts" in options:
        value = options["max_repair_attempts"]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("max_repair_attempts invalido.")
        if value < 0 or value > 2:
            raise ValueError("max_repair_attempts fora da faixa.")
        output["max_repair_attempts"] = value
    if "execution_attempt" in options:
        value = options["execution_attempt"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("execution_attempt invalido.")
        output["execution_attempt"] = value
    if "timeout_seconds" in options:
        value = options["timeout_seconds"]
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError("timeout_seconds invalido.")
        output["timeout_seconds"] = value
    for key in [
        "sql_execution_limits",
        "result_normalization_limits",
        "run_finalization_limits",
        "application_response_limits",
    ]:
        if key in options:
            value = options[key]
            if not _int_mapping(value):
                raise ValueError("Limites invalidos.")
            output[key] = deepcopy(value)  # type: ignore[literal-required]
    return output


def _validated_metadata(
    metadata: object,
    limits: ApplicationServiceLimits,
) -> dict[str, str | int | bool | None]:
    if metadata is None:
        return {}
    if not isinstance(metadata, Mapping):
        raise ValueError("Metadata invalida.")
    if len(metadata) > limits["max_metadata_entries"]:
        raise ValueError("Metadata excessiva.")
    output: dict[str, str | int | bool | None] = {}
    for key, value in metadata.items():
        if not _valid_identifier(key, limits["max_metadata_key_length"]):
            raise ValueError("Chave de metadata invalida.")
        if value is None or isinstance(value, bool):
            output[str(key)] = value
        elif isinstance(value, int) and not isinstance(value, bool):
            output[str(key)] = value
        elif isinstance(value, str) and _valid_safe_text(
            value,
            limits["max_metadata_value_length"],
        ):
            output[str(key)] = value
        else:
            raise ValueError("Valor de metadata invalido.")
    return output


def _resolve_id_for_response(
    value: object,
    id_generator: IdGenerator,
    max_length: int,
) -> str:
    if value is None:
        generated = id_generator()
        if not _valid_identifier(generated, max_length):
            raise ValueError("Identificador gerado invalido.")
        return generated
    return str(value) if _valid_identifier(value, max_length) else ""


def _extract_application_response(
    final_state: object,
    *,
    request_id: str,
    run_id: str,
) -> ApplicationResponse:
    if not isinstance(final_state, Mapping) or not final_state:
        raise ApplicationServiceGraphResultError("Estado final invalido.")
    response = final_state.get("application_response")
    if not isinstance(response, Mapping):
        raise ApplicationServiceGraphResultError("ApplicationResponse ausente.")
    _validate_application_response(response, request_id=request_id, run_id=run_id)
    return deepcopy(dict(response))  # type: ignore[return-value]


def _validate_application_response(
    response: Mapping[str, Any],
    *,
    request_id: str,
    run_id: str,
) -> None:
    if response.get("contract_version") != APPLICATION_RESPONSE_CONTRACT_VERSION:
        raise ApplicationServiceGraphResultError("Contrato de resposta invalido.")
    if response.get("request_id") != request_id:
        raise ApplicationServiceGraphResultError("request_id divergente.")
    if response.get("run_id") != run_id:
        raise ApplicationServiceGraphResultError("run_id divergente.")
    if response.get("status") not in {
        "success",
        "rejected",
        "infrastructure_error",
    }:
        raise ApplicationServiceGraphResultError("Status invalido.")
    if not _valid_identifier(response.get("response_id"), 128):
        raise ApplicationServiceGraphResultError("response_id invalido.")
    fingerprint = response.get("response_fingerprint")
    if not _valid_identifier(fingerprint, 128):
        raise ApplicationServiceGraphResultError("Fingerprint ausente.")
    payload = deepcopy(dict(response))
    payload.pop("response_fingerprint", None)
    if stable_fingerprint(payload) != fingerprint:
        raise ApplicationServiceGraphResultError("Fingerprint divergente.")
    if response.get("status") != "success" and response.get("data") is not None:
        raise ApplicationServiceGraphResultError("Data inconsistente.")
    if not isinstance(response.get("finalization"), Mapping):
        raise ApplicationServiceGraphResultError("Finalizacao ausente.")


def _minimal_response(
    *,
    request_id: str,
    run_id: str,
    status: ApplicationResponseStatus,
    code: str,
    field: str,
) -> ApplicationResponse:
    outcome = status
    error: ApplicationResponseError = {
        "code": _safe_code(code),
        "category": "application_service",
        "stage": "application_service",
        "field": _safe_code(field).lower(),
        "message": (
            "A requisicao nao pode ser processada."
            if status == "rejected"
            else "O processamento nao pode ser concluido."
        ),
        "retryable": status == "infrastructure_error",
    }
    response: ApplicationResponse = {
        "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
        "response_id": stable_fingerprint(
            {
                "contract_version": APPLICATION_RESPONSE_CONTRACT_VERSION,
                "request_id": request_id,
                "run_id": run_id,
                "source": "application_service",
            }
        ),
        "request_id": request_id,
        "run_id": run_id,
        "status": status,
        "original_outcome": outcome,
        "message": (
            "A solicitacao nao pode ser processada."
            if status == "rejected"
            else "O processamento nao pode ser concluido."
        ),
        "data": None,
        "errors": [error],
        "warnings": [],
        "metadata": {
            "persisted": False,
            "audited": False,
            "observability_degraded": False,
            "original_outcome": outcome,
            "finalization_status": "incomplete",
            "contract_versions": {
                "application_request": APPLICATION_REQUEST_CONTRACT_VERSION,
                "application_response": APPLICATION_RESPONSE_CONTRACT_VERSION,
            },
            "lineage": {},
        },
        "finalization": {
            "status": "incomplete",
            "run_record_built": False,
            "persisted": False,
            "persistence_record_id": None,
            "audited": False,
            "audit_event_id": None,
            "observability_emitted": False,
            "observability_degraded": False,
            "error_codes": [_safe_code(code)],
        },
        "response_fingerprint": "",
    }
    payload = deepcopy(response)
    payload.pop("response_fingerprint", None)
    response["response_fingerprint"] = stable_fingerprint(payload)
    return deepcopy(response)


def _diagnostic(
    code: str,
    field: str,
    message: str,
) -> ApplicationRequestDiagnostic:
    return {
        "code": code,  # type: ignore[typeddict-item]
        "field": field,
        "message": message,
    }


def _has_control_character(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)


def _valid_identifier(value: object, max_length: int) -> bool:
    if not isinstance(value, str) or not value or len(value) > max_length:
        return False
    return all(char in _SAFE_ID_CHARS for char in value)


def _valid_safe_text(value: object, max_length: int) -> bool:
    if not isinstance(value, str) or not value or len(value) > max_length:
        return False
    if _has_control_character(value):
        return False
    return all(char in _SAFE_TEXT_CHARS for char in value)


def _valid_email(value: object, max_length: int) -> bool:
    if not _valid_safe_text(value, max_length):
        return False
    text = str(value)
    return text.count("@") == 1 and "." in text.split("@", 1)[1]


def _int_mapping(value: object) -> bool:
    if not isinstance(value, Mapping):
        return False
    for item in value.values():
        if isinstance(item, bool):
            return False
        if isinstance(item, int):
            continue
        if isinstance(item, Mapping):
            if not _int_mapping(item):
                return False
            continue
        return False
    return True


def _safe_code(value: object) -> str:
    text = str(value or "").upper()
    return "".join(
        char if char.isalnum() or char == "_" else "_"
        for char in text
    )[:96] or "UNKNOWN_ERROR"
