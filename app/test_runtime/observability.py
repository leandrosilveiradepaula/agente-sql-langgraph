from __future__ import annotations

import json
import logging
import time
from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from app.application.internal_sql_agent_v1_shared import shadow_record_id
from app.http.http_request_types import HttpRequestEnvelope
from app.http.http_response_types import HttpResponseEnvelope


class ObservedShadowEvidenceRepository:
    def __init__(self, inner: Any) -> None:
        if inner is None:
            raise RuntimeError("shadow repository must be injected.")
        self.inner = inner
        self.last_results_by_shadow_id: dict[str, dict[str, Any]] = {}

    def create(self, record: Mapping[str, Any]) -> Mapping[str, Any]:
        result = self.inner.create(deepcopy(dict(record)))
        self._capture(record, result)
        return result

    def update_evidence(self, record: Mapping[str, Any]) -> Mapping[str, Any]:
        result = self.inner.update_evidence(deepcopy(dict(record)))
        self._capture(record, result)
        return result

    def finalize(self, request: Mapping[str, Any]) -> Mapping[str, Any]:
        result = self.inner.finalize(deepcopy(dict(request)))
        self._capture(request, result)
        return result

    def fetch_by_shadow_record_id(self, shadow_record_id: str) -> Any:
        return self.inner.fetch_by_shadow_record_id(shadow_record_id)

    def list_by_agent_run_id(self, agent_run_id: str) -> Any:
        return self.inner.list_by_agent_run_id(agent_run_id)

    def persistence_status(self, value: str | None) -> str | None:
        if not value:
            return None
        result = self.last_results_by_shadow_id.get(value)
        if not isinstance(result, Mapping):
            return None
        status = result.get("status")
        return status if isinstance(status, str) else None

    def _capture(
        self,
        source: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        value = source.get("shadow_record_id")
        if isinstance(value, str) and value:
            self.last_results_by_shadow_id[value] = deepcopy(dict(result))


class ObservedInternalHttpHandler:
    def __init__(
        self,
        *,
        inner: Any,
        repository: ObservedShadowEvidenceRepository,
        logger: logging.Logger | Any | None = None,
    ) -> None:
        if inner is None or not callable(getattr(inner, "handle", None)):
            raise RuntimeError("inner HTTP handler must be injected.")
        self._inner = inner
        self._repository = repository
        self._logger = logger or logging.getLogger("langgraph.shadow_test")

    def handle(self, request: HttpRequestEnvelope) -> HttpResponseEnvelope:
        started = time.perf_counter()
        endpoint = str(request.get("path", ""))
        payload = _safe_payload(request.get("body", b""))
        event_type = _event_type(endpoint)
        self._emit(
            {
                "event": "shadow_test_request_accepted",
                "endpoint": endpoint,
                "agent_run_id": payload.get("agent_run_id"),
                "event_type": event_type,
            }
        )
        response = self._inner.handle(request)
        duration_ms = int((time.perf_counter() - started) * 1000)
        body = _safe_payload(response.get("body", b""))
        run_id = body.get("run_id")
        agent_run_id = body.get("agent_run_id") or payload.get("agent_run_id")
        record_id = (
            shadow_record_id(
                agent_run_id=str(agent_run_id),
                run_id=str(run_id),
                event_type=str(event_type),
            )
            if agent_run_id and run_id and event_type
            else None
        )
        self._emit(
            {
                "event": "shadow_test_request_completed",
                "endpoint": endpoint,
                "agent_run_id": agent_run_id,
                "run_id": run_id,
                "shadow_record_id": record_id,
                "event_type": event_type,
                "status": body.get("status"),
                "duration_ms": duration_ms,
                "persistence_status": self._repository.persistence_status(record_id),
            }
        )
        return response

    def _emit(self, payload: Mapping[str, Any]) -> None:
        message = json.dumps(
            {key: value for key, value in payload.items() if value is not None},
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        info = getattr(self._logger, "info", None)
        if callable(info):
            try:
                info(message)
            except Exception:
                return


def _safe_payload(body: object) -> dict[str, Any]:
    if not isinstance(body, bytes):
        return {}
    try:
        payload = json.loads(body.decode("utf-8"))
    except Exception:
        return {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _event_type(endpoint: str) -> str | None:
    if endpoint == "/v1/internal/sql-agent/generate":
        return "generate"
    if endpoint == "/v1/internal/sql-agent/execute-approved-shadow":
        return "execute_approved_shadow"
    return None
