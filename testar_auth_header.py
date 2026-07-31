from __future__ import annotations

from copy import deepcopy

from app.http.auth_header import (
    AuthorizationHeaderError,
    extract_bearer_credential,
)
from app.security.auth_types import default_auth_security_limits


TOKEN = "test-opaque-token"


def _request(headers=None, body=b'{"question":"ok"}', path="/v1/sql-agent/query"):
    return {
        "method": "POST",
        "path": path,
        "headers": headers if headers is not None else {"Authorization": f"Bearer {TOKEN}"},
        "body": body,
    }


def _raises(code, request, limits=None) -> None:
    try:
        extract_bearer_credential(
            request,
            limits=limits or default_auth_security_limits(),
        )
    except AuthorizationHeaderError as error:
        assert error.code == code
        assert TOKEN not in repr(error)
    else:
        raise AssertionError(f"Era esperado {code}.")


def test_bearer_valido() -> None:
    credential = extract_bearer_credential(
        _request(),
        limits=default_auth_security_limits(),
    )
    assert credential.reveal_for_authenticator() == TOKEN


def test_scheme_case_diferente() -> None:
    credential = extract_bearer_credential(
        _request(headers={"Authorization": f"bEaReR {TOKEN}"}),
        limits=default_auth_security_limits(),
    )
    assert credential.reveal_for_authenticator() == TOKEN


def test_header_ausente() -> None:
    _raises("AUTHORIZATION_HEADER_REQUIRED", _request(headers={}))


def test_token_vazio() -> None:
    _raises(
        "AUTHORIZATION_CREDENTIAL_REQUIRED",
        _request(headers={"Authorization": "Bearer "}),
    )


def test_basic() -> None:
    _raises(
        "AUTHORIZATION_SCHEME_UNSUPPORTED",
        _request(headers={"Authorization": f"Basic {TOKEN}"}),
    )


def test_multiplos_espacos() -> None:
    _raises(
        "AUTHORIZATION_HEADER_INVALID",
        _request(headers={"Authorization": f"Bearer  {TOKEN}"}),
    )


def test_whitespace_ambiguo() -> None:
    _raises(
        "AUTHORIZATION_HEADER_INVALID",
        _request(headers={"Authorization": f"Bearer {TOKEN} "}),
    )


def test_cr() -> None:
    _raises(
        "AUTHORIZATION_HEADER_INVALID",
        _request(headers={"Authorization": f"Bearer {TOKEN}\r"}),
    )


def test_lf() -> None:
    _raises(
        "AUTHORIZATION_HEADER_INVALID",
        _request(headers={"Authorization": f"Bearer {TOKEN}\n"}),
    )


def test_caractere_de_controle() -> None:
    _raises(
        "AUTHORIZATION_CREDENTIAL_INVALID_CHARACTER",
        _request(headers={"Authorization": "Bearer abc\x7f"}),
    )


def test_token_acima_do_limite() -> None:
    _raises(
        "AUTHORIZATION_CREDENTIAL_TOO_LARGE",
        _request(headers={"Authorization": "Bearer abcdef"}),
        {**default_auth_security_limits(), "max_credential_bytes": 5},
    )


def test_header_acima_do_limite() -> None:
    _raises(
        "AUTHORIZATION_HEADER_INVALID",
        _request(headers={"Authorization": "Bearer abcdef"}),
        {**default_auth_security_limits(), "max_authorization_header_bytes": 10},
    )


def test_multiplos_authorization() -> None:
    _raises(
        "AUTHORIZATION_HEADER_AMBIGUOUS",
        _request(headers={"Authorization": f"Bearer {TOKEN}", "authorization": f"Bearer {TOKEN}"}),
    )


def test_valores_conflitantes() -> None:
    _raises(
        "AUTHORIZATION_HEADER_AMBIGUOUS",
        _request(headers={"Authorization": f"Bearer {TOKEN}, Bearer other"}),
    )


def test_token_em_query_nao_e_aceito() -> None:
    _raises(
        "AUTHORIZATION_HEADER_REQUIRED",
        _request(headers={}, path=f"/v1/sql-agent/query?token={TOKEN}"),
    )


def test_token_no_body_nao_e_aceito() -> None:
    _raises(
        "AUTHORIZATION_HEADER_REQUIRED",
        _request(headers={}, body=f'{{"token":"{TOKEN}"}}'.encode("utf-8")),
    )


def test_token_nao_aparece_em_erro() -> None:
    try:
        extract_bearer_credential(
            _request(headers={"Authorization": f"Digest {TOKEN}"}),
            limits=default_auth_security_limits(),
        )
    except AuthorizationHeaderError as error:
        assert TOKEN not in str(error)
        assert TOKEN not in repr(error)


def test_token_nao_aparece_em_repr() -> None:
    credential = extract_bearer_credential(
        _request(),
        limits=default_auth_security_limits(),
    )
    assert TOKEN not in repr(credential)
    assert TOKEN not in str(credential)


def test_utf8_invalido_quando_envelope_permite_bytes() -> None:
    _raises(
        "AUTHORIZATION_HEADER_INVALID",
        _request(headers={"Authorization": b"Bearer abc"}),  # type: ignore[dict-item]
    )


def test_envelope_nao_mutado() -> None:
    request = _request()
    original = deepcopy(request)
    extract_bearer_credential(request, limits=default_auth_security_limits())
    assert request == original


def main() -> None:
    tests = [
        test_bearer_valido,
        test_scheme_case_diferente,
        test_header_ausente,
        test_token_vazio,
        test_basic,
        test_multiplos_espacos,
        test_whitespace_ambiguo,
        test_cr,
        test_lf,
        test_caractere_de_controle,
        test_token_acima_do_limite,
        test_header_acima_do_limite,
        test_multiplos_authorization,
        test_valores_conflitantes,
        test_token_em_query_nao_e_aceito,
        test_token_no_body_nao_e_aceito,
        test_token_nao_aparece_em_erro,
        test_token_nao_aparece_em_repr,
        test_utf8_invalido_quando_envelope_permite_bytes,
        test_envelope_nao_mutado,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
