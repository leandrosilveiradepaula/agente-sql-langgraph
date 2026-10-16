from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

from scripts.preview_semantic_overlay_readonly import parse_overlay_policy, main


ROOT = Path(__file__).resolve().parent
RUNNER = ROOT / "scripts/run_shadow_semantic_overlay_preflight.sh"
BASE = ROOT / "semantic_context/candidate_parity_demo_finance_v11.json"
OVERLAY = ROOT / "semantic_context/candidate_overlay_demo_finance_v12.json"
SUITE = ROOT / "scripts/validation/demo_finance_v12_independent_semantic_cases.json"


def test_versioned_chain_and_evaluation_isolation() -> None:
    base = json.loads(BASE.read_text(encoding="utf-8"))
    raw_overlay = json.loads(OVERLAY.read_text(encoding="utf-8"))
    policy = parse_overlay_policy(raw_overlay)
    suite = json.loads(SUITE.read_text(encoding="utf-8"))
    assert base["candidate_version"] == policy["source_version"]
    assert policy["source_version"] != policy["candidate_version"]
    assert all(change["operation"] in {
        "extend_concept_terms", "mirror_concept_terms", "clone_entity_alias",
        "add_catalog_exclusion",
    } for change in policy["changes"])
    assert len(suite["cases"]) >= 8
    assert all(set(item) <= {
        "question", "expected_intent", "expected_plan_status",
        "expected_error_code", "expected_temporal_issue",
    } for item in suite["cases"])
    assert len({item["question"] for item in suite["cases"]}) == len(suite["cases"])
    # An explicit operation should coexist with unranked/untrended controls.
    intents = {item.get("expected_intent") for item in suite["cases"]}
    assert len(intents) >= 4
    text = (ROOT / "scripts/preview_semantic_overlay_readonly.py").read_text(
        encoding="utf-8"
    )
    assert 'baseline = evaluate_suite(base, suite)' in text
    assert 'evaluated = evaluate_suite(candidate, suite)' in text
    assert '"regressed_case_indexes"' in text
    assert '"activation_authorized": False' in text
    assert '"real_sql_execution": False' in text
    assert "benchmark" not in json.dumps(policy).casefold()


def test_overlay_cli_denies_execution_before_loading_any_context() -> None:
    with (
        patch("sys.argv", ["preview"]),
        patch.dict("os.environ", {"LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "true"}),
        patch("scripts.preview_semantic_overlay_readonly.PostgresContextRepository") as repo,
    ):
        assert main() == 3
        repo.assert_not_called()


def test_runner_invalid_paths_fail_before_docker() -> None:
    text = RUNNER.read_text(encoding="utf-8")
    bash = shutil.which("bash")
    if bash:
        syntax = subprocess.run([bash, "-n", str(RUNNER)], capture_output=True, text=True)
        assert syntax.returncode == 0, syntax.stderr
        for args in (
            [],
            ["../../unsafe.json"],
            ["semantic_context/base.json", "../../unsafe.json"],
            ["semantic_context/base.json", "semantic_context/overlay.json"],
            ["semantic_context/base.json", "semantic_context/overlay.json", "bad"],
            ["semantic_context/base.json", "semantic_context/overlay.json", "a" * 64, "../../bad.json"],
        ):
            result = subprocess.run(
                [bash, str(RUNNER), *args], cwd=ROOT,
                capture_output=True, text=True,
            )
            assert result.returncode == 2, (args, result.stdout, result.stderr)
            assert "ABORTED:" in result.stdout
    else:
        assert text.startswith("#!/usr/bin/env bash\nset -euo pipefail")


def test_runner_only_uses_reviewed_existing_shadow() -> None:
    script = RUNNER.read_text(encoding="utf-8")
    for required in (
        'branch --show-current',
        'cat-file -e "HEAD:$tracked"',
        'archive --format=tar HEAD',
        'docker inspect "$CONTAINER"',
        '"$REAL_SQL_FLAG" != "false"',
        'os.environ.get("CONTEXT_POSTGRES_DSN")',
        'private staging directory required',
        'relative.is_absolute() or ".." in relative.parts',
        'unsupported archived file type',
        'target.open("xb")',
        'PYTHONDONTWRITEBYTECODE=1',
        'scripts.preview_semantic_overlay_readonly',
        '--expected-source-fingerprint "$EXPECTED_SOURCE_FINGERPRINT"',
        'trap cleanup EXIT',
    ):
        assert required in script, required
    for forbidden in (
        "docker compose up", "docker build", "docker cp ", "docker restart",
        "docker run ", "psql ", "export CONTEXT_POSTGRES_DSN",
        "SEMANTIC_AGENT_VERSION=", "SEMANTIC_MIGRATION_POSTGRES_DSN",
        "printenv", "ai_ducklake_benchmarks", "golden_answer",
    ):
        assert forbidden not in script, forbidden


if __name__ == "__main__":
    test_versioned_chain_and_evaluation_isolation()
    test_overlay_cli_denies_execution_before_loading_any_context()
    test_runner_invalid_paths_fail_before_docker()
    test_runner_only_uses_reviewed_existing_shadow()
    print("V12_SEMANTIC_READONLY_CANDIDATE=PASS")
