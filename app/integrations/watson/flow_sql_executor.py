from __future__ import annotations

from copy import deepcopy

from app.domain.sql_execution import (
    SqlExecutionProviderResult,
    SqlExecutionRequest,
)
from app.integrations.watson.configuration import (
    WATSON_FLOW_CONTRACT_VERSION,
    WatsonFlowConfiguration,
)
from app.integrations.watson.flow_contracts import watson_flow_run_request
from app.integrations.watson.flow_limits import WatsonFlowLimits
from app.integrations.watson.flow_response_normalizer import (
    normalize_watson_flow_response,
)
from app.integrations.watson.iam_contracts import iam_token_request
from app.integrations.watson.sql_transport import (
    build_watson_flow_payload,
    compact_sql_for_watson_transport,
)
from app.ports.iam_token_provider import IamTokenProvider
from app.ports.watson_flow_client import WatsonFlowClient


class WatsonFlowSqlExecutorAdapter:
    def __init__(
        self,
        *,
        configuration: WatsonFlowConfiguration,
        limits: WatsonFlowLimits,
        iam_token_provider: IamTokenProvider,
        flow_client: WatsonFlowClient,
    ) -> None:
        self._configuration = configuration
        self._limits = limits
        self._iam = iam_token_provider
        self._flow = flow_client

    def execute(
        self,
        request: SqlExecutionRequest,
    ) -> SqlExecutionProviderResult:
        sql = request.get("current_sql")
        if not isinstance(sql, str) or not sql.strip():
            return _execution_error(
                "SQL_EXECUTION_REQUEST_INVALID",
                "request_invalid",
                "Requisicao de execucao invalida.",
                status="rejected",
            )
        transport = compact_sql_for_watson_transport(sql, self._limits)
        if transport.status != "success" or transport.sql_transport is None:
            return _execution_error(
                "SQL_EXECUTION_PROVIDER_FAILED",
                "provider_failed",
                "SQL nao pode ser preparada para transporte Watson.",
            )
        token_result = self._iam.get_token(
            iam_token_request(
                request_id=request["request_id"],
                run_id=request["run_id"],
                timeout_seconds=request["limits"]["timeout_seconds"],
                audience="watson-flow-execution",
            )
        )
        if token_result.get("status") != "success":
            return _iam_failure(token_result.get("status"))
        token = token_result.get("token")
        try:
            flow_request = watson_flow_run_request(
                flow_id=self._configuration.flow_id,
                bearer_token=token,  # type: ignore[arg-type]
                payload=build_watson_flow_payload(transport.sql_transport),
                request_id=request["request_id"],
                run_id=request["run_id"],
                invocation_id=request["execution_id"],
                timeout_seconds=request["limits"]["timeout_seconds"],
                purpose="execution",
                limits=self._limits,
            )
            flow_result = self._flow.run_flow(deepcopy(flow_request))
        except Exception:
            return _execution_error(
                "SQL_EXECUTION_PROVIDER_FAILED",
                "provider_failed",
                "Watson Flow execution falhou.",
            )
        if flow_result.get("status") != "success":
            return _flow_failure(flow_result.get("status"))
        normalized = normalize_watson_flow_response(
            flow_result.get("raw_output"),
            "execution",
            self._limits,
        )
        if normalized.status == "success":
            return {
                "status": "success",
                "provider_name": "watson_flow_sql_executor",
                "provider_version": self._configuration.contract_version,
                "request_fingerprint": request["request_fingerprint"],
                "sql_fingerprint": request["sql_fingerprint"],
                "columns": deepcopy(normalized.columns),
                "rows": deepcopy(normalized.rows),
                "row_count": normalized.row_count,
                "duration_ms": normalized.duration_ms or flow_result.get("duration_ms") or 0,
                "truncated": normalized.truncated,
                "executed": True,
                "statement_type": "select",
                "warnings": [],
            }
        if normalized.status == "functional_error":
            return _execution_error(
                "SQL_EXECUTION_RESPONSE_INVALID",
                "response_invalid",
                "Watson Flow execution rejeitou a consulta.",
                status="rejected",
            )
        return _execution_error(
            "SQL_EXECUTION_RESPONSE_INVALID",
            "response_invalid",
            "Watson Flow execution retornou resposta invalida.",
            status="rejected",
        )


def _iam_failure(status: object) -> SqlExecutionProviderResult:
    mapping = {
        "authentication_failed": ("SQL_EXECUTION_AUTHENTICATION_FAILED", "authentication_failed"),
        "timeout": ("SQL_EXECUTION_TIMEOUT", "timeout"),
        "unavailable": ("SQL_EXECUTION_PROVIDER_FAILED", "provider_failed"),
        "invalid_response": ("SQL_EXECUTION_RESPONSE_INVALID", "response_invalid"),
    }
    code, category = mapping.get(status, ("SQL_EXECUTION_UNEXPECTED_ERROR", "unexpected_error"))
    return _execution_error(code, category, "IAM token provider falhou.")


def _flow_failure(status: object) -> SqlExecutionProviderResult:
    mapping = {
        "authentication_failed": ("SQL_EXECUTION_AUTHENTICATION_FAILED", "authentication_failed"),
        "timeout": ("SQL_EXECUTION_TIMEOUT", "timeout"),
        "unavailable": ("SQL_EXECUTION_PROVIDER_FAILED", "provider_failed"),
        "rate_limited": ("SQL_EXECUTION_PROVIDER_FAILED", "provider_failed"),
        "invalid_response": ("SQL_EXECUTION_RESPONSE_INVALID", "response_invalid"),
        "http_error": ("SQL_EXECUTION_PROVIDER_FAILED", "provider_failed"),
    }
    code, category = mapping.get(status, ("SQL_EXECUTION_UNEXPECTED_ERROR", "unexpected_error"))
    return _execution_error(code, category, "Watson Flow falhou.")


def _execution_error(
    code: str,
    category: str,
    message: str,
    *,
    status: str = "error",
) -> SqlExecutionProviderResult:
    return {
        "status": status,  # type: ignore[typeddict-item]
        "provider_name": "watson_flow_sql_executor",
        "provider_version": WATSON_FLOW_CONTRACT_VERSION,
        "failure_category": category,  # type: ignore[typeddict-item]
        "error_code": code,  # type: ignore[typeddict-item]
        "message": message,
        "executed": False,
        "warnings": [],
    }
