from __future__ import annotations

from dataclasses import FrozenInstanceError, asdict

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


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"


def _config(**overrides):
    values = {
        "api_base_url": "https://example.invalid",
        "flow_id": FLOW_ID,
        "iam_token_url": IBM_IAM_TOKEN_URL,
        "contract_version": WATSON_FLOW_CONTRACT_VERSION,
        "connect_timeout_seconds": 3,
        "request_timeout_seconds": 10,
        "max_response_bytes": 1000,
        "expected_flow_name": "Agentic_workflow_1_5887h4",
        "environment_label": "test",
    }
    values.update(overrides)
    return WatsonFlowConfiguration(**values)


def _raises(fn) -> None:
    try:
        fn()
    except (WatsonFlowContractError, FrozenInstanceError):
        return
    raise AssertionError("Era esperada falha de contrato.")


def main() -> None:
    cfg = _config()
    assert cfg.api_base_url == "https://example.invalid"
    assert watson_flow_run_path(cfg.flow_id) == (
        f"/v1/orchestrate/flows/{FLOW_ID}/run"
    )
    assert _config(api_base_url="https://host.invalid").api_base_url
    _raises(lambda: _config(api_base_url="http://host.invalid"))
    _raises(lambda: _config(api_base_url="https://u:p@host.invalid"))
    _raises(lambda: _config(api_base_url="https://host.invalid?a=1"))
    _raises(lambda: _config(api_base_url="https://host.invalid#frag"))
    _raises(lambda: _config(api_base_url="https://host.invalid/path"))
    assert _config(iam_token_url=IBM_IAM_TOKEN_URL).iam_token_url.endswith(
        "/identity/token"
    )
    _raises(lambda: _config(iam_token_url="https://iam.invalid/token?a=1"))
    assert _config(flow_id=FLOW_ID).flow_id == FLOW_ID
    _raises(lambda: _config(flow_id=""))
    _raises(lambda: _config(flow_id="not-a-uuid"))
    _raises(lambda: _config(connect_timeout_seconds=0))
    _raises(lambda: _config(request_timeout_seconds=-1))
    _raises(lambda: _config(request_timeout_seconds=301))
    limits = default_watson_flow_limits()
    assert limits.max_transport_sql_characters == 10_000
    _raises(lambda: WatsonFlowLimits(**{**asdict(limits), "max_rows": 0}))
    _raises(lambda: WatsonFlowLimits(**{**asdict(limits), "max_rows": True}))
    _raises(
        lambda: WatsonFlowLimits(
            **{**asdict(limits), "max_transport_sql_characters": 9999}
        )
    )
    _raises(lambda: setattr(cfg, "flow_id", FLOW_ID))
    assert "api_key" not in repr(cfg).casefold()
    print("testar_watson_flow_configuration.py: 21/21 OK")


if __name__ == "__main__":
    main()
