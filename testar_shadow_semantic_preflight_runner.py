from __future__ import annotations

import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "scripts/run_shadow_semantic_candidate_preflight.sh"


def script_text() -> str:
    return RUNNER.read_text(encoding="utf-8")


def test_shell_syntax_and_invalid_arguments_fail_before_docker() -> None:
    text = script_text()
    bash = shutil.which("bash")
    if bash is not None:
        checked = subprocess.run([bash, "-n", str(RUNNER.relative_to(ROOT))], cwd=ROOT, capture_output=True, text=True)
        assert checked.returncode == 0, checked.stderr
        for bad in (
            [],
            ["../outside.json"],
            ["semantic_context/../../file.json"],
            ["semantic_context/valid.json", "not-a-sha"],
        ):
            result = subprocess.run(
                [bash, str(RUNNER.relative_to(ROOT)), *bad],
                cwd=ROOT,
                capture_output=True,
                text=True,
            )
            assert result.returncode == 2, (bad, result.stderr, result.stdout)
            assert "ABORTED:" in result.stdout
    else:
        # Windows clean-room images without Bash still exercise static gates.
        assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail")


def test_only_existing_runtime_and_readonly_gate() -> None:
    text = script_text()
    assert "docker inspect" in text
    assert 'REAL_SQL_FLAG="$(' in text
    assert '"$REAL_SQL_FLAG" != "false"' in text
    assert 'os.environ.get("CONTEXT_POSTGRES_DSN")' in text
    assert 'docker exec -w "$STAGE"' in text
    assert 'PYTHONDONTWRITEBYTECODE=1' in text
    assert "python -m scripts.preview_semantic_candidate_readonly" in text
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
    ):
        assert forbidden not in text, forbidden


def test_reviewed_git_source_is_ephemeral_and_safe() -> None:
    text = script_text()
    assert 'git -C "$ROOT_DIR" archive --format=tar HEAD' in text
    assert '"$POLICY_RELATIVE"' in text
    assert 'git -C "$ROOT_DIR" branch --show-current' in text
    assert 'git -C "$ROOT_DIR" cat-file -e "HEAD:$POLICY_RELATIVE"' in text
    assert 'root.mkdir(mode=0o700)' in text
    assert 'relative.is_absolute() or ".." in relative.parts' in text
    assert "unsupported archived file type" in text
    assert 'target.open("xb")' in text
    assert "trap cleanup EXIT" in text
    assert "shutil.rmtree(p,ignore_errors=True)" in text
    assert '-e "PYTHONPATH=$STAGE"' in text
    assert "app \\\n" in text
    assert "scripts/preview_semantic_candidate_readonly.py" in text
    assert "scripts/audit_semantic_candidate_parity_readonly.py" in text
    assert "scripts/preflight_semantic_candidate_readonly.py" in text


def test_no_business_rules_and_no_benchmark_data_embedded() -> None:
    text = script_text()
    for forbidden in (
        "demo-finance-v10",
        "demo-finance-v11",
        "gold_orcamento",
        "gold_lancamentos_contabeis",
        "ai_ducklake_benchmarks",
        "golden_answer",
        "expected_sql",
        "execute_sql",
        "provider",
        "sql_pattern",
    ):
        assert forbidden not in text, forbidden


if __name__ == "__main__":
    test_shell_syntax_and_invalid_arguments_fail_before_docker()
    test_only_existing_runtime_and_readonly_gate()
    test_reviewed_git_source_is_ephemeral_and_safe()
    test_no_business_rules_and_no_benchmark_data_embedded()
    print("SHADOW_SEMANTIC_PREFLIGHT_RUNNER=PASS")
