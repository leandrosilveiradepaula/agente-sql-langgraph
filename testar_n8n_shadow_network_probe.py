from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
PROBE = ROOT / "scripts/probe_n8n_shadow_network_readonly.sh"


def _bash_binary() -> str:
    """Avoid Windows WSL launcher; use actual Git-for-Windows Bash instead."""
    if os.name != "nt":
        result = shutil.which("bash")
        assert result is not None, "Bash is required to lint the probe"
        return result

    candidates: list[Path] = []
    git = shutil.which("git")
    if git:
        git_parent = Path(git).parent
        candidates.extend([
            git_parent / "bash.exe",
            git_parent.parent / "bin" / "bash.exe",
        ])
    program_files = os.environ.get("ProgramFiles")
    if program_files:
        candidates.append(Path(program_files) / "Git" / "bin" / "bash.exe")
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    raise AssertionError("Git-for-Windows Bash required for shell syntax validation")


def test_network_probe_syntax_and_safety():
    source = PROBE.read_text(encoding="utf-8")
    # Supply the source on stdin so Windows paths need no POSIX conversion.
    completed = subprocess.run(
        [_bash_binary(), "-n"],
        input=source,
        capture_output=True,
        text=True,
        check=False,
        cwd=ROOT,
    )
    assert completed.returncode == 0, (
        f"shell_syntax_exit={completed.returncode}: {completed.stderr[:800]}"
    )
    assert "docker exec" in source
    assert 'method: "GET"' in source
    assert "real_sql_execution !== false" in source
    assert "N8N_TO_SHADOW_CONNECTIVITY=PASS" in source
    assert "SHARED_NETWORK_COUNT=" in source
    for forbidden in (
        "docker network connect",
        "docker network create",
        "docker compose up",
        "import:workflow",
        "activate-workflow",
        'method: "POST"',
        "Authorization",
        "LANGGRAPH_S2S_TOKEN",
    ):
        assert forbidden not in source, forbidden


if __name__ == "__main__":
    test_network_probe_syntax_and_safety()
    print("N8N_SHADOW_NETWORK_PROBE_OFFLINE=PASS")
