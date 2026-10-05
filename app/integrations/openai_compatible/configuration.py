from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import urlsplit


OPENAI_COMPATIBLE_PROVIDER_KEY_ENV = "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY"
OPENAI_COMPATIBLE_CONFIG_VERSION_ENV = "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION"
OPENAI_COMPATIBLE_BASE_URL_ENV = "OPENAI_COMPATIBLE_SQL_BASE_URL"
OPENAI_COMPATIBLE_MODEL_ENV = "OPENAI_COMPATIBLE_SQL_MODEL"
OPENAI_COMPATIBLE_SECRET_NAME_ENV = "OPENAI_COMPATIBLE_SQL_API_KEY_SECRET_NAME"
OPENAI_COMPATIBLE_CONNECT_TIMEOUT_ENV = "OPENAI_COMPATIBLE_CONNECT_TIMEOUT_SECONDS"
OPENAI_COMPATIBLE_READ_TIMEOUT_ENV = "OPENAI_COMPATIBLE_READ_TIMEOUT_SECONDS"
OPENAI_COMPATIBLE_MAX_TOKENS_ENV = "OPENAI_COMPATIBLE_MAX_TOKENS"

DEFAULT_CREDENTIAL_NAME = "OPENAI_COMPATIBLE_SQL_API_KEY"
DEFAULT_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_READ_TIMEOUT_SECONDS = 60
DEFAULT_MAX_TOKENS = 8192
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_RESPONSE_BYTES = 200_000


class OpenAiCompatibleConfigurationError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class OpenAiCompatibleConfiguration:
    provider_key: str
    config_version: str
    api_base_url: str
    model_id: str
    api_key_secret_name: str = DEFAULT_CREDENTIAL_NAME
    connect_timeout_seconds: int = DEFAULT_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: int = DEFAULT_READ_TIMEOUT_SECONDS
    max_tokens: int = DEFAULT_MAX_TOKENS
    temperature: float = DEFAULT_TEMPERATURE
    max_response_bytes: int = DEFAULT_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        for field_name in (
            "provider_key",
            "config_version",
            "model_id",
            "api_key_secret_name",
        ):
            value = getattr(self, field_name)
            object.__setattr__(
                self,
                field_name,
                _public_text(value, field_name),
            )
        object.__setattr__(
            self,
            "api_base_url",
            _https_base_url(self.api_base_url),
        )
        _positive_int(self.connect_timeout_seconds, "connect_timeout_seconds", 300)
        _positive_int(self.read_timeout_seconds, "read_timeout_seconds", 300)
        _positive_int(self.max_tokens, "max_tokens", 200_000)
        _positive_int(self.max_response_bytes, "max_response_bytes", 20_000_000)
        if not isinstance(self.temperature, (int, float)) or isinstance(
            self.temperature, bool
        ):
            raise OpenAiCompatibleConfigurationError("temperature invalida.")
        if float(self.temperature) < 0 or float(self.temperature) > 2:
            raise OpenAiCompatibleConfigurationError("temperature fora do intervalo.")


def load_openai_compatible_configuration(
    environ: Mapping[str, str] | None = None,
) -> OpenAiCompatibleConfiguration | None:
    source = os.environ if environ is None else environ
    provider_key = _optional(source, OPENAI_COMPATIBLE_PROVIDER_KEY_ENV)
    base_url = _optional(source, OPENAI_COMPATIBLE_BASE_URL_ENV)
    model_id = _optional(source, OPENAI_COMPATIBLE_MODEL_ENV)
    config_version = _optional(source, OPENAI_COMPATIBLE_CONFIG_VERSION_ENV)

    configured = [provider_key, base_url, model_id, config_version]
    if not any(configured):
        return None
    if not all(configured):
        raise OpenAiCompatibleConfigurationError(
            "Configuracao OpenAI-compatible incompleta."
        )

    return OpenAiCompatibleConfiguration(
        provider_key=provider_key or "",
        config_version=config_version or "",
        api_base_url=base_url or "",
        model_id=model_id or "",
        api_key_secret_name=(
            _optional(source, OPENAI_COMPATIBLE_SECRET_NAME_ENV)
            or DEFAULT_CREDENTIAL_NAME
        ),
        connect_timeout_seconds=_optional_int(
            source,
            OPENAI_COMPATIBLE_CONNECT_TIMEOUT_ENV,
            DEFAULT_CONNECT_TIMEOUT_SECONDS,
        ),
        read_timeout_seconds=_optional_int(
            source,
            OPENAI_COMPATIBLE_READ_TIMEOUT_ENV,
            DEFAULT_READ_TIMEOUT_SECONDS,
        ),
        max_tokens=_optional_int(
            source,
            OPENAI_COMPATIBLE_MAX_TOKENS_ENV,
            DEFAULT_MAX_TOKENS,
        ),
    )


def build_chat_completions_url(
    configuration: OpenAiCompatibleConfiguration,
) -> str:
    return f"{configuration.api_base_url}/api/chat/completions"


def _optional(source: Mapping[str, str], name: str) -> str | None:
    value = source.get(name)
    if value is None or not str(value).strip():
        return None
    return str(value).strip()


def _optional_int(
    source: Mapping[str, str],
    name: str,
    default: int,
) -> int:
    value = source.get(name)
    if value is None or not str(value).strip():
        return default
    try:
        if isinstance(value, bool):
            raise ValueError
        return int(str(value).strip())
    except ValueError as exc:
        raise OpenAiCompatibleConfigurationError(
            f"{name} deve ser inteiro."
        ) from exc


def _public_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenAiCompatibleConfigurationError(
            f"{field_name} deve ser texto nao vazio."
        )
    text = value.strip()
    if any(ord(character) < 32 or ord(character) == 127 for character in text):
        raise OpenAiCompatibleConfigurationError(
            f"{field_name} contem controle."
        )
    lowered = text.casefold()
    if field_name != "api_key_secret_name" and any(
        marker in lowered
        for marker in ("bearer", "apikey=", "api_key=", "secret=")
    ):
        raise OpenAiCompatibleConfigurationError(
            f"{field_name} parece conter segredo."
        )
    return text


def _https_base_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise OpenAiCompatibleConfigurationError("api_base_url invalida.")
    text = value.strip().rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.hostname:
        raise OpenAiCompatibleConfigurationError(
            "api_base_url deve usar HTTPS."
        )
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise OpenAiCompatibleConfigurationError(
            "api_base_url contem componente nao permitido."
        )
    return text


def _positive_int(value: object, field_name: str, maximum: int) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, int)
        or value <= 0
        or value > maximum
    ):
        raise OpenAiCompatibleConfigurationError(
            f"{field_name} invalido."
        )
