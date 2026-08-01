from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from app.integrations.watson.flow_limits import (
    WatsonFlowContractError,
    WatsonFlowLimits,
    default_watson_flow_limits,
)


WATSON_FLOW_CONTRACT_VERSION = "watson-flow-n8n-v2.2.31-2026-08-01"
IBM_IAM_TOKEN_URL = "https://iam.cloud.ibm.com/identity/token"
WATSON_FLOW_RUN_PATH_TEMPLATE = "/v1/orchestrate/flows/{flow_id}/run"


@dataclass(frozen=True, slots=True)
class WatsonFlowConfiguration:
    api_base_url: str
    flow_id: str
    iam_token_url: str
    contract_version: str
    connect_timeout_seconds: int
    request_timeout_seconds: int
    max_response_bytes: int
    expected_flow_name: str | None = None
    environment_label: str | None = None

    def __post_init__(self) -> None:
        limits = default_watson_flow_limits()
        object.__setattr__(
            self,
            "api_base_url",
            _validated_url(
                self.api_base_url,
                field_name="api_base_url",
                limits=limits,
                allow_path=False,
            ),
        )
        object.__setattr__(
            self,
            "iam_token_url",
            _validated_url(
                self.iam_token_url,
                field_name="iam_token_url",
                limits=limits,
                allow_path=True,
            ),
        )
        object.__setattr__(
            self,
            "flow_id",
            _validated_flow_id(self.flow_id, limits=limits),
        )
        if self.contract_version != WATSON_FLOW_CONTRACT_VERSION:
            raise WatsonFlowContractError("contract_version invalida.")
        for name in (
            "connect_timeout_seconds",
            "request_timeout_seconds",
            "max_response_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise WatsonFlowContractError(f"{name} deve ser positivo.")
            if name.endswith("timeout_seconds") and value > 300:
                raise WatsonFlowContractError(f"{name} excede limite defensivo.")
        if self.max_response_bytes > limits.max_raw_response_bytes:
            raise WatsonFlowContractError(
                "max_response_bytes excede limite Watson."
            )
        _optional_public_text(self.expected_flow_name, "expected_flow_name")
        _optional_public_text(self.environment_label, "environment_label")


def watson_flow_run_path(flow_id: str) -> str:
    return WATSON_FLOW_RUN_PATH_TEMPLATE.format(flow_id=flow_id)


def _validated_url(
    value: str,
    *,
    field_name: str,
    limits: WatsonFlowLimits,
    allow_path: bool,
) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WatsonFlowContractError(f"{field_name} deve ser URL nao vazia.")
    text = value.strip()
    if len(text.encode("utf-8")) > limits.max_url_bytes:
        raise WatsonFlowContractError(f"{field_name} excede limite.")
    if _has_control(text):
        raise WatsonFlowContractError(f"{field_name} contem controle.")
    lowered = text.casefold()
    if any(marker in lowered for marker in ("apikey=", "access_token", "bearer ")):
        raise WatsonFlowContractError(f"{field_name} contem segredo.")
    parsed = _split_https_url(text)
    if parsed is None:
        raise WatsonFlowContractError(f"{field_name} deve usar HTTPS com host.")
    authority, path = parsed
    if "@" in authority:
        raise WatsonFlowContractError(f"{field_name} nao permite userinfo.")
    if "?" in text or "#" in text:
        raise WatsonFlowContractError(f"{field_name} nao permite query/fragment.")
    if not allow_path and path not in {"", "/"}:
        raise WatsonFlowContractError(f"{field_name} nao permite path.")
    if not allow_path and text.endswith("/"):
        raise WatsonFlowContractError(f"{field_name} nao permite barra final.")
    if allow_path and not path.startswith("/"):
        raise WatsonFlowContractError(f"{field_name} path invalido.")
    return text.rstrip("/") if not allow_path else text


def _validated_flow_id(value: str, *, limits: WatsonFlowLimits) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WatsonFlowContractError("flow_id deve ser texto nao vazio.")
    text = value.strip()
    if len(text.encode("utf-8")) > limits.max_flow_id_bytes:
        raise WatsonFlowContractError("flow_id excede limite.")
    if _has_control(text):
        raise WatsonFlowContractError("flow_id contem controle.")
    try:
        UUID(text)
    except ValueError as exc:
        raise WatsonFlowContractError("flow_id deve estar em formato UUID.") from exc
    return text


def _optional_public_text(value: str | None, field_name: str) -> None:
    if value is None:
        return
    if not isinstance(value, str) or _has_control(value):
        raise WatsonFlowContractError(f"{field_name} invalido.")
    lowered = value.casefold()
    if any(marker in lowered for marker in ("apikey", "token", "secret", "bearer")):
        raise WatsonFlowContractError(f"{field_name} parece sensivel.")


def _has_control(value: str) -> bool:
    return any((ord(char) < 32 and char not in "\t\r\n") or ord(char) == 127 for char in value)


def _split_https_url(value: str) -> tuple[str, str] | None:
    prefix = "https://"
    if not value.startswith(prefix):
        return None
    rest = value[len(prefix) :]
    if not rest:
        return None
    slash_index = rest.find("/")
    authority = rest if slash_index < 0 else rest[:slash_index]
    path = "" if slash_index < 0 else rest[slash_index:]
    if not authority or authority.startswith(".") or authority.endswith("."):
        return None
    host = authority.rsplit(":", 1)[0] if ":" in authority else authority
    if not host or any(char.isspace() for char in authority):
        return None
    return authority, path
