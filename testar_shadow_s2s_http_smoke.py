from __future__ import annotations

from unittest.mock import patch
from scripts.smoke_shadow_s2s_http_readonly import main


def test_smoke_requires_shadow_only() -> None:
    with patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true", "LANGGRAPH_S2S_TOKEN": "synthetic"}, clear=True):
        assert main() == 2


def test_smoke_expected_http_contract_without_network() -> None:
    def fake_call(path, *, token=None):
        if path == "/health":
            return 200, {"status": "ok", "real_sql_execution": False}
        if token is None or token == "invalid-synthetic-token":
            return 401, {"error": {"code": "UNAUTHORIZED_SERVICE"}}
        return 400, {"error": {"code": "SHADOW_RECORD_ID_INVALID"}}
    with patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false", "LANGGRAPH_S2S_TOKEN": "synthetic"}, clear=True):
        with patch("scripts.smoke_shadow_s2s_http_readonly.call", side_effect=fake_call):
            assert main() == 0


if __name__ == "__main__":
    test_smoke_requires_shadow_only()
    test_smoke_expected_http_contract_without_network()
    print("SHADOW_S2S_SMOKE_OFFLINE=PASS")
