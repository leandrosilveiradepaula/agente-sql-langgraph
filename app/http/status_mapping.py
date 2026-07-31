from __future__ import annotations

from collections.abc import Mapping


def http_status_for_application_response(response: Mapping[str, object]) -> int:
    status = response.get("status")
    if status == "success":
        return 200
    if status == "rejected":
        return 422
    if status == "infrastructure_error":
        return 503
    return 500
