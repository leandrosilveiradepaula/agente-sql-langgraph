from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit

from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.watson.flow_limits import WatsonFlowContractError


HttpTransportStatus = Literal[
    "success",
    "timeout",
    "dns_failure",
    "tls_failure",
    "connection_failure",
    "response_too_large",
    "invalid_response",
    "unexpected_error",
]

CRITICAL_HEADERS = {"authorization", "content-length", "host"}
SAFE_RESPONSE_HEADERS = {
    "content-type",
    "content-encoding",
    "retry-after",
    "x-request-id",
    "x-correlation-id",
    "trace-id",
}


@dataclass(frozen=True, slots=True)
class HttpHeader:
    name: str
    public_value: str | None = None
    sensitive_value: SensitiveSecret | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _validate_header_name(self.name))
        if (self.public_value is None) == (self.sensitive_value is None):
            raise WatsonFlowContractError("Header deve ter exatamente um valor.")
        if self.public_value is not None:
            object.__setattr__(
                self,
                "public_value",
                _validate_header_value(self.public_value, "header"),
            )
        if self.sensitive_value is not None and not isinstance(
            self.sensitive_value,
            SensitiveSecret,
        ):
            raise WatsonFlowContractError("Header sensivel invalido.")

    def materialize_for_transport(self) -> tuple[str, str]:
        if self.sensitive_value is not None:
            return self.name, _validate_header_value(
                self.sensitive_value.reveal_for_transport(),
                "header sensivel",
            )
        return self.name, self.public_value or ""

    def __repr__(self) -> str:
        if self.sensitive_value is not None:
            return f"HttpHeader(name={self.name!r}, sensitive_value=<redacted>)"
        return f"HttpHeader(name={self.name!r}, public_value={self.public_value!r})"


@dataclass(frozen=True, slots=True)
class HttpTransportRequest:
    method: str
    url: str
    headers: tuple[HttpHeader, ...]
    body: bytes
    connect_timeout_seconds: int
    read_timeout_seconds: int
    max_response_bytes: int
    operation_name: str
    request_id: str | None = None
    allow_query: bool = False

    def __post_init__(self) -> None:
        if self.method != "POST":
            raise WatsonFlowContractError("Metodo HTTP nao permitido.")
        _validate_https_url(self.url, allow_query=self.allow_query)
        if not isinstance(self.body, bytes):
            raise WatsonFlowContractError("body deve ser bytes.")
        for name in ("connect_timeout_seconds", "read_timeout_seconds"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0 or value > 300:
                raise WatsonFlowContractError(f"{name} invalido.")
        if (
            isinstance(self.max_response_bytes, bool)
            or not isinstance(self.max_response_bytes, int)
            or self.max_response_bytes <= 0
            or self.max_response_bytes > 20_000_000
        ):
            raise WatsonFlowContractError("max_response_bytes invalido.")
        if not isinstance(self.operation_name, str) or not self.operation_name.strip():
            raise WatsonFlowContractError("operation_name invalido.")
        if self.request_id is not None and (
            not isinstance(self.request_id, str)
            or not self.request_id.strip()
            or _has_control(self.request_id)
        ):
            raise WatsonFlowContractError("request_id tecnico invalido.")
        _validate_headers(self.headers)

    def __repr__(self) -> str:
        return (
            "HttpTransportRequest("
            f"method={self.method!r}, url=<redacted>, "
            f"headers={self.headers!r}, body=<redacted>, "
            f"operation_name={self.operation_name!r})"
        )


@dataclass(frozen=True, slots=True)
class HttpTransportResponse:
    status_code: int
    headers: dict[str, str]
    body: bytes
    duration_ms: int | None = None

    def __post_init__(self) -> None:
        if isinstance(self.status_code, bool) or not isinstance(self.status_code, int):
            raise WatsonFlowContractError("status_code invalido.")
        if self.status_code < 100 or self.status_code > 599:
            raise WatsonFlowContractError("status_code fora do intervalo.")
        if not isinstance(self.body, bytes):
            raise WatsonFlowContractError("body deve ser bytes.")
        safe: dict[str, str] = {}
        for key, value in self.headers.items():
            lowered = _validate_header_name(key).casefold()
            if lowered not in SAFE_RESPONSE_HEADERS:
                continue
            safe[lowered] = _validate_header_value(str(value), "response header")
        object.__setattr__(self, "headers", safe)
        if self.duration_ms is not None and (
            isinstance(self.duration_ms, bool)
            or not isinstance(self.duration_ms, int)
            or self.duration_ms < 0
        ):
            raise WatsonFlowContractError("duration_ms invalido.")


@dataclass(frozen=True, slots=True)
class HttpTransportResult:
    status: HttpTransportStatus
    response: HttpTransportResponse | None = None
    public_error_code: str | None = None
    public_error_message: str | None = None
    diagnostics: dict[str, object] | None = None

    def __post_init__(self) -> None:
        if self.status == "success":
            if not isinstance(self.response, HttpTransportResponse):
                raise WatsonFlowContractError("response obrigatoria no sucesso.")
            return
        if self.status not in {
            "timeout",
            "dns_failure",
            "tls_failure",
            "connection_failure",
            "response_too_large",
            "invalid_response",
            "unexpected_error",
        }:
            raise WatsonFlowContractError("status HTTP invalido.")
        if self.response is not None:
            raise WatsonFlowContractError("falha HTTP nao deve conter response.")

    def __repr__(self) -> str:
        return (
            "HttpTransportResult("
            f"status={self.status!r}, response={self.response!r}, "
            "diagnostics=<sanitized>)"
        )


def http_transport_success(response: HttpTransportResponse) -> HttpTransportResult:
    return HttpTransportResult(status="success", response=response)


def http_transport_failure(
    status: HttpTransportStatus,
    *,
    code: str | None = None,
    message: str | None = None,
    diagnostics: dict[str, object] | None = None,
) -> HttpTransportResult:
    if status == "success":
        raise WatsonFlowContractError("Use http_transport_success.")
    return HttpTransportResult(
        status=status,
        public_error_code=code or f"HTTP_{status.upper()}",
        public_error_message=message or "Transporte HTTP falhou.",
        diagnostics=_sanitize_diagnostics(diagnostics),
    )


def materialize_headers(headers: tuple[HttpHeader, ...]) -> dict[str, str]:
    return {name: value for name, value in (header.materialize_for_transport() for header in headers)}


def sanitize_response_headers(headers: object) -> dict[str, str]:
    output: dict[str, str] = {}
    if isinstance(headers, dict):
        iterator = headers.items()
    elif hasattr(headers, "items"):
        iterator = headers.items()
    else:
        iterator = []
    for key, value in iterator:
        if not isinstance(key, str):
            continue
        lowered = key.casefold()
        if lowered in SAFE_RESPONSE_HEADERS and isinstance(value, str):
            try:
                output[lowered] = _validate_header_value(value, "response header")
            except WatsonFlowContractError:
                continue
    return output


def _validate_headers(headers: tuple[HttpHeader, ...]) -> None:
    if not isinstance(headers, tuple) or not all(isinstance(h, HttpHeader) for h in headers):
        raise WatsonFlowContractError("headers devem ser HttpHeader.")
    seen_critical: set[str] = set()
    for header in headers:
        lowered = header.name.casefold()
        if lowered in CRITICAL_HEADERS:
            if lowered in seen_critical:
                raise WatsonFlowContractError("Header critico duplicado.")
            seen_critical.add(lowered)


def _validate_header_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WatsonFlowContractError("Header name invalido.")
    if any(ord(char) < 33 or ord(char) > 126 or char in "()<>@,;:\\\"/[]?={} \t" for char in value):
        raise WatsonFlowContractError("Header name invalido.")
    return value


def _validate_header_value(value: str, field_name: str) -> str:
    if not isinstance(value, str):
        raise WatsonFlowContractError(f"{field_name} invalido.")
    if any(char in value for char in "\r\n\0"):
        raise WatsonFlowContractError(f"{field_name} contem controle.")
    try:
        value.encode("latin-1")
    except UnicodeEncodeError as exc:
        raise WatsonFlowContractError(f"{field_name} deve ser latin-1.") from exc
    return value


def _validate_https_url(value: str, *, allow_query: bool) -> None:
    if not isinstance(value, str) or not value.strip():
        raise WatsonFlowContractError("URL invalida.")
    if _has_control(value):
        raise WatsonFlowContractError("URL contem controle.")
    parsed = urlsplit(value)
    if parsed.scheme != "https":
        raise WatsonFlowContractError("Apenas HTTPS e permitido.")
    if not parsed.hostname:
        raise WatsonFlowContractError("Host obrigatorio.")
    if parsed.username or parsed.password:
        raise WatsonFlowContractError("URL nao permite userinfo.")
    if parsed.fragment:
        raise WatsonFlowContractError("URL nao permite fragment.")
    if parsed.query and not allow_query:
        raise WatsonFlowContractError("URL nao permite query.")
    if not parsed.path.startswith("/"):
        raise WatsonFlowContractError("Path absoluto obrigatorio.")
    if parsed.port is not None and (parsed.port <= 0 or parsed.port > 65535):
        raise WatsonFlowContractError("Porta invalida.")


def _sanitize_diagnostics(value: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    output: dict[str, object] = {}
    blocked = {"authorization", "headers", "body", "url", "token", "apikey", "api_key"}
    for key, raw in value.items():
        if not isinstance(key, str) or key.casefold() in blocked:
            continue
        if isinstance(raw, (str, int, bool)) or raw is None:
            text = str(raw).casefold()
            if any(marker in text for marker in ("bearer", "apikey", "token", "select ")):
                continue
            output[key[:64]] = raw
    return output


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
