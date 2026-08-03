from __future__ import annotations

import importlib
import os
import socket
import sys
import tempfile
from pathlib import Path


MODULES = [
    "app.bootstrap",
    "app.composition.watson_test",
    "app.infrastructure.http",
    "app.infrastructure.secrets",
    "app.integrations.watson.live_configuration",
    "app.integrations.watson.live_iam_token_provider",
    "app.integrations.watson.live_watson_flow_client",
    "scripts.manual_watson_flow_probe",
    "scripts.offline_watson_test_composition_check",
]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SENSITIVE_ENV = {
    "IBM_CLOUD_API_KEY",
    "WATSON_API_BASE_URL",
    "WATSON_FLOW_ID",
    "WATSON_IAM_TOKEN_URL",
}


def _block_network() -> None:
    def blocked(*_args, **_kwargs):
        raise RuntimeError("NETWORK_BLOCKED_IMPORT_CHECK")

    socket.socket.connect = blocked  # type: ignore[method-assign]
    socket.create_connection = blocked  # type: ignore[assignment]
    socket.getaddrinfo = blocked  # type: ignore[assignment]


def _sanitize_env() -> None:
    for name in SENSITIVE_ENV | {name.lower() for name in SENSITIVE_ENV}:
        os.environ.pop(name, None)
    os.environ["SQL_AGENT_DISABLE_NETWORK"] = "1"


def main() -> int:
    _sanitize_env()
    _block_network()
    before = set(Path.cwd().iterdir())
    with tempfile.TemporaryDirectory(prefix="sql-agent-imports-") as tmp:
        os.environ["TMP"] = tmp
        os.environ["TEMP"] = tmp
        for module in MODULES:
            importlib.import_module(module)
    after = set(Path.cwd().iterdir())
    if before != after:
        print("IMPORT_CHECK_FAILED: filesystem_changed")
        return 1
    print("IMPORT_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
