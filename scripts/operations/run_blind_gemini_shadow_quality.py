"""Isolated, operator-gated Gemini-only quality benchmark using a blind dispatch plan.

This is deliberately NOT the n8n Shadow transport or Phase-1 integration proof.
Only question, new run ID and operator-validated scope enter the model runtime.
No historical SQL, intent expectation, result or golden answer enters the child.

Default preflight is pure offline. An explicit live flag, human approval token,
bound call limit and expected Gemini model are all required for generation.
The child runs inside the pre-existing Shadow image with a FAKE evidence store
and reads ONLY semantic context; it never executes financial SQL or changes the
running SQL-InfoDive service or its environment.
"""
from __future__ import annotations

import argparse
from collections.abc import Mapping
import json
import os
from pathlib import Path
import re
import stat
import subprocess
import sys
from typing import Any

from app.domain.shadow_evidence_types import validate_shadow_run_record
from scripts.blind_shadow_batch import (
    collect_post_generation_correlations,
    verify_dispatch_plan,
    _read_private_json,
)
from scripts.blind_shadow_benchmark import (
    evaluate_blind_benchmark,
    load_baseline,
    _write_exclusive,
)

MAX_RECORD_BYTES = 4 * 1024 * 1024
MAX_EXPORT_BYTES = 64 * 1024 * 1024
_ALLOWED_STATUS = frozenset(("success", "rejected", "infrastructure_error"))
_SAFE_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_SAFE_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
APPROVAL = "RUN-BLIND-GEMINI-QUALITY"
LIVE_ENV = "BLIND_GEMINI_LLM_ALLOW_LIVE"

# This script is executed with 'python -u -c' INSIDE the unchanged Shadow
# image. It never reads files containing the n8n baseline or historical SQL.
CHILD = r'''
import asyncio
import json
import os
import sys

from app.adapters.testing.fake_shadow_evidence_repository import FakeShadowEvidenceRepository
from app.infrastructure.http.http_contracts import http_transport_failure
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.integrations.google_gemini.configuration import load_google_gemini_configuration
from app.integrations.google_gemini.sql_generator_adapter import GoogleGeminiSqlGeneratorAdapter
from app.test_runtime.composition import create_shadow_test_runtime

class LimitedProviderTransport:
    def __init__(self, cap):
        self._delegate = StdlibHttpTransport()
        self.cap = cap
        self.calls = 0
    def send(self, request):
        if request.operation_name != "google_gemini_generate_content":
            return http_transport_failure("transport_unavailable")
        if self.calls >= self.cap:
            return http_transport_failure("transport_unavailable")
        self.calls += 1
        return self._delegate.send(request)

class Receive:
    def __init__(self, body):
        self.body = body
        self.used = False
    async def __call__(self):
        if not self.used:
            self.used = True
            return {"type":"http.request","body":self.body,"more_body":False}
        return {"type":"http.disconnect"}

async def run_one(app, token, payload):
    body = json.dumps(payload, separators=(",",":"), ensure_ascii=False).encode()
    scope = {
        "type":"http", "method":"POST",
        "path":"/v1/internal/sql-agent/generate",
        "query_string":b"",
        "headers":[
            (b"content-type",b"application/json"),
            (b"accept",b"application/json"),
            (b"authorization",("Bearer "+token).encode("ascii")),
        ],
    }
    events = []
    async def send(event):
        events.append(event)
    await app(scope, Receive(body), send)
    starts = [e for e in events if e.get("type")=="http.response.start"]
    chunks = [e.get("body",b"") for e in events if e.get("type")=="http.response.body"]
    if len(starts) != 1 or not chunks:
        raise RuntimeError("generation_response_invalid")
    return int(starts[0]["status"]), json.loads(b"".join(chunks))

def main():
    data = json.loads(sys.stdin.readline())
    if set(data) != {"cases","suite","principal_id","organization_id","expected_model","max_provider_calls"}:
        raise RuntimeError("blind_payload_invalid")
    if (os.environ.get("LANGGRAPH_RUNTIME_MODE") != "shadow_test"
        or os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false"
        or os.environ.get("SHADOW_DEFAULT_LLM_SELECTION_JSON","").strip()
        or os.environ.get("OPENAI_COMPATIBLE_SQL_ENABLED","").lower() != "false"):
        raise RuntimeError("gemini_runtime_mode_invalid")
    config = load_google_gemini_configuration()
    if config.model_id != data["expected_model"]:
        raise RuntimeError("gemini_model_identity_changed")
    if not os.environ.get("GEMINI_API_KEY"):
        raise RuntimeError("gemini_key_unavailable")
    repo = FakeShadowEvidenceRepository()
    transport = LimitedProviderTransport(data["max_provider_calls"])
    runtime = create_shadow_test_runtime(
        shadow_repository_override=repo,
        http_transport_override=transport,
    )
    if runtime.config.allow_real_sql_execution or not isinstance(
        runtime.sql_generator, GoogleGeminiSqlGeneratorAdapter
    ):
        raise RuntimeError("wrong_shadow_generator")
    if (runtime.config.expected_organization_id is not None
        and runtime.config.expected_organization_id != data["organization_id"]):
        raise RuntimeError("shadow_organization_scope_mismatch")
    principal = {"id":data["principal_id"],"profile":"vps_shadow_quality_benchmark"}
    if data["organization_id"] is not None:
        principal["organization_id"] = data["organization_id"]
    for case in data["cases"]:
        if transport.calls >= transport.cap:
            raise RuntimeError("provider_call_budget_exhausted")
        request = {
            "contract_version":"1",
            "agent_run_id":case["agent_run_id"],
            "question":case["question"],
            "principal":principal,
            "correlation_metadata":{
                "source":"vps_operator_shadow_quality",
                "suite":data["suite"],
                "case_id":case["case_id"],
                "event":"generate",
            },
        }
        http_status, response = asyncio.run(run_one(
            runtime.app, runtime.config.s2s_token, request,
        ))
        matches = repo.list_by_agent_run_id(case["agent_run_id"])["records"]
        if len(matches) != 1 or matches[0]["run_id"] != response.get("run_id"):
            raise RuntimeError("signed_generation_evidence_missing")
        print(json.dumps({
            "case_id":case["case_id"], "agent_run_id":case["agent_run_id"],
            "record":matches[0],
            "http_status":http_status, "status":response.get("status"),
            "provider_calls_total":transport.calls,
        }, ensure_ascii=False, separators=(",",":")), flush=True)

main()
'''


def _validated_inputs(
    manifest: Any, receipt: Any, plan: Any, expected_count: int,
) -> list[dict[str, str]]:
    verify_dispatch_plan(manifest, receipt, plan)
    if type(expected_count) is not int or len(plan["cases"]) != expected_count:
        raise ValueError("expected_blind_case_count_mismatch")
    return plan["cases"]


def _private_output_directory(path: str) -> Path:
    directory = Path(path)
    if not directory.is_absolute() or directory.is_symlink():
        raise ValueError("output_directory_invalid")
    if directory.exists():
        if any(directory.iterdir()):
            raise ValueError("output_directory_not_empty")
    else:
        if not directory.parent.is_dir() or directory.parent.is_symlink():
            raise ValueError("output_parent_invalid")
        directory.mkdir(mode=0o700)
    state = directory.stat()
    if (not stat.S_ISDIR(state.st_mode) or state.st_uid != os.geteuid()
            or state.st_mode & 0o077):
        raise ValueError("output_directory_permissions_invalid")
    return directory


def _validated_child_line(
    raw: str, case: Mapping[str, str], previous_calls: int, limit: int,
) -> tuple[dict[str, Any], int]:
    if not isinstance(raw, str) or len(raw.encode("utf-8")) > MAX_RECORD_BYTES:
        raise ValueError("provider_record_too_large")
    msg = json.loads(raw)
    if (not isinstance(msg, dict)
            or set(msg) != {
                "case_id", "agent_run_id", "record",
                "http_status", "status", "provider_calls_total",
            }
            or msg["case_id"] != case["case_id"]
            or msg["agent_run_id"] != case["agent_run_id"]
            or type(msg["provider_calls_total"]) is not int
            or not previous_calls <= msg["provider_calls_total"] <= limit
            or type(msg["http_status"]) is not int
            or msg["http_status"] not in (200, 422, 503)
            or msg["status"] not in _ALLOWED_STATUS):
        raise ValueError("provider_receipt_invalid")
    record = validate_shadow_run_record(msg["record"])
    if (record["agent_run_id"] != case["agent_run_id"]
            or record.get("question") != case["question"]
            or record.get("event_type") != "generate"
            or record.get("status") != msg["status"]
            or not isinstance(record.get("principal"), Mapping)
            or record["run_id"] != msg["record"].get("run_id")):
        raise ValueError("signed_provider_record_mismatch")
    return record, msg["provider_calls_total"]


def _evaluate_after_generation(
    manifest: Mapping[str, Any],
    receipt: Mapping[str, Any],
    plan: Mapping[str, Any],
    baseline: Mapping[str, Any],
    records: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    frozen = load_baseline(baseline)
    evidence = {"contract_version":"1", "records":records}
    correlation = collect_post_generation_correlations(
        manifest, receipt, plan, evidence,
    )
    report = evaluate_blind_benchmark(
        frozen, manifest, evidence, receipt,
        dispatch_plan=plan, correlation=correlation,
    )
    if report["benchmark_exposed_to_generator"] is not False:
        raise ValueError("blind_generation_contract_violation")
    return correlation, report


def _run_live(args: Any, manifest: dict, receipt: dict, plan: dict) -> int:
    if (args.approve != APPROVAL
            or os.environ.get(LIVE_ENV) != "true"
            or os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION","false") != "false"):
        print("BLIND_GEMINI=BLOCKED_EXPLICIT_LLM_APPROVAL_REQUIRED")
        return 3
    if os.name != "posix" or os.geteuid() != 0:
        print("BLIND_GEMINI=BLOCKED_ROOT_LOCAL_OPERATOR_REQUIRED")
        return 3
    if (not _SAFE_CONTAINER.fullmatch(args.shadow_container)
            or not _SAFE_ID.fullmatch(args.principal_id)
            or (args.organization_id and not _SAFE_ID.fullmatch(args.organization_id))
            or not _SAFE_ID.fullmatch(args.expected_model)
            or type(args.max_provider_calls) is not int
            or not 1 <= args.max_provider_calls <= 768):
        print("BLIND_GEMINI=BLOCKED_LIVE_ARGUMENTS_INVALID")
        return 3
    # Never load the baseline before or inside the model runtime.
    directory = _private_output_directory(args.output_dir)
    command = [
        "docker", "exec", "-i",
        "-e", "SHADOW_DEFAULT_LLM_SELECTION_JSON=",
        "-e", "OPENAI_COMPATIBLE_SQL_ENABLED=false",
        args.shadow_container, "python", "-u", "-c", CHILD,
    ]
    payload = {
        "cases":plan["cases"], "suite":plan["suite"],
        "principal_id":args.principal_id,
        "organization_id":args.organization_id,
        "expected_model":args.expected_model,
        "max_provider_calls":args.max_provider_calls,
    }
    process = subprocess.Popen(
        command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL, text=True, encoding="utf-8",
    )
    records: list[dict[str, Any]] = []
    calls = 0
    try:
        if process.stdin is None or process.stdout is None:
            raise ValueError("docker_transport_unavailable")
        process.stdin.write(json.dumps(payload, ensure_ascii=False) + "\n")
        process.stdin.close()
        for index, case in enumerate(plan["cases"], start=1):
            line = process.stdout.readline(MAX_RECORD_BYTES + 1)
            if not line:
                raise ValueError("docker_generation_ended_before_all_cases")
            record, calls = _validated_child_line(
                line, case, calls, args.max_provider_calls,
            )
            _write_exclusive(str(directory / f"{index:03}-signed-record.json"),
                             record)
            records.append(record)
            print(f"BLIND_GEMINI_CASE={index}/{len(plan['cases'])}"
                  f" STATUS={record['status']}", flush=True)
        if process.wait(timeout=20) != 0:
            raise ValueError("gemini_worker_failed")
    except (OSError, ValueError, TypeError, KeyError, UnicodeError,
            subprocess.SubprocessError):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=10)
        print("BLIND_GEMINI=BLOCKED_PARTIAL_PRIVATE_RECORDS_RETAINED")
        print("BLIND_GEMINI_CAPTURED_RECORDS=" + str(len(records)))
        print("BLIND_GEMINI_PROVIDER_CALLS_OBSERVED=" + str(calls))
        return 2
    evidence = {"contract_version":"1", "records":records}
    encoded = json.dumps(evidence, separators=(",",":"), ensure_ascii=False).encode()
    if len(encoded) > MAX_EXPORT_BYTES:
        print("BLIND_GEMINI=BLOCKED_EVIDENCE_SIZE")
        return 2
    _write_exclusive(str(directory / "shadow-records-v1.json"), evidence)
    # This is the first step that opens the historical SQL baseline.
    frozen = _read_private_json(args.baseline)
    correlation, report = _evaluate_after_generation(
        manifest, receipt, plan, frozen, records,
    )
    _write_exclusive(str(directory / "post-generation-correlation-v1.json"),
                     correlation)
    _write_exclusive(str(directory / "structural-evaluation-v1.json"), report)
    print("BLIND_GEMINI=PASS")
    print("BLIND_GEMINI_CASES=" + str(len(records)))
    print("BLIND_GEMINI_PROVIDER_CALLS_OBSERVED=" + str(calls))
    print("BLIND_GEMINI_STRUCTURAL_SUMMARY=" +
          json.dumps(report["summary"], ensure_ascii=False, sort_keys=True))
    print("BLIND_GEMINI_N8N_TRANSPORT_TESTED=false")
    print("BLIND_GEMINI_FINANCIAL_SQL_EXECUTED=false")
    print("BLIND_GEMINI_SHADOW_DATABASE_WRITTEN=false")
    print("BLIND_GEMINI_PROVIDER_COST_USD=NOT_ATTESTED")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Blind standalone Gemini Shadow quality test")
    parser.add_argument("action", choices=("preflight", "run"))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--dispatch-plan", required=True)
    parser.add_argument("--expected-cases", required=True, type=int)
    parser.add_argument("--baseline")
    parser.add_argument("--output-dir")
    parser.add_argument("--shadow-container")
    parser.add_argument("--principal-id")
    parser.add_argument("--organization-id")
    parser.add_argument("--expected-model")
    parser.add_argument("--max-provider-calls", type=int)
    parser.add_argument("--approve")
    args = parser.parse_args()
    try:
        manifest = _read_private_json(args.manifest)
        receipt = _read_private_json(args.receipt)
        plan = _read_private_json(args.dispatch_plan)
        cases = _validated_inputs(manifest, receipt, plan, args.expected_cases)
        if args.action == "preflight":
            print("BLIND_GEMINI_PREFLIGHT=PASS")
            print("BLIND_GEMINI_CASES=" + str(len(cases)))
            print("BLIND_GEMINI_PROVIDER_CALLS=0")
            print("BLIND_GEMINI_FINANCIAL_SQL_EXECUTED=false")
            return 0
        if not all((
            args.baseline, args.output_dir, args.shadow_container,
            args.principal_id, args.expected_model, args.max_provider_calls,
        )):
            raise ValueError("live_arguments_missing")
        return _run_live(args, manifest, receipt, plan)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        print("BLIND_GEMINI=BLOCKED_INVALID_OR_INCOMPLETE_INPUT")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
