from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Any, Literal, TypedDict


AUTH_CONTRACT_VERSION = "v1.0.0-http-auth-boundary"

AuthenticationStatus = Literal[
    "authenticated",
    "invalid_credentials",
    "unavailable",
    "error",
]
AuthenticationErrorCode = Literal[
    "AUTHENTICATION_INVALID_CREDENTIALS",
    "AUTHENTICATION_PRINCIPAL_INVALID",
    "AUTHENTICATION_SERVICE_UNAVAILABLE",
    "AUTHENTICATION_UNEXPECTED_ERROR",
]
AuthorizationStatus = Literal["allowed", "denied", "unavailable", "error"]
AuthorizationErrorCode = Literal[
    "AUTHORIZATION_DENIED",
    "AUTHORIZATION_SERVICE_UNAVAILABLE",
    "AUTHORIZATION_UNEXPECTED_ERROR",
]
AuthorizationAction = Literal["sql_agent.query.execute"]
AuthorizationResource = Literal["sql_agent.query"]


class AuthSecurityLimits(TypedDict):
    max_authorization_header_bytes: int
    max_credential_bytes: int
    max_principal_id_bytes: int
    max_principal_email_bytes: int
    max_principal_profile_bytes: int
    max_principal_organization_id_bytes: int
    max_roles: int
    max_role_bytes: int
    max_scopes: int
    max_scope_bytes: int
    max_attributes: int
    max_attribute_key_bytes: int
    max_attribute_value_bytes: int
    max_auth_diagnostics: int
    max_diagnostic_code_bytes: int
    max_diagnostic_message_bytes: int


@dataclass(frozen=True)
class BearerCredential:
    _value: str = field(repr=False)

    def reveal_for_authenticator(self) -> str:
        return self._value

    def __str__(self) -> str:
        return "BearerCredential(<redacted>)"


@dataclass(frozen=True)
class PrincipalAttribute:
    key: str
    value: str | int | bool | None


@dataclass(frozen=True)
class AuthenticatedPrincipal:
    subject_id: str
    email: str | None = None
    profile: str | None = None
    organization_id: str | None = None
    roles: tuple[str, ...] = ()
    scopes: tuple[str, ...] = ()
    attributes: Mapping[str, str | int | bool | None] = field(
        default_factory=lambda: MappingProxyType({})
    )
    authentication_method: str | None = None
    issuer_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "roles", tuple(self.roles))
        object.__setattr__(self, "scopes", tuple(self.scopes))
        object.__setattr__(
            self,
            "attributes",
            MappingProxyType(dict(self.attributes)),
        )

    def __deepcopy__(self, memo: dict[int, object]) -> "AuthenticatedPrincipal":
        del memo
        return AuthenticatedPrincipal(
            subject_id=self.subject_id,
            email=self.email,
            profile=self.profile,
            organization_id=self.organization_id,
            roles=tuple(self.roles),
            scopes=tuple(self.scopes),
            attributes=dict(self.attributes),
            authentication_method=self.authentication_method,
            issuer_id=self.issuer_id,
        )

    def __repr__(self) -> str:
        return "AuthenticatedPrincipal(<redacted>)"


class AuthenticationContext(TypedDict, total=False):
    method: str
    route: str
    request_id: str
    correlation_id: str


class AuthenticationResult(TypedDict, total=False):
    contract_version: str
    status: AuthenticationStatus
    principal: AuthenticatedPrincipal | None
    error_code: AuthenticationErrorCode | str | None
    diagnostics: list[dict[str, str]]


class AuthorizationRequest(TypedDict, total=False):
    contract_version: str
    action: AuthorizationAction
    resource: AuthorizationResource
    method: str
    route: str
    organization_id: str | None
    context: dict[str, str]


class AuthorizationDecision(TypedDict, total=False):
    contract_version: str
    status: AuthorizationStatus
    error_code: AuthorizationErrorCode | str | None
    diagnostics: list[dict[str, str]]


def default_auth_security_limits() -> AuthSecurityLimits:
    return {
        "max_authorization_header_bytes": 2048,
        "max_credential_bytes": 1536,
        "max_principal_id_bytes": 128,
        "max_principal_email_bytes": 254,
        "max_principal_profile_bytes": 64,
        "max_principal_organization_id_bytes": 128,
        "max_roles": 32,
        "max_role_bytes": 64,
        "max_scopes": 64,
        "max_scope_bytes": 128,
        "max_attributes": 16,
        "max_attribute_key_bytes": 64,
        "max_attribute_value_bytes": 256,
        "max_auth_diagnostics": 8,
        "max_diagnostic_code_bytes": 96,
        "max_diagnostic_message_bytes": 160,
    }


def validate_auth_security_limits(
    limits: Mapping[str, Any],
) -> AuthSecurityLimits:
    defaults = default_auth_security_limits()
    maximums = {
        "max_authorization_header_bytes": 8192,
        "max_credential_bytes": 4096,
        "max_principal_id_bytes": 512,
        "max_principal_email_bytes": 512,
        "max_principal_profile_bytes": 256,
        "max_principal_organization_id_bytes": 512,
        "max_roles": 100,
        "max_role_bytes": 256,
        "max_scopes": 200,
        "max_scope_bytes": 256,
        "max_attributes": 100,
        "max_attribute_key_bytes": 256,
        "max_attribute_value_bytes": 1024,
        "max_auth_diagnostics": 32,
        "max_diagnostic_code_bytes": 160,
        "max_diagnostic_message_bytes": 512,
    }
    output: dict[str, int] = {}
    for key, maximum in maximums.items():
        value = limits.get(key, defaults[key])
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("Limite de autenticacao invalido.")
        if value <= 0 or value > maximum:
            raise ValueError("Limite de autenticacao fora da faixa.")
        output[key] = value
    return output  # type: ignore[return-value]


def create_authenticated_principal(
    value: Mapping[str, Any],
    *,
    limits: Mapping[str, Any],
) -> AuthenticatedPrincipal:
    safe_limits = validate_auth_security_limits(limits)
    allowed = {
        "subject_id",
        "email",
        "profile",
        "organization_id",
        "roles",
        "scopes",
        "attributes",
        "authentication_method",
        "issuer_id",
    }
    if set(value) - allowed:
        raise ValueError("Principal contem campos desconhecidos.")
    subject_id = _required_text(
        value.get("subject_id"),
        safe_limits["max_principal_id_bytes"],
    )
    roles = _unique_text_tuple(
        value.get("roles", ()),
        max_items=safe_limits["max_roles"],
        max_bytes=safe_limits["max_role_bytes"],
    )
    scopes = _unique_text_tuple(
        value.get("scopes", ()),
        max_items=safe_limits["max_scopes"],
        max_bytes=safe_limits["max_scope_bytes"],
    )
    attributes = _attributes(
        value.get("attributes", {}),
        safe_limits,
    )
    return AuthenticatedPrincipal(
        subject_id=subject_id,
        email=_optional_text(
            value.get("email"),
            safe_limits["max_principal_email_bytes"],
        ),
        profile=_optional_text(
            value.get("profile"),
            safe_limits["max_principal_profile_bytes"],
        ),
        organization_id=_optional_text(
            value.get("organization_id"),
            safe_limits["max_principal_organization_id_bytes"],
        ),
        roles=roles,
        scopes=scopes,
        attributes=attributes,
        authentication_method=_optional_text(
            value.get("authentication_method"),
            safe_limits["max_principal_profile_bytes"],
        ),
        issuer_id=_optional_text(
            value.get("issuer_id"),
            safe_limits["max_principal_organization_id_bytes"],
        ),
    )


def validate_authenticated_principal(
    principal: object,
    *,
    limits: Mapping[str, Any],
) -> bool:
    if not isinstance(principal, AuthenticatedPrincipal):
        return False
    try:
        create_authenticated_principal(
            {
                "subject_id": principal.subject_id,
                "email": principal.email,
                "profile": principal.profile,
                "organization_id": principal.organization_id,
                "roles": principal.roles,
                "scopes": principal.scopes,
                "attributes": dict(principal.attributes),
                "authentication_method": principal.authentication_method,
                "issuer_id": principal.issuer_id,
            },
            limits=limits,
        )
    except ValueError:
        return False
    return True


def authentication_result(
    *,
    status: AuthenticationStatus,
    principal: AuthenticatedPrincipal | None = None,
    error_code: str | None = None,
) -> AuthenticationResult:
    result: AuthenticationResult = {
        "contract_version": AUTH_CONTRACT_VERSION,
        "status": status,
        "principal": principal,
        "error_code": error_code,
        "diagnostics": [],
    }
    if not validate_authentication_result(result):
        raise ValueError("Resultado de autenticacao incoerente.")
    return deepcopy(result)


def validate_authentication_result(result: object) -> bool:
    if not isinstance(result, Mapping):
        return False
    if result.get("contract_version") != AUTH_CONTRACT_VERSION:
        return False
    status = result.get("status")
    principal = result.get("principal")
    if status == "authenticated":
        return isinstance(principal, AuthenticatedPrincipal) and not result.get(
            "error_code"
        )
    if status in {"invalid_credentials", "unavailable", "error"}:
        return principal is None and isinstance(result.get("error_code"), str)
    return False


def authorization_request(
    *,
    method: str,
    route: str,
    organization_id: str | None,
) -> AuthorizationRequest:
    return {
        "contract_version": AUTH_CONTRACT_VERSION,
        "action": "sql_agent.query.execute",
        "resource": "sql_agent.query",
        "method": method,
        "route": route,
        "organization_id": organization_id,
        "context": {},
    }


def authorization_decision(
    *,
    status: AuthorizationStatus,
    error_code: str | None = None,
) -> AuthorizationDecision:
    decision: AuthorizationDecision = {
        "contract_version": AUTH_CONTRACT_VERSION,
        "status": status,
        "error_code": error_code,
        "diagnostics": [],
    }
    if not validate_authorization_decision(decision):
        raise ValueError("Decisao de autorizacao incoerente.")
    return deepcopy(decision)


def validate_authorization_decision(decision: object) -> bool:
    if not isinstance(decision, Mapping):
        return False
    if decision.get("contract_version") != AUTH_CONTRACT_VERSION:
        return False
    status = decision.get("status")
    if status == "allowed":
        return not decision.get("error_code")
    if status in {"denied", "unavailable", "error"}:
        return isinstance(decision.get("error_code"), str)
    return False


def principal_to_application_user(
    principal: AuthenticatedPrincipal,
) -> dict[str, str]:
    user = {"id": principal.subject_id}
    for source, target in [
        (principal.email, "email"),
        (principal.profile, "profile"),
        (principal.organization_id, "organization_id"),
    ]:
        if source:
            user[target] = source
    return deepcopy(user)


def _required_text(value: object, max_bytes: int) -> str:
    text = _optional_text(value, max_bytes)
    if not text:
        raise ValueError("Texto obrigatorio ausente.")
    return text


def _optional_text(value: object, max_bytes: int) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Texto invalido.")
    if _has_control(value) or len(value.encode("utf-8")) > max_bytes:
        raise ValueError("Texto invalido.")
    return str(value)


def _unique_text_tuple(
    value: object,
    *,
    max_items: int,
    max_bytes: int,
) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)):
        raise ValueError("Colecao invalida.")
    output: list[str] = []
    seen: set[str] = set()
    for item in value:
        text = _required_text(item, max_bytes)
        key = text.casefold()
        if key in seen:
            raise ValueError("Valor duplicado.")
        seen.add(key)
        output.append(text)
    if len(output) > max_items:
        raise ValueError("Colecao excessiva.")
    return tuple(output)


def _attributes(
    value: object,
    limits: AuthSecurityLimits,
) -> dict[str, str | int | bool | None]:
    if not isinstance(value, Mapping):
        raise ValueError("Atributos invalidos.")
    if len(value) > limits["max_attributes"]:
        raise ValueError("Atributos excessivos.")
    output: dict[str, str | int | bool | None] = {}
    for key, item in value.items():
        text_key = _required_text(key, limits["max_attribute_key_bytes"])
        if isinstance(item, bool) or isinstance(item, int) or item is None:
            output[text_key] = item
        elif isinstance(item, str):
            output[text_key] = _required_text(
                item,
                limits["max_attribute_value_bytes"],
            )
        else:
            raise ValueError("Atributo invalido.")
    return output


def _has_control(value: str) -> bool:
    return any(ord(char) < 32 or ord(char) == 127 for char in value)
