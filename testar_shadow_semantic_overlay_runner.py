from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "scripts/run_shadow_semantic_overlay_preflight.sh"


def test_runner_syntax_and_invalid_input_fail_before_docker() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    bash = shutil.which("bash")
    if bash is not None:
        result = subprocess.run(
            [bash, "-n", str(RUNNER)], cwd=ROOT, capture_output=True, text=True,
        )
        assert result.returncode == 0, result.stderr
        for args in (
            [],
            ["../unexpected.json"],
            ["semantic_context/base.json", "../escape.json"],
            ["semantic_context/base.json", "semantic_context/v12.json", "invalid"],
            ["semantic_context/base.json", "semantic_context/v12.json",
             "a" * 64, "scripts/validation/../untracked.json"],
        ):
            checked = subprocess.run(
                [bash, str(RUNNER), *args], cwd=ROOT,
                capture_output=True, text=True,
            )
            assert checked.returncode == 2, (args, checked.stdout, checked.stderr)
            assert "ABORTED:" in checked.stdout
    else:
        assert source.startswith("#!/usr/bin/env bash\nset -euo pipefail")


def test_runner_only_stages_reviewed_sources_with_shadow_gate() -> None:
    source = RUNNER.read_text(encoding="utf-8")
    for required in (
        'git -C "$ROOT_DIR" archive --format=tar HEAD',
        'git -C "$ROOT_DIR" branch --show-current',
        'git -C "$ROOT_DIR" cat-file -e',
        "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION",
        "REAL_SQL_FLAG",
        "docker inspect",
        'docker exec -w "$STAGE"',
        "PYTHONDONTWRITEBYTECODE=1",
        "scripts.preview_semantic_overlay_readonly",
        "--base-policy",
        "--overlay",
        "--cases",
        "--expected-source-fingerprint",
        "semantic_overlay_readonly_",
        "trap cleanup EXIT",
        "private staging directory required",
        "unsupported archived file type",
    ):
        assert required in source, required
    for forbidden in (
        "docker compose up",
        "docker build",
        "docker cp ",
        "docker restart",
        "docker run ",
        "psql ",
        "SEMANTIC_AGENT_VERSION=",
        "SEMANTIC_MIGRATION_POSTGRES_DSN",
        "export CONTEXT_POSTGRES_DSN",
        "printenv",
        "ai_ducklake_benchmarks",
        "expected_sql",
        "golden_answer",
        "execute_sql",
    ):
        assert forbidden not in source, forbidden


if __name__ == "__main__":
    test_runner_syntax_and_invalid_input_fail_before_docker()
    test_runner_only_stages_reviewed_sources_with_shadow_gate()
    print("SHADOW_SEMANTIC_OVERLAY_RUNNER=PASS")
