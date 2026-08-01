from __future__ import annotations

from dataclasses import asdict, is_dataclass

from app.integrations.watson.flow_limits import WatsonFlowContractError
from app.integrations.watson.iam_contracts import (
    SensitiveBearerToken,
    iam_token_failure,
    iam_token_request,
    iam_token_success,
)


def _raises(fn) -> None:
    try:
        fn()
    except (WatsonFlowContractError, TypeError, AttributeError):
        return
    raise AssertionError("Era esperada falha.")


def main() -> None:
    req = iam_token_request(request_id="req", run_id="run", timeout_seconds=5)
    assert req["force_refresh"] is False
    token = SensitiveBearerToken("tok-test")
    result = iam_token_success(token)
    assert result["status"] == "success"
    _raises(lambda: SensitiveBearerToken(""))
    _raises(lambda: SensitiveBearerToken("x" * 9000))
    _raises(lambda: SensitiveBearerToken("abc\n"))
    assert iam_token_success(token, token_type="Bearer")["token_type"] == "Bearer"
    _raises(lambda: iam_token_success(token, token_type="Basic"))
    assert iam_token_success(token, expires_in=1)["expires_in"] == 1
    _raises(lambda: iam_token_success(token, expires_in=0))
    assert repr(token) == "SensitiveBearerToken(<redacted>)"
    assert str(token) == "<redacted>"
    assert not is_dataclass(token)
    _raises(lambda: asdict(token))  # type: ignore[arg-type]
    assert iam_token_failure("unavailable")["status"] == "unavailable"
    assert iam_token_failure("timeout")["status"] == "timeout"
    assert iam_token_failure("authentication_failed")["status"] == "authentication_failed"
    assert iam_token_failure("invalid_response")["status"] == "invalid_response"
    assert iam_token_failure("unexpected_error")["status"] == "unexpected_error"
    sanitized = iam_token_failure(
        "unexpected_error",
        diagnostics={"access_token": "tok-test", "safe_code": "x"},
    )
    assert sanitized["diagnostics"] == {"safe_code": "x"}
    assert "tok-test" not in repr(sanitized)
    _raises(lambda: setattr(token, "_value", "new"))
    print("testar_iam_token_contract.py: 20/20 OK")


if __name__ == "__main__":
    main()
