from __future__ import annotations

from dataclasses import asdict, is_dataclass

from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.infrastructure.contracts import InfrastructureContractError


def _raises(fn, exc=Exception) -> None:
    try:
        fn()
    except exc:
        return
    raise AssertionError("Era esperada falha.")


def main() -> None:
    secret = SensitiveSecret("secret-test")
    assert secret.reveal_for_transport() == "secret-test"
    _raises(lambda: SensitiveSecret(""), InfrastructureContractError)
    _raises(lambda: SensitiveSecret("   "), InfrastructureContractError)
    _raises(lambda: SensitiveSecret("a\0b"), InfrastructureContractError)
    _raises(lambda: SensitiveSecret("a\rb"), InfrastructureContractError)
    _raises(lambda: SensitiveSecret("a\nb"), InfrastructureContractError)
    _raises(lambda: SensitiveSecret("a\x1fb"), InfrastructureContractError)
    assert SensitiveSecret("x" * 4, max_bytes=4).reveal_for_transport() == "xxxx"
    _raises(lambda: SensitiveSecret("xxxxx", max_bytes=4), InfrastructureContractError)
    assert SensitiveSecret("á", max_bytes=2).reveal_for_transport() == "á"
    assert "secret-test" not in repr(secret)
    assert str(secret) == "<redacted>"
    assert not is_dataclass(secret)
    _raises(lambda: asdict(secret), TypeError)
    _raises(lambda: iter(secret), TypeError)
    _raises(lambda: secret[0], TypeError)
    _raises(lambda: len(secret), TypeError)
    _raises(lambda: setattr(secret, "_secret", "changed"), AttributeError)
    try:
        SensitiveSecret("leak-value", max_bytes=1)
    except InfrastructureContractError as error:
        assert "leak-value" not in str(error)
    else:
        raise AssertionError("Era esperada falha.")
    print("testar_sensitive_secret.py: 18/18 OK")


if __name__ == "__main__":
    main()
