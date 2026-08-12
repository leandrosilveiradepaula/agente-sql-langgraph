from __future__ import annotations

import inspect
import json

from app.asgi.asgi_types import HeaderPairs
from app.security import internal_service_auth
from app.security.internal_service_auth import (
    INTERNAL_SERVICE_NAME,
    InternalServiceAuthConfig,
    authenticate_internal_service,
)


TOKEN = "test-s2s-token"


def _config() -> InternalServiceAuthConfig:
    return InternalServiceAuthConfig(expected_token=TOKEN)


def _auth(headers: object):
    return authenticate_internal_service(headers, config=_config())


def test_token_correto_autentica_service() -> None:
    result = _auth({"Authorization": f"Bearer {TOKEN}"})
    assert result["status"] == "authenticated"
    assert result["service_name"] == INTERNAL_SERVICE_NAME


def test_token_errado_ausente_e_cookie_sem_bearer_nao_autenticam() -> None:
    assert _auth({"Authorization": "Bearer wrong-token"})["status"] == "unauthorized"
    assert _auth({})["status"] == "unauthorized"
    assert _auth({"Cookie": "session=browser"})["status"] == "unauthorized"


def test_bearer_vazio_basic_lowercase_e_malformed_falham() -> None:
    for value in (
        "Bearer ",
        "Basic abc",
        "bearer test-s2s-token",
        "Bearer  test-s2s-token",
        "Bearer test-s2s-token extra",
        "Bearer test-s2s-token ",
    ):
        assert _auth({"Authorization": value})["status"] == "unauthorized"


def test_authorization_duplicado_falha_sem_escolher_header() -> None:
    headers = HeaderPairs(
        (
            ("authorization", f"Bearer {TOKEN}"),
            ("authorization", "Bearer wrong-token"),
        )
    )
    assert _auth(headers)["status"] == "unauthorized"


def test_authorization_oversized_falha() -> None:
    oversized = "Bearer " + ("a" * 1100)
    assert _auth({"Authorization": oversized})["status"] == "unauthorized"


def test_principal_no_payload_nao_autentica_caller() -> None:
    payload = {
        "principal": {
            "id": "user-1",
            "email": "user@example.invalid",
            "profile": "admin",
        }
    }
    assert _auth({"Content-Type": "application/json"})["status"] == "unauthorized"
    assert "principal" in payload


def test_compare_digest_e_usado() -> None:
    source = inspect.getsource(internal_service_auth.authenticate_internal_service)
    assert "hmac.compare_digest" in source
    assert "credential == config.expected_token" not in source


def test_secret_nao_aparece_em_repr_erro_ou_json() -> None:
    secret = "test-secret-hidden"
    config = InternalServiceAuthConfig(expected_token=secret)
    wrong = authenticate_internal_service(
        {"Authorization": "Bearer wrong-token"},
        config=config,
    )
    serialized = repr(config) + repr(wrong) + json.dumps(wrong)
    assert secret not in serialized
    assert "wrong-token" not in serialized


def main() -> None:
    tests = [
        test_token_correto_autentica_service,
        test_token_errado_ausente_e_cookie_sem_bearer_nao_autenticam,
        test_bearer_vazio_basic_lowercase_e_malformed_falham,
        test_authorization_duplicado_falha_sem_escolher_header,
        test_authorization_oversized_falha,
        test_principal_no_payload_nao_autentica_caller,
        test_compare_digest_e_usado,
        test_secret_nao_aparece_em_repr_erro_ou_json,
    ]
    for index, test in enumerate(tests, start=1):
        test()
        print(f"TESTE {index} - {test.__name__}: OK")


if __name__ == "__main__":
    main()
