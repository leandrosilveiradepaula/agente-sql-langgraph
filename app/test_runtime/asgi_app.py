from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from app.asgi.asgi_types import AsgiReceive, AsgiScope, AsgiSend
from app.test_runtime.config import ShadowTestRuntimeConfig


class ShadowTestAsgiApplication:
    def __init__(
        self,
        *,
        internal_app: Any,
        config: ShadowTestRuntimeConfig,
    ) -> None:
        if internal_app is None or not callable(internal_app):
            raise RuntimeError("internal ASGI app must be injected.")
        self._internal_app = internal_app
        self._config = config

    async def __call__(
        self,
        scope: AsgiScope,
        receive: AsgiReceive,
        send: AsgiSend,
    ) -> None:
        if _is_health(scope):
            await _send_json(
                send,
                200,
                {
                    "status": "ok",
                    "runtime_mode": self._config.runtime_mode,
                    "real_sql_execution": False,
                    "shadow_persistence": self._config.shadow_persistence,
                },
            )
            return
        await self._internal_app(scope, receive, send)


def _is_health(scope: Mapping[str, Any]) -> bool:
    return (
        scope.get("type") == "http"
        and str(scope.get("method", "")).upper() == "GET"
        and scope.get("path") == "/health"
    )


async def _send_json(
    send: AsgiSend,
    status_code: int,
    payload: Mapping[str, Any],
) -> None:
    body = json.dumps(
        dict(payload),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    headers = [
        (b"content-type", b"application/json"),
        (b"cache-control", b"no-store"),
        (b"content-length", str(len(body)).encode("ascii")),
    ]
    await send({"type": "http.response.start", "status": status_code, "headers": headers})
    await send({"type": "http.response.body", "body": body, "more_body": False})
