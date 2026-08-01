from __future__ import annotations

from dataclasses import dataclass

from app.integrations.watson.configuration import (
    IBM_IAM_TOKEN_URL,
    WATSON_FLOW_CONTRACT_VERSION,
    WatsonFlowConfiguration,
    watson_flow_run_path,
)
from app.integrations.watson.flow_limits import (
    WatsonFlowContractError,
    WatsonFlowLimits,
    default_watson_flow_limits,
)
from app.ports.secret_value_provider import SecretName


@dataclass(frozen=True, slots=True)
class LiveWatsonFlowConfiguration:
    watson_configuration: WatsonFlowConfiguration
    api_key_secret_name: SecretName
    enabled: bool

    def __post_init__(self) -> None:
        if not isinstance(self.watson_configuration, WatsonFlowConfiguration):
            raise WatsonFlowContractError("watson_configuration invalida.")
        if not isinstance(self.api_key_secret_name, SecretName):
            object.__setattr__(
                self,
                "api_key_secret_name",
                SecretName(str(self.api_key_secret_name)),
            )
        if not isinstance(self.enabled, bool):
            raise WatsonFlowContractError("enabled deve ser bool.")


def create_live_watson_flow_configuration(
    *,
    api_base_url: str,
    flow_id: str,
    api_key_secret_name: str,
    enabled: bool,
    iam_token_url: str = IBM_IAM_TOKEN_URL,
    connect_timeout_seconds: int = 5,
    read_timeout_seconds: int = 30,
    max_response_bytes: int | None = None,
    contract_version: str = WATSON_FLOW_CONTRACT_VERSION,
    limits: WatsonFlowLimits | None = None,
) -> LiveWatsonFlowConfiguration:
    if not isinstance(enabled, bool):
        raise WatsonFlowContractError("enabled deve ser bool.")
    safe_limits = limits or default_watson_flow_limits()
    watson_config = WatsonFlowConfiguration(
        api_base_url=api_base_url,
        flow_id=flow_id,
        iam_token_url=iam_token_url,
        contract_version=contract_version,
        connect_timeout_seconds=connect_timeout_seconds,
        request_timeout_seconds=read_timeout_seconds,
        max_response_bytes=max_response_bytes or safe_limits.max_raw_response_bytes,
    )
    return LiveWatsonFlowConfiguration(
        watson_configuration=watson_config,
        api_key_secret_name=SecretName(api_key_secret_name),
        enabled=enabled,
    )


def build_watson_flow_run_url(configuration: WatsonFlowConfiguration) -> str:
    path = watson_flow_run_path(configuration.flow_id)
    return f"{configuration.api_base_url}{path}"
