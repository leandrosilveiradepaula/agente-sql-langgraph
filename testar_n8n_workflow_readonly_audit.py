from __future__ import annotations

import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.audit_n8n_workflows_readonly import (
    edges,
    main,
    parse_workflows,
    render,
    safe_title,
)


def fixtures():
    source = {
        "id": "synthetic_active",
        "name": "Synthetic Finance SQL",
        "active": True,
        "nodes": [
            {
                "name": "Start",
                "type": "n8n-nodes-base.webhook",
                "parameters": {
                    "path": "https://host.example/invisible-private-endpoint"
                },
            },
            {
                "name": "Transform",
                "type": "n8n-nodes-base.code",
                "parameters": {
                    "jsCode": "console.log('PRIVATE_CODE_NEVER_PRINT');"
                },
            },
            {
                "name": "Execute",
                "type": "n8n-nodes-base.postgres",
                "parameters": {
                    "query": "SELECT 'PRIVATE_SQL_NEVER_PRINT'",
                    "credentials": "PRIVATE_CREDENTIAL_NEVER_PRINT",
                },
            },
        ],
        "connections": {
            "Start": {
                "main": [[{"node": "Transform", "type": "main", "index": 0}]]
            },
            "Transform": {
                "main": [[{"node": "Execute", "type": "main", "index": 0}]]
            },
        },
    }
    others = {
        "id": "other_workflow",
        "name": "Unrelated webhook",
        "active": False,
        "nodes": [
            {
                "name": "Unrelated",
                "type": "n8n-nodes-base.manualTrigger",
                "parameters": {"text": "PRIVATE_PARAMETER_NEVER_PRINT"},
            }
        ],
        "connections": {},
    }
    return [source, others]


def capture(callback, *args, **kwargs) -> str:
    stream = io.StringIO()
    with redirect_stdout(stream):
        callback(*args, **kwargs)
    return stream.getvalue()


def test_safe_inventory_no_parameters_or_secrets():
    src = fixtures()
    result = capture(
        render,
        src,
        matches=["finance", "unknown"],
        workflow_id=None,
        max_workflows=12,
        max_nodes=90,
    )
    assert "N8N_WORKFLOW_MATCHES=1" in result
    assert "GRAPH_WORKFLOW_ID=synthetic_active" in result
    assert "trigger=true" in result
    assert "review=true" in result
    assert "downstream=002(0)" in result
    assert "downstream=003(0)" in result
    assert "OFFICIAL_INSERTION_POINT=NOT_YET_APPROVED" in result
    for forbidden in (
        "PRIVATE_CODE_NEVER_PRINT",
        "PRIVATE_SQL_NEVER_PRINT",
        "PRIVATE_CREDENTIAL_NEVER_PRINT",
        "PRIVATE_PARAMETER_NEVER_PRINT",
        "invisible-private-endpoint",
        "https://host.example",
    ):
        assert forbidden not in result, forbidden


def test_many_matches_and_explicit_id():
    src = fixtures()
    result = capture(
        render, src, matches=["unrelated", "synthetic"],
        workflow_id=None, max_workflows=12, max_nodes=90,
    )
    assert "N8N_WORKFLOW_MATCHES=2" in result
    assert "N8N_OFFICIAL_SELECTION=REQUIRED_MULTIPLE_MATCHES" in result
    assert "GRAPH_WORKFLOW_ID=" not in result

    by_id = capture(
        render, src, matches=[],
        workflow_id="synthetic_active", max_workflows=12, max_nodes=2,
    )
    assert "GRAPH_TRUNCATED=1" in by_id
    assert "GRAPH_WORKFLOW_ID=synthetic_active" in by_id

    absent = capture(
        render, src, matches=[],
        workflow_id="absent", max_workflows=12, max_nodes=90,
    )
    assert "N8N_WORKFLOW_ID_NOT_FOUND=true" in absent

    no_selector = capture(
        render, src, matches=[], workflow_id=None,
        max_workflows=12, max_nodes=90,
    )
    assert "N8N_WORKFLOW_MATCHES=0" in no_selector
    assert "Synthetic Finance SQL" not in no_selector


def test_export_schema_and_graph():
    src = fixtures()
    assert parse_workflows(src) == src
    assert parse_workflows(src[0]) == [src[0]]
    assert parse_workflows({"workflows": src}) == src
    assert parse_workflows({"data": src}) == src
    assert edges(src[0]) == [(1, 2, 0), (2, 3, 0)]
    assert safe_title("Bearer abcdefg") == "[secret-redacted]"
    assert "[url-redacted]" in safe_title("example https://host.invalid/key")
    assert "[email-redacted]" in safe_title("tester@example.invalid")


def test_no_exception_or_source_disclosure():
    with TemporaryDirectory() as tmp:
        path = Path(tmp) / "workflows.json"
        path.write_text(json.dumps(fixtures()), encoding="utf-8")
        stdout = io.StringIO()
        with redirect_stdout(stdout):
            assert main([
                "--input", str(path),
                "--match", "Synthetic",
            ]) == 0
        assert "N8N_AUDIT_READONLY=PASS" in stdout.getvalue()

        path.write_text("not-json SECRET_EXPORT_VALUE", encoding="utf-8")
        output = io.StringIO()
        with redirect_stdout(output):
            status = main(["--input", str(path), "--match", "Synthetic"])
        assert status == 3
        assert output.getvalue().strip() == "N8N_AUDIT_INPUT_INVALID"
        assert "SECRET_EXPORT_VALUE" not in output.getvalue()


def test_runner_is_readonly_and_cleans_temporary_export():
    runner = (
        Path(__file__).resolve().parent
        / "scripts/run_n8n_workflow_audit_readonly.sh"
    ).read_text(encoding="utf-8")
    assert "export:workflow --all" in runner
    assert "trap cleanup EXIT" in runner
    assert 'umask 077' in runner
    assert "docker cp" in runner
    assert "export:credentials" not in runner
    assert "import:workflow" not in runner
    assert "update:workflow" not in runner
    assert "publish:workflow" not in runner
    assert "n8n execute" not in runner
    assert "docker compose up" not in runner


if __name__ == "__main__":
    test_safe_inventory_no_parameters_or_secrets()
    test_many_matches_and_explicit_id()
    test_export_schema_and_graph()
    test_no_exception_or_source_disclosure()
    test_runner_is_readonly_and_cleans_temporary_export()
    print("N8N_WORKFLOW_READONLY_AUDIT_OFFLINE=PASS")
