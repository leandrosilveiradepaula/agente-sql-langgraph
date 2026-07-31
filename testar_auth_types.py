from __future__ import annotations

from copy import deepcopy

from app.security.auth_policy import ScopeAuthorizationPolicy
from app.security.auth_types import (
    AuthenticatedPrincipal,
    BearerCredential,
    authentication_result,
    authorization_decision,
    authorization_request,
    create_authenticated_principal,
    default_auth_security_limits,
    principal_to_application_user,
    validate_auth_security_limits,
    validate_authenticated_principal,
    validate_authentication_result,
    validate_authorization_decision,
)


def _raises(func, *args, **kwargs) -> None:
    try:
        func(*args, **kwargs)
    except ValueError:
        return
    raise AssertionError("Era esperado ValueError.")


def _principal(**overrides):
    data = {"subject_id": "principal-1"}
    data.update(overrides)
    return create_authenticated_principal(
        data,
        limits=default_auth_security_limits(),
    )


def test_principal_minimo_valido() -> None:
    principal = _principal()
    assert principal.subject_id == "principal-1"
    assert principal.roles == ()
    assert principal_to_application_user(principal) == {"id": "principal-1"}


def test_principal_completo_valido() -> None:
    principal = _principal(
        email="person@example.invalid",
        profile="generic-profile",
        organization_id="org-1",
        roles=["role.one"],
        scopes=["scope.one"],
        attributes={"tier": "one", "active": True},
        authentication_method="bearer",
        issuer_id="issuer-1",
    )
    assert principal.email == "person@example.invalid"
    assert principal.roles == ("role.one",)
    assert principal.scopes == ("scope.one",)
    assert dict(principal.attributes)["active"] is True


def test_subject_id_ausente() -> None:
    _raises(
        create_authenticated_principal,
        {},
        limits=default_auth_security_limits(),
    )


def test_subject_id_vazio() -> None:
    _raises(
        create_authenticated_principal,
        {"subject_id": " "},
        limits=default_auth_security_limits(),
    )


def test_limite_utf8() -> None:
    limits = {**default_auth_security_limits(), "max_principal_id_bytes": 6}
    assert create_authenticated_principal(
        {"subject_id": "ação"},
        limits=limits,
    ).subject_id == "ação"
    _raises(create_authenticated_principal, {"subject_id": "ações"}, limits=limits)


def test_caractere_de_controle() -> None:
    _raises(
        create_authenticated_principal,
        {"subject_id": "principal\n1"},
        limits=default_auth_security_limits(),
    )


def test_roles_duplicadas() -> None:
    _raises(_principal, roles=["one", "ONE"])


def test_scopes_duplicados() -> None:
    _raises(_principal, scopes=["one", "ONE"])


def test_excesso_de_roles() -> None:
    _raises(
        _principal,
        roles=[f"role-{index}" for index in range(40)],
    )


def test_excesso_de_scopes() -> None:
    _raises(
        _principal,
        scopes=[f"scope-{index}" for index in range(70)],
    )


def test_attribute_valido() -> None:
    principal = _principal(attributes={"key": 1, "flag": False, "none": None})
    assert dict(principal.attributes)["key"] == 1


def test_attribute_aninhado_invalido() -> None:
    _raises(_principal, attributes={"nested": {"bad": True}})


def test_token_ausente_do_principal() -> None:
    principal = _principal()
    assert "token" not in repr(principal).casefold()
    assert not hasattr(principal, "token")


def test_campos_desconhecidos() -> None:
    _raises(_principal, claims={"sub": "principal-1"})


def test_imutabilidade() -> None:
    principal = _principal(roles=["one"], scopes=["two"], attributes={"a": "b"})
    try:
        principal.roles += ("x",)
    except Exception:
        pass
    else:
        raise AssertionError("Roles devem ser imutaveis.")
    try:
        principal.attributes["a"] = "changed"  # type: ignore[index]
    except TypeError:
        pass
    else:
        raise AssertionError("Attributes devem ser imutaveis.")


def test_copia_independente() -> None:
    source = {"subject_id": "principal-1", "roles": ["one"], "attributes": {"a": "b"}}
    principal = create_authenticated_principal(
        source,
        limits=default_auth_security_limits(),
    )
    source["roles"].append("two")  # type: ignore[union-attr]
    source["attributes"]["a"] = "changed"  # type: ignore[index]
    copied = deepcopy(principal)
    assert principal.roles == ("one",)
    assert dict(principal.attributes)["a"] == "b"
    assert copied is not principal


def test_limites_zero_negativos_excessivos() -> None:
    for value in [0, -1, 999999]:
        _raises(
            validate_auth_security_limits,
            {**default_auth_security_limits(), "max_roles": value},
        )


def test_authentication_result_coerente() -> None:
    principal = _principal()
    result = authentication_result(status="authenticated", principal=principal)
    assert validate_authentication_result(result)
    invalid = authentication_result(
        status="invalid_credentials",
        error_code="AUTHENTICATION_INVALID_CREDENTIALS",
    )
    assert invalid["principal"] is None


def test_authentication_result_incoerente() -> None:
    assert not validate_authentication_result(
        {
            "contract_version": "v1.0.0-http-auth-boundary",
            "status": "authenticated",
            "principal": None,
            "error_code": None,
        }
    )


def test_authorization_decision_coerente() -> None:
    assert validate_authorization_decision(authorization_decision(status="allowed"))
    denied = authorization_decision(
        status="denied",
        error_code="AUTHORIZATION_DENIED",
    )
    assert denied["status"] == "denied"


def test_authorization_decision_incoerente() -> None:
    assert not validate_authorization_decision(
        {
            "contract_version": "v1.0.0-http-auth-boundary",
            "status": "allowed",
            "error_code": "AUTHORIZATION_DENIED",
        }
    )


def test_scope_policy_match_exato() -> None:
    principal = _principal(scopes=["scope.allowed"])
    request = authorization_request(
        method="POST",
        route="/v1/sql-agent/query",
        organization_id=None,
    )
    policy = ScopeAuthorizationPolicy(required_scope="scope.allowed")
    assert policy.authorize(principal, request)["status"] == "allowed"
    denied = ScopeAuthorizationPolicy(required_scope="scope").authorize(
        principal,
        request,
    )
    assert denied["status"] == "denied"


def main() -> None:
    tests = [
        test_principal_minimo_valido,
        test_principal_completo_valido,
        test_subject_id_ausente,
        test_subject_id_vazio,
        test_limite_utf8,
        test_caractere_de_controle,
        test_roles_duplicadas,
        test_scopes_duplicados,
        test_excesso_de_roles,
        test_excesso_de_scopes,
        test_attribute_valido,
        test_attribute_aninhado_invalido,
        test_token_ausente_do_principal,
        test_campos_desconhecidos,
        test_imutabilidade,
        test_copia_independente,
        test_limites_zero_negativos_excessivos,
        test_authentication_result_coerente,
        test_authentication_result_incoerente,
        test_authorization_decision_coerente,
        test_authorization_decision_incoerente,
        test_scope_policy_match_exato,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
