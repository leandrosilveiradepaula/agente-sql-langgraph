"""Jornada G1: real n8n Code nodes + real LangGraph S2S ASGI + evidence API.

All I/O is local Node.js subprocess and in-memory ASGI. This is an
integration *contract rehearsal*, not a deployed n8n run, Vercel traffic,
Gemini output, financial query execution or authorization for activation.

The n8n candidate is parsed from its actual checked-in, inactive JSON and
its private offline renderer. The incoming structural envelope mirrors the
Product's versioned lib/langgraph-shadow-client.ts contract (it is not
produced by the deployed Product). Neither baseline SQL nor financial
expectations are provided to the SQL generator.
"""
from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlencode

from app.adapters.testing.fake_shadow_evidence_repository import (
    FakeShadowEvidenceRepository,
)
from app.adapters.testing.shadow_run_visualization_fixtures import (
    generate_for_agent,
)
from app.domain.result_normalization import stable_fingerprint
from app.domain.shadow_evidence_types import (
    _fingerprint_payload,
    validate_shadow_run_record,
)
from app.test_runtime.composition import create_shadow_test_runtime
from app.test_runtime.offline_adapters import (
    OFFLINE_SQL,
    ShadowTestContextRepository,
    ShadowTestSqlGenerator,
    ShadowTestSqlRepairer,
)
from scripts.n8n.render_parallel_shadow_workflow import render_private_candidate
from testar_internal_shadow_read_v1_http_handler import _env, _run_asgi

ROOT = Path(__file__).resolve().parent
SYNTHETIC_ORGANIZATION = "synthetic-tenant-one"
AGENT_RUN_ID = "synthetic-agent-run-20261023"
QUESTION = "Execute uma generic analysis de teste."
RENDERED = render_private_candidate("http://shadow-internal:8000")


def _n8n_code(
    name: str, incoming: dict, *, previous: dict[str, dict] | None = None,
) -> dict:
    """Execute the actual n8n Code node without any real n8n integration."""
    node = shutil.which("node")
    if not node:
        raise AssertionError("Node.js is required for offline n8n contract tests")
    source = r"""
const flow = JSON.parse(process.argv[1]);
const name = process.argv[2];
const input = JSON.parse(process.argv[3]);
const previous = JSON.parse(process.argv[4]);
const selected = flow.nodes.find(item => item.name === name);
if (!selected || typeof selected.parameters.jsCode !== "string") {
  throw new Error("SIMULATED_NODE_NOT_FOUND");
}
const mockInput = {first() { return {json: input}; }};
const mockPrevious = key => ({
  first() {
    if (!(key in previous)) throw new Error("SIMULATED_PRIOR_NODE_MISSING");
    return {json: previous[key]};
  }
});
const result = new Function("$input", "$", selected.parameters.jsCode)(
  mockInput, mockPrevious
);
if (!Array.isArray(result) || result.length !== 1) {
  throw new Error("SIMULATED_N8N_OUTPUT_INVALID");
}
process.stdout.write(JSON.stringify(result[0].json));
"""
    completed = subprocess.run(
        [
            node, "-e", source, json.dumps(RENDERED),
            name, json.dumps(incoming), json.dumps(previous or {}),
        ],
        cwd=ROOT,
        check=False, capture_output=True, encoding="utf-8",
        errors="replace", timeout=30,
    )
    if completed.returncode != 0:
        # Never surface raw node output (which may include SQL in a real
        # workflow). A fixed sanitized error is adequate for this test.
        raise AssertionError("N8N_OFFLINE_CONTRACT_NODE_FAILED")
    return json.loads(completed.stdout)


def _n8n_expression(name: str, field: str, item: dict) -> str:
    node = shutil.which("node")
    if not node:
        raise AssertionError("Node.js is required for offline n8n contract tests")
    source = r"""
const flow = JSON.parse(process.argv[1]);
const name = process.argv[2], field = process.argv[3];
const data = JSON.parse(process.argv[4]);
const target = flow.nodes.find(node => node.name === name);
const expression = target?.parameters?.[field];
if (typeof expression !== "string" ||
    !expression.startsWith("={{") || !expression.endsWith("}}")) {
  throw new Error("SIMULATED_EXPRESSION_INVALID");
}
const result = new Function("$json", "$env", "return (" +
  expression.slice(3, -2) + ");")(data, {});
process.stdout.write(String(result));
"""
    completed = subprocess.run(
        [node, "-e", source, json.dumps(RENDERED), name, field,
         json.dumps(item)],
        cwd=ROOT, check=False, capture_output=True, encoding="utf-8",
        errors="replace", timeout=30,
    )
    if completed.returncode != 0:
        raise AssertionError("N8N_OFFLINE_CONTRACT_EXPRESSION_FAILED")
    return completed.stdout


def _product_envelope(event: str, *, organization: str = SYNTHETIC_ORGANIZATION) -> dict:
    assert event in {"generate", "execute_approved"}
    return {
        "contract_version": "1",
        "agent_run_id": AGENT_RUN_ID,
        "principal": {
            "id": "synthetic-user",
            "email": "synthetic@example.invalid",
            "profile": "runtime_validation",
            "organization_id": organization,
        },
        "correlation_metadata": {
            "source": "nextjs_bff",
            "event": event,
            "route": "/api/generate-sql" if event == "generate" else "/api/execute-watson",
            "timestamp": "2026-10-23T15:00:00.000Z",
            "request_id": f"synthetic-request-{event}",
            "agent_version": "synthetic-semantic-version",
        },
        **(
            {"question": QUESTION}
            if event == "generate"
            else {"approved_sql": OFFLINE_SQL}
        ),
        # A malicious/mistaken baseline hint is never an input to the
        # LangGraph generator through the transport allowlist.
        "golden_answer": "synthetic-forbidden-evaluation-only-sentinel",
    }


def _synthetic_old_record(run_id: str) -> dict:
    record = generate_for_agent(AGENT_RUN_ID, run_id)
    record["principal"]["organization_id"] = SYNTHETIC_ORGANIZATION
    digest = stable_fingerprint(_fingerprint_payload(record))
    record["fingerprints"]["evidence_payload"] = digest
    record["evidence_fingerprint"] = digest
    return validate_shadow_run_record(record)


def _runtime():
    repository = FakeShadowEvidenceRepository()
    # Simulate >10 older successful attempts that previously hid the newly
    # accepted attempt from n8n's bounded evidence read.
    for index in range(13):
        assert repository.create(
            _synthetic_old_record(f"old-run-{index:03d}")
        )["status"] == "created"
    generator = ShadowTestSqlGenerator()
    env = _env()
    env["LANGGRAPH_EXPECTED_ORGANIZATION_ID"] = SYNTHETIC_ORGANIZATION
    runtime = create_shadow_test_runtime(
        env,
        shadow_repository_override=repository,
        context_repository_override=ShadowTestContextRepository(),
        sql_generator_override=generator,
        sql_repairer_override=ShadowTestSqlRepairer(),
    )
    assert runtime.config.allow_real_sql_execution is False
    return runtime, repository, generator


def _process_cycle(runtime, event: str) -> tuple[dict, dict, dict]:
    envelope = _product_envelope(event)
    prepared = _n8n_code("Validate Shadow Envelope", {"body": envelope})
    assert prepared["event"] == event
    assert prepared["agent_run_id"] == AGENT_RUN_ID
    assert "golden_answer" not in json.dumps(prepared, ensure_ascii=False)
    assert prepared["shadow_request"]["principal"]["organization_id"] == (
        SYNTHETIC_ORGANIZATION
    )

    ack = json.loads(_n8n_expression(
        "Acknowledge Shadow Receipt", "responseBody", prepared,
    ))
    assert ack == {
        "contract_version": "1", "accepted": True,
        "agent_run_id": AGENT_RUN_ID, "event": event,
    }
    target = _n8n_expression("Call LangGraph Shadow", "url", prepared)
    assert target.endswith(prepared["target_path"])
    assert target.startswith("http://shadow-internal:8000/v1/internal/")

    post_status, post_body = _run_asgi(
        runtime.app, "POST", prepared["target_path"],
        prepared["shadow_request"],
    )
    assert post_status == 200, (event, post_status, post_body.get("status"))
    assert post_body["status"] == "success", (event, post_body.get("status"))
    assert post_body["agent_run_id"] == AGENT_RUN_ID
    assert isinstance(post_body["run_id"], str) and post_body["run_id"]

    accepted = _n8n_code(
        "Validate LangGraph Response",
        {"statusCode": post_status, "body": post_body},
        previous={"Validate Shadow Envelope": prepared},
    )
    assert accepted["run_id"] == post_body["run_id"]
    assert accepted["status"] == post_body["status"]
    read_url = _n8n_expression(
        "Read Correlated Evidence", "url", accepted,
    )
    exact_query = urlencode({"run_id": accepted["run_id"], "limit": 10})
    assert read_url.endswith(
        "/v1/internal/agent-runs/" + AGENT_RUN_ID + "/shadow-runs?" + exact_query
    ), "Exact attempt was not forwarded to the evidence lookup"
    read_status, read_body = _run_asgi(
        runtime.app, "GET",
        "/v1/internal/agent-runs/" + AGENT_RUN_ID + "/shadow-runs",
        query_string=exact_query,
    )
    # Only a fixed safe code is printed on failure, never questions/SQL.
    assert read_status == 200, (
        "G1_EVIDENCE_READ_NOT_OK", read_status,
        (read_body.get("error") or {}).get("code", "NO_SAFE_ERROR_CODE"),
    )
    assert len(read_body["items"]) == 1
    # Run the actual final n8n Code node (not a parallel mock assertion).
    confirmed = _n8n_code(
        "Assert Shadow Evidence",
        {"statusCode": read_status, "body": read_body},
        previous={"Validate LangGraph Response": accepted},
    )
    assert confirmed["correlated"] is True
    assert confirmed["run_id"] == post_body["run_id"]
    assert confirmed["status"] == "success"
    assert confirmed["shadow_record_id"] == read_body["items"][0]["shadow_record_id"]
    assert confirmed["event"] == event
    assert "SELECT" not in json.dumps(confirmed)
    assert "token" not in json.dumps(confirmed).casefold()
    return prepared, post_body, confirmed


def test_offline_bff_envelope_n8n_langgraph_generate_and_approved_event() -> None:
    runtime, repository, generator = _runtime()
    _, generate, generate_evidence = _process_cycle(runtime, "generate")
    assert generator.calls == 1
    _, execute, execute_evidence = _process_cycle(runtime, "execute_approved")
    assert generator.calls == 1  # No new SQL generation on approved SQL event.
    assert generate["run_id"] != execute["run_id"]
    assert generate_evidence["shadow_record_id"] != execute_evidence["shadow_record_id"]
    assert len(repository.records) == 15
    assert all(
        record["principal"]["organization_id"] == SYNTHETIC_ORGANIZATION
        for record in repository.records.values()
    )
    assert runtime.config.allow_real_sql_execution is False


def test_foreign_tenant_fails_before_provider_and_evidence() -> None:
    runtime, repository, generator = _runtime()
    count = len(repository.records)
    prepared = _n8n_code(
        "Validate Shadow Envelope",
        {"body": _product_envelope("generate", organization="foreign-tenant")},
    )
    assert prepared["shadow_request"]["principal"]["organization_id"] == "foreign-tenant"
    code, response = _run_asgi(
        runtime.app, "POST", prepared["target_path"],
        prepared["shadow_request"],
    )
    assert code in (401, 403, 422)
    assert response.get("status") != "success"
    assert not response.get("sql")
    assert generator.calls == 0
    assert len(repository.records) == count
    assert SYNTHETIC_ORGANIZATION not in json.dumps(response)
    assert "SELECT" not in json.dumps(response)


def main() -> None:
    tests = (
        test_offline_bff_envelope_n8n_langgraph_generate_and_approved_event,
        test_foreign_tenant_fails_before_provider_and_evidence,
    )
    for test in tests:
        test()
        print(test.__name__ + ": PASS")
    print("G1_N8N_LANGGRAPH_OFFLINE_BRIDGE=PASS")


if __name__ == "__main__":
    main()
