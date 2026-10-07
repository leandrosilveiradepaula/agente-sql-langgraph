from __future__ import annotations

from app.adapters.testing.fake_secret_value_provider import FakeSecretValueProvider
from app.infrastructure.secrets.environment_secret_provider import EnvironmentSecretProvider
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.infrastructure.contracts import InfrastructureContractError
from app.ports.secret_value_provider import SecretName, secret_lookup_failure


def _raises(fn, exc=Exception) -> None:
    try:
        fn()
    except exc:
        return
    raise AssertionError("Era esperada falha.")


def main() -> None:
    provider = EnvironmentSecretProvider(environ={"TEST_SECRET_KEY": "test-secret"})
    result = provider.get_secret(SecretName("TEST_SECRET_KEY"))
    assert result["status"] == "success"
    assert result["secret"].reveal_for_transport() == "test-secret"
    assert provider.get_secret(SecretName("MISSING"))["status"] == "missing"
    assert EnvironmentSecretProvider(environ={"A": ""}).get_secret(SecretName("A"))["status"] == "invalid"
    assert EnvironmentSecretProvider(environ={"A": "x\n"}).get_secret(SecretName("A"))["status"] == "invalid"
    assert provider.requested_names == ["TEST_SECRET_KEY", "MISSING"]
    assert len(provider.requested_names) == 2
    _raises(lambda: SecretName("bad-name"), InfrastructureContractError)
    assert EnvironmentSecretProvider(environ={}, unavailable=True).get_secret(SecretName("A"))["status"] == "unavailable"
    assert "test-secret" not in repr(provider)
    source = {"A": "one"}
    env_provider = EnvironmentSecretProvider(environ=source)
    assert env_provider.get_secret(SecretName("A"))["secret"].reveal_for_transport() == "one"
    source["A"] = "two"
    assert env_provider.get_secret(SecretName("A"))["secret"].reveal_for_transport() == "two"
    assert env_provider.calls == 2
    fake = FakeSecretValueProvider(secret=SensitiveSecret("test-secret"))
    assert fake.get_secret(SecretName("A"))["status"] == "success"
    assert fake.calls == 1
    assert secret_lookup_failure("unexpected_error", diagnostics={"secret": "hidden"})["diagnostics"] == {}
    print("testar_secret_value_provider.py: 12/12 OK")


if __name__ == "__main__":
    main()
