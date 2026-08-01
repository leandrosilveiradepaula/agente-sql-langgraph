from __future__ import annotations

from copy import deepcopy

from app.domain.engine_preflight import (
    EnginePreflightProviderResult,
    EnginePreflightRequest,
)
from app.integrations.watson.configuration import WatsonFlowConfiguration
from app.integrations.watson.flow_contracts import (
    watson_flow_run_request,
)
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


class WatsonFlowEnginePreflightAdapter:
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

    def preflight(
        self,
        request: EnginePreflightRequest,
    ) -> EnginePreflightProviderResult:
        sql = request.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            return _preflight_error(
                "ENGINE_PREFLIGHT_REQUEST_INVALID",
                "adapter_error",
                "Requisicao de preflight invalida.",
            )
        transport = compact_sql_for_watson_transport(sql, self._limits)
        if transport.status != "success" or transport.sql_transport is None:
            return _preflight_error(
                "ENGINE_PREFLIGHT_PROVIDER_FAILED",
                "adapter_error",
                "SQL nao pode ser preparada para transporte Watson.",
            )
        token_result = self._iam.get_token(
            iam_token_request(
                request_id=str(request.get("request_fingerprint", "")),
                run_id=str(request.get("query_plan_fingerprint", "")),
                timeout_seconds=max(1, int(request.get("timeout_ms", 1000)) // 1000),
                audience="watson-flow-preflight",
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
                request_id=str(request.get("request_fingerprint", "")),
                run_id=str(request.get("query_plan_fingerprint", "")),
                invocation_id=f"preflight-{request.get('request_fingerprint', '')}",
                timeout_seconds=self._configuration.request_timeout_seconds,
                purpose="preflight",
                limits=self._limits,
            )
            flow_result = self._flow.run_flow(deepcopy(flow_request))
        except Exception:
            return _preflight_error(
                "ENGINE_PREFLIGHT_PROVIDER_FAILED",
                "adapter_error",
                "Watson Flow preflight falhou.",
            )
        if flow_result.get("status") != "success":
            return _flow_failure(flow_result.get("status"))
        normalized = normalize_watson_flow_response(
            flow_result.get("raw_output"),
            "preflight",
            self._limits,
        )
        if normalized.status == "success":
            return {
                "status": "approved",
                "provider_name": "watson_flow_preflight",
                "provider_version": self._configuration.contract_version,
                "duration_ms": normalized.duration_ms or flow_result.get("duration_ms") or 0,
                "statement_planned": True,
                "executed": False,
                "rows_returned": 0,
                "warnings": [],
            }
        if normalized.status == "functional_error":
            return {
                "status": "rejected",
                "provider_name": "watson_flow_preflight",
                "provider_version": self._configuration.contract_version,
                "duration_ms": normalized.duration_ms or 0,
                "failure_category": normalized.failure_category,
                "error_code": _engine_code(normalized.failure_category),
                "message": "Watson Flow preflight rejeitou a SQL.",
                "repairable": normalized.repairable,
                "statement_planned": False,
                "executed": False,
                "rows_returned": 0,
            }
        return _preflight_error(
            "ENGINE_PREFLIGHT_RESPONSE_INVALID",
            "adapter_error",
            "Watson Flow preflight retornou resposta invalida.",
        )


def _iam_failure(status: object) -> EnginePreflightProviderResult:
    mapping = {
        "authentication_failed": ("ENGINE_PREFLIGHT_AUTHENTICATION_FAILED", "authentication_failed"),
        "timeout": ("ENGINE_PREFLIGHT_TIMEOUT", "timeout"),
        "unavailable": ("ENGINE_PREFLIGHT_PROVIDER_UNAVAILABLE", "provider_unavailable"),
        "invalid_response": ("ENGINE_PREFLIGHT_RESPONSE_INVALID", "protocol_error"),
    }
    code, category = mapping.get(status, ("ENGINE_PREFLIGHT_PROVIDER_FAILED", "adapter_error"))
    return _preflight_error(code, category, "IAM token provider falhou.")


def _flow_failure(status: object) -> EnginePreflightProviderResult:
    mapping = {
        "authentication_failed": ("ENGINE_PREFLIGHT_AUTHENTICATION_FAILED", "authentication_failed"),
        "timeout": ("ENGINE_PREFLIGHT_TIMEOUT", "timeout"),
        "unavailable": ("ENGINE_PREFLIGHT_PROVIDER_UNAVAILABLE", "provider_unavailable"),
        "rate_limited": ("ENGINE_PREFLIGHT_PROVIDER_UNAVAILABLE", "provider_unavailable"),
        "invalid_response": ("ENGINE_PREFLIGHT_RESPONSE_INVALID", "protocol_error"),
        "http_error": ("ENGINE_PREFLIGHT_PROVIDER_FAILED", "protocol_error"),
    }
    code, category = mapping.get(status, ("ENGINE_PREFLIGHT_PROVIDER_FAILED", "adapter_error"))
    return _preflight_error(code, category, "Watson Flow falhou.")


def _preflight_error(code: str, category: str, message: str) -> EnginePreflightProviderResult:
    return {
        "status": "error",
        "provider_name": "watson_flow_preflight",
        "provider_version": "watson-flow-n8n-v2.2.31-2026-08-01",
        "failure_category": category,  # type: ignore[typeddict-item]
        "error_code": code,  # type: ignore[typeddict-item]
        "message": message,
        "repairable": False,
        "statement_planned": False,
        "executed": False,
        "rows_returned": 0,
    }


def _engine_code(category: str) -> str:
    return {
        "column_not_found": "ENGINE_PREFLIGHT_COLUMN_NOT_FOUND",
        "table_not_found": "ENGINE_PREFLIGHT_TABLE_NOT_FOUND",
        "schema_not_found": "ENGINE_PREFLIGHT_SCHEMA_NOT_FOUND",
        "syntax_error": "ENGINE_PREFLIGHT_SYNTAX_ERROR",
    }.get(category, "ENGINE_PREFLIGHT_UNKNOWN_SQL_ERROR")
