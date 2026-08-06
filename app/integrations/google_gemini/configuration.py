from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from urllib.parse import quote, urlsplit


GOOGLE_GEMINI_PROVIDER_NAME = "google_gemini"
GEMINI_API_KEY_SECRET_NAME = "GEMINI_API_KEY"
GEMINI_API_BASE_URL_ENV = "GEMINI_API_BASE_URL"
GEMINI_SQL_GENERATOR_MODEL_ENV = "GEMINI_SQL_GENERATOR_MODEL"
GEMINI_CONNECT_TIMEOUT_ENV = "GEMINI_CONNECT_TIMEOUT_SECONDS"
GEMINI_READ_TIMEOUT_ENV = "GEMINI_READ_TIMEOUT_SECONDS"
GEMINI_MAX_OUTPUT_TOKENS_ENV = "GEMINI_MAX_OUTPUT_TOKENS"
DEFAULT_GEMINI_API_BASE_URL = "https://generativelanguage.googleapis.com"
DEFAULT_GEMINI_MODEL_ID = "gemini-2.5-flash"
DEFAULT_GEMINI_CONNECT_TIMEOUT_SECONDS = 5
DEFAULT_GEMINI_READ_TIMEOUT_SECONDS = 30
DEFAULT_GEMINI_TEMPERATURE = 0.0
DEFAULT_GEMINI_TOP_P = 0.1
DEFAULT_GEMINI_TOP_K = 1
DEFAULT_GEMINI_MAX_OUTPUT_TOKENS = 8192
DEFAULT_GEMINI_RESPONSE_MIME_TYPE = "text/plain"
DEFAULT_GEMINI_THINKING_BUDGET = 0
DEFAULT_GEMINI_MAX_RESPONSE_BYTES = 200_000


class GoogleGeminiConfigurationError(ValueError):
    """
    Erro de configuracao nao sensivel do adapter Gemini.
    """


@dataclass(frozen=True, slots=True)
class GoogleGeminiConfiguration:
    api_base_url: str = DEFAULT_GEMINI_API_BASE_URL
    model_id: str = DEFAULT_GEMINI_MODEL_ID
    connect_timeout_seconds: int = DEFAULT_GEMINI_CONNECT_TIMEOUT_SECONDS
    read_timeout_seconds: int = DEFAULT_GEMINI_READ_TIMEOUT_SECONDS
    temperature: float = DEFAULT_GEMINI_TEMPERATURE
    top_p: float = DEFAULT_GEMINI_TOP_P
    top_k: int = DEFAULT_GEMINI_TOP_K
    max_output_tokens: int = DEFAULT_GEMINI_MAX_OUTPUT_TOKENS
    response_mime_type: str = DEFAULT_GEMINI_RESPONSE_MIME_TYPE
    thinking_budget: int = DEFAULT_GEMINI_THINKING_BUDGET
    max_response_bytes: int = DEFAULT_GEMINI_MAX_RESPONSE_BYTES

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "api_base_url",
            _validated_base_url(self.api_base_url),
        )
        object.__setattr__(
            self,
            "model_id",
            _validated_public_text(self.model_id, "model_id"),
        )
        object.__setattr__(
            self,
            "response_mime_type",
            _validated_public_text(
                self.response_mime_type,
                "response_mime_type",
            ),
        )
        _validate_timeout(
            self.connect_timeout_seconds,
            "connect_timeout_seconds",
        )
        _validate_timeout(
            self.read_timeout_seconds,
            "read_timeout_seconds",
        )
        _validate_float_range(self.temperature, "temperature", minimum=0.0, maximum=2.0)
        _validate_float_range(self.top_p, "top_p", minimum=0.0, maximum=1.0)
        _validate_positive_int(self.top_k, "top_k")
        _validate_positive_int(
            self.max_output_tokens,
            "max_output_tokens",
        )
        _validate_non_negative_int(
            self.thinking_budget,
            "thinking_budget",
        )
        _validate_positive_int(
            self.max_response_bytes,
            "max_response_bytes",
            maximum=20_000_000,
        )


def default_google_gemini_configuration() -> GoogleGeminiConfiguration:
    return GoogleGeminiConfiguration()


def load_google_gemini_configuration(
    environ: Mapping[str, str] | None = None,
) -> GoogleGeminiConfiguration:
    source = os.environ if environ is None else environ
    return GoogleGeminiConfiguration(
        api_base_url=_optional_text(
            source,
            GEMINI_API_BASE_URL_ENV,
            DEFAULT_GEMINI_API_BASE_URL,
        ),
        model_id=_optional_text(
            source,
            GEMINI_SQL_GENERATOR_MODEL_ENV,
            DEFAULT_GEMINI_MODEL_ID,
        ),
        connect_timeout_seconds=_optional_int(
            source,
            GEMINI_CONNECT_TIMEOUT_ENV,
            DEFAULT_GEMINI_CONNECT_TIMEOUT_SECONDS,
        ),
        read_timeout_seconds=_optional_int(
            source,
            GEMINI_READ_TIMEOUT_ENV,
            DEFAULT_GEMINI_READ_TIMEOUT_SECONDS,
        ),
        max_output_tokens=_optional_int(
            source,
            GEMINI_MAX_OUTPUT_TOKENS_ENV,
            DEFAULT_GEMINI_MAX_OUTPUT_TOKENS,
        ),
    )


def build_gemini_generate_content_url(
    configuration: GoogleGeminiConfiguration,
) -> str:
    if not isinstance(configuration, GoogleGeminiConfiguration):
        raise GoogleGeminiConfigurationError(
            "configuration invalida."
        )
    model = quote(configuration.model_id, safe="-_.~")
    return f"{configuration.api_base_url}/v1beta/models/{model}:generateContent"


def _validated_base_url(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoogleGeminiConfigurationError(
            "api_base_url deve ser URL nao vazia."
        )
    text = value.strip()
    if _has_control(text):
        raise GoogleGeminiConfigurationError(
            "api_base_url contem controle."
        )
    lowered = text.casefold()
    if any(marker in lowered for marker in ("apikey=", "api_key=", "token", "bearer ")):
        raise GoogleGeminiConfigurationError(
            "api_base_url contem segredo."
        )
    parsed = urlsplit(text)
    if parsed.scheme != "https" or not parsed.hostname:
        raise GoogleGeminiConfigurationError(
            "api_base_url deve usar HTTPS com host."
        )
    if parsed.username or parsed.password:
        raise GoogleGeminiConfigurationError(
            "api_base_url nao permite userinfo."
        )
    if parsed.query or parsed.fragment:
        raise GoogleGeminiConfigurationError(
            "api_base_url nao permite query ou fragment."
        )
    if parsed.path not in {"", "/"}:
        raise GoogleGeminiConfigurationError(
            "api_base_url nao permite path."
        )
    if parsed.port is not None and (parsed.port <= 0 or parsed.port > 65535):
        raise GoogleGeminiConfigurationError("api_base_url porta invalida.")
    return text.rstrip("/")


def _optional_text(
    source: Mapping[str, str],
    name: str,
    default: str,
) -> str:
    value = source.get(name)
    if value is None or not str(value).strip():
        return default
    return str(value)


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
        raise GoogleGeminiConfigurationError(
            f"{name} deve ser inteiro."
        ) from exc


def _validated_public_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise GoogleGeminiConfigurationError(
            f"{field_name} deve ser texto nao vazio."
        )
    text = value.strip()
    if _has_control(text):
        raise GoogleGeminiConfigurationError(
            f"{field_name} contem controle."
        )
    lowered = text.casefold()
    if any(marker in lowered for marker in ("apikey", "api_key", "token", "secret", "bearer")):
        raise GoogleGeminiConfigurationError(
            f"{field_name} parece sensivel."
        )
    return text


def _validate_timeout(value: object, field_name: str) -> None:
    _validate_positive_int(value, field_name, maximum=300)


def _validate_positive_int(
    value: object,
    field_name: str,
    *,
    maximum: int | None = None,
) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise GoogleGeminiConfigurationError(
            f"{field_name} deve ser inteiro positivo."
        )
    if maximum is not None and value > maximum:
        raise GoogleGeminiConfigurationError(
            f"{field_name} excede limite."
        )


def _validate_non_negative_int(value: object, field_name: str) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise GoogleGeminiConfigurationError(
            f"{field_name} deve ser inteiro nao negativo."
        )


def _validate_float_range(
    value: object,
    field_name: str,
    *,
    minimum: float,
    maximum: float,
) -> None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise GoogleGeminiConfigurationError(
            f"{field_name} deve ser numerico."
        )
    number = float(value)
    if number < minimum or number > maximum:
        raise GoogleGeminiConfigurationError(
            f"{field_name} fora do intervalo."
        )


def _has_control(value: str) -> bool:
    return any(ord(character) < 32 or ord(character) == 127 for character in value)
