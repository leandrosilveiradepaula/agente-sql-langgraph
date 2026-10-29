from __future__ import annotations

"""Read-only Gemini model availability probe for an existing Shadow container.

GET /v1beta/models/<configured-model> only: no generateContent, SQL, prompt,
database access, token usage, persistent state or secret disclosure.
"""

import http.client
import os
import socket
import ssl
import sys
from collections.abc import Callable, Mapping
from typing import Any
from urllib.parse import urlsplit

from app.integrations.google_gemini.configuration import (
    build_gemini_generate_content_url,
    load_google_gemini_configuration,
)

_SUCCESS = "MODEL_VISIBLE"
_HTTP_CLASSIFICATIONS = {
    400: "HTTP_BAD_REQUEST",
    401: "AUTHENTICATION_FAILED",
    403: "ACCESS_FORBIDDEN",
    404: "MODEL_NOT_FOUND",
    408: "PROVIDER_TIMEOUT",
    429: "RATE_LIMITED",
}


def _classify_http(status_code: int) -> str:
    if status_code == 200:
        return _SUCCESS
    if status_code in _HTTP_CLASSIFICATIONS:
        return _HTTP_CLASSIFICATIONS[status_code]
    if 500 <= status_code < 600:
        return "PROVIDER_UNAVAILABLE"
    return "HTTP_ERROR"


def probe_model_access(
    environ: Mapping[str, str],
    *,
    connection_factory: Callable[..., Any] | None = None,
) -> tuple[str, int | None]:
    """Return only an allowlisted category and upstream HTTP status.

    A 200 proves the model metadata endpoint is accessible with this key,
    not that generateContent succeeds or a financial SQL is valid.
    """
    if environ.get("LANGGRAPH_RUNTIME_MODE") != "shadow_test":
        return "NOT_SHADOW_RUNTIME", None
    if environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false":
        return "REAL_SQL_NOT_DISABLED", None
    if environ.get("GEMINI_SQL_GENERATOR_PROVIDER_KEY", "google_gemini") != "google_gemini":
        return "GEMINI_NOT_SELECTED", None

    api_key = environ.get("GEMINI_API_KEY")
    if not isinstance(api_key, str) or not api_key.strip():
        return "API_KEY_MISSING", None

    try:
        configuration = load_google_gemini_configuration(environ)
        url = build_gemini_generate_content_url(configuration)
        parsed = urlsplit(url)
        if parsed.scheme != "https" or not parsed.hostname or not parsed.path.endswith(":generateContent"):
            return "CONFIG_INVALID", None
        model_path = parsed.path.removesuffix(":generateContent")
    except (ValueError, TypeError):
        return "CONFIG_INVALID", None

    connection = None
    try:
        factory = connection_factory or http.client.HTTPSConnection
        connection = factory(
            parsed.hostname,
            parsed.port,
            timeout=configuration.connect_timeout_seconds,
            context=ssl.create_default_context(),
        )
        connection.request(
            "GET",
            model_path,
            headers={
                "x-goog-api-key": api_key,
                "Accept": "application/json",
                "Connection": "close",
            },
        )
        response = connection.getresponse()
        status = response.status
        if type(status) is not int or status < 100 or status > 599:
            return "INVALID_RESPONSE", None
        return _classify_http(status), status
    except (socket.timeout, TimeoutError):
        return "TIMEOUT", None
    except socket.gaierror:
        return "DNS_FAILURE", None
    except ssl.SSLError:
        return "TLS_FAILURE", None
    except OSError:
        return "CONNECTION_FAILURE", None
    except Exception:
        return "UNEXPECTED_ERROR", None
    finally:
        if connection is not None:
            try:
                connection.close()
            except Exception:
                pass


def main() -> int:
    category, http_status = probe_model_access(os.environ)
    print("G3_MODEL_ACCESS=" + category)
    print("G3_MODEL_ACCESS_HTTP=" + (str(http_status) if http_status is not None else "not_available"))
    print("G3_GENERATION_INVOKED=false")
    print("G3_SQL_EXECUTED=false")
    print("G3_MODEL_VISIBLE_IS_NOT_GENERATION_SUCCESS=true")
    return 0 if category == _SUCCESS else 2


if __name__ == "__main__":
    sys.exit(main())
