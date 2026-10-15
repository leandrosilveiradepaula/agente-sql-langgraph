from __future__ import annotations

import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROBE = ROOT / "scripts/probe_n8n_shadow_network_readonly.sh"


def test_network_probe_syntax_and_safety():
    completed = subprocess.run(
        ["bash", "-n", str(PROBE)],
        capture_output=True, text=True, check=False,
    )
    assert completed.returncode == 0, completed.stderr
    source = PROBE.read_text(encoding="utf-8")
    assert "docker exec" in source
    assert "method: \"GET\"" in source
    assert "real_sql_execution !== false" in source
    assert "N8N_TO_SHADOW_CONNECTIVITY=PASS" in source
    assert "SHARED_NETWORK_COUNT=" in source
    for forbidden in (
        "docker network connect",
        "docker network create",
        "docker compose up",
        "import:workflow",
        "activate-workflow",
        "method: \"POST\"",
        "Authorization",
        "LANGGRAPH_S2S_TOKEN",
    ):
        assert forbidden not in source, forbidden


if __name__ == "__main__":
    test_network_probe_syntax_and_safety()
    print("N8N_SHADOW_NETWORK_PROBE_OFFLINE=PASS")
