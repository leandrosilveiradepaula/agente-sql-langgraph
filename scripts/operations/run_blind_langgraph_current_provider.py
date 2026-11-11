"""Replay frozen blind questions through EXISTING LangGraph/LLM configuration.

The 63 n8n/Gemini historical answers are EVALUATION ONLY.
No generation call may go to Gemini. The child refuses a Gemini provider,
clears its Gemini API credential, and only permits the currently configured
OpenAI-compatible private SQL model transport.

Offline preflight is default. Real model requests need explicit cost approval
and a bounded per-batch call count. This is an isolated LangGraph quality test,
NOT n8n/Product authenticated integration or financial SQL execution.
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
from typing import Any

from app.domain.shadow_evidence_types import validate_shadow_run_record
from scripts.blind_shadow_batch import (
    _read_private_json,
    collect_post_generation_correlations,
    verify_dispatch_plan,
)
from scripts.blind_shadow_benchmark import (
    _write_exclusive,
    evaluate_blind_benchmark,
    load_baseline,
)

APPROVAL = "RUN-63-LANGGRAPH-PRIVATE-LLM"
LIVE_FLAG = "BLIND_LANGGRAPH_LLM_ALLOW_LIVE"
RECORD_MAX_BYTES = 4 * 1024 * 1024
EXPORT_MAX_BYTES = 64 * 1024 * 1024
SAFE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
SAFE_CONTAINER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")

# CHILD goes to a new Python process inside the already configured Shadow
# container. No baseline, expected SQL, intended filters, or n8n golden answers
# are copied, loaded or passed to this process. Gemini credentials are blanked.
CHILD = r'''
import asyncio
import json
import os
import sys

from app.adapters.testing.fake_shadow_evidence_repository import FakeShadowEvidenceRepository
from app.infrastructure.http.http_contracts import http_transport_failure
from app.infrastructure.http.stdlib_http_transport import StdlibHttpTransport
from app.integrations.openai_compatible.configuration import load_openai_compatible_configuration
from app.integrations.openai_compatible.sql_generator_adapter import OpenAiCompatibleSqlGeneratorAdapter
from app.test_runtime.composition import create_shadow_test_runtime

class PrivateModelOnlyTransport:
    def __init__(self, maximum):
        self.delegate = StdlibHttpTransport()
        self.maximum = maximum
        self.calls = 0

    def send(self, request):
        # Not even an accidental alternate provider is allowed onto the wire.
        if request.operation_name != "openai_compatible_chat_completions":
            return http_transport_failure("transport_unavailable")
        if self.calls >= self.maximum:
            return http_transport_failure("transport_unavailable")
        self.calls += 1
        return self.delegate.send(request)

class Receive:
    def __init__(self, body):
        self.body = body
        self.used = False

    async def __call__(self):
        if not self.used:
            self.used = True
            return {"type":"http.request","body":self.body,"more_body":False}
        return {"type":"http.disconnect"}

async def generate_once(app, token, payload):
    data = json.dumps(payload, ensure_ascii=False, separators=(",",":")).encode()
    events = []
    async def send(event):
        events.append(event)
    scope = {
        "type":"http", "method":"POST",
        "path":"/v1/internal/sql-agent/generate",
        "query_string":b"",
        "headers":[
            (b"content-type", b"application/json"),
            (b"accept", b"application/json"),
            (b"authorization", ("Bearer "+token).encode("ascii")),
        ],
    }
    await app(scope, Receive(data), send)
    start = [e for e in events if e.get("type")=="http.response.start"]
    parts = [e.get("body",b"") for e in events if e.get("type")=="http.response.body"]
    if len(start)!=1 or not parts:
        raise RuntimeError("shadow_generate_http_invalid")
    return int(start[0]["status"]), json.loads(b"".join(parts))

def main():
    batch = json.loads(sys.stdin.readline())
    if set(batch) != {
        "cases", "suite", "principal_id", "organization_id",
        "expected_provider", "expected_model", "max_provider_calls"
    } or len(batch["cases"]) < 1:
        raise RuntimeError("blind_payload_invalid")
    if (os.environ.get("LANGGRAPH_RUNTIME_MODE") != "shadow_test"
        or os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION") != "false"
        or os.environ.get("GEMINI_API_KEY","") != ""):
        raise RuntimeError("langgraph_shadow_safety_invalid")
    configured = json.loads(os.environ.get("SHADOW_DEFAULT_LLM_SELECTION_JSON") or "{}")
    compatible = load_openai_compatible_configuration()
    if compatible is None or set(configured) != {
        "provider_key", "model_key", "config_version"
    }:
        raise RuntimeError("existing_private_provider_unavailable")
    identity = {
        "provider_key":compatible.provider_key,
        "model_key":compatible.model_id,
        "config_version":compatible.config_version,
    }
    if (configured != identity
        or compatible.provider_key != batch["expected_provider"]
        or compatible.model_id != batch["expected_model"]
        or "gemini" in compatible.provider_key.casefold()
        or "gemini" in compatible.model_id.casefold()):
        raise RuntimeError("existing_private_model_identity_mismatch")
    if not os.environ.get(compatible.api_key_secret_name):
        raise RuntimeError("existing_private_provider_credential_missing")

    org = os.environ.get("LANGGRAPH_EXPECTED_ORGANIZATION_ID")
    if not org or batch["organization_id"] != org:
        raise RuntimeError("organization_scope_unattested")

    evidence_store = FakeShadowEvidenceRepository()
    provider_transport = PrivateModelOnlyTransport(batch["max_provider_calls"])
    runtime = create_shadow_test_runtime(
        shadow_repository_override=evidence_store,
        http_transport_override=provider_transport,
    )
    if (runtime.config.allow_real_sql_execution
        or not isinstance(runtime.sql_generator, OpenAiCompatibleSqlGeneratorAdapter)
        or runtime.config.expected_organization_id != batch["organization_id"]):
        raise RuntimeError("unexpected_langgraph_runtime")

    principal = {
        "id":batch["principal_id"],
        "organization_id":batch["organization_id"],
        "profile":"offline_langgraph_quality",
    }
    for case in batch["cases"]:
        if provider_transport.calls >= provider_transport.maximum:
            raise RuntimeError("private_provider_call_cap_exhausted")
        request = {
            "contract_version":"1",
            "agent_run_id":case["agent_run_id"],
            "question":case["question"],
            "principal":principal,
            "correlation_metadata":{
                "source":"vps_operator_langgraph_quality",
                "event":"generate",
                "case_id":case["case_id"],
                "suite":batch["suite"],
            },
        }
        status_code, response = asyncio.run(generate_once(
            runtime.app, runtime.config.s2s_token, request,
        ))
        observed = evidence_store.list_by_agent_run_id(
            case["agent_run_id"],
        )["records"]
        if (len(observed)!=1
            or observed[0]["run_id"] != response.get("run_id")
            or observed[0]["agent_run_id"] != case["agent_run_id"]):
            raise RuntimeError("langgraph_signed_evidence_missing")
        record = observed[0]
        provider_metadata = record.get("langgraph_evidence",{}).get(
            "provider_metadata",{}
        )
        if record["status"] == "success":
            if (provider_metadata.get("sql_generation_result_provider_name")
                != compatible.provider_key
                or provider_metadata.get("sql_generation_result_provider_model")
                != compatible.model_id):
                raise RuntimeError("generated_sql_provider_identity_unattested")
        print(json.dumps({
            "case_id":case["case_id"],
            "agent_run_id":case["agent_run_id"],
            "record":record,
            "http_status":status_code,
            "status":response.get("status"),
            "provider_calls_total":provider_transport.calls,
        }, ensure_ascii=False, separators=(",",":")), flush=True)
        if record["status"] == "infrastructure_error":
            # Fail early instead of repeating a broken endpoint 63 times.
            raise RuntimeError("private_model_or_context_infrastructure_failed")
main()
'''


def validate_blind_inputs(
    manifest: Any, receipt: Any, plan: Any, expected_cases: int,
) -> list[dict[str, str]]:
    verify_dispatch_plan(manifest, receipt, plan)
    if type(expected_cases) is not int or expected_cases <= 0:
        raise ValueError("invalid_expected_case_count")
    if len(plan["cases"]) != expected_cases:
        raise ValueError("case_count_mismatch")
    return plan["cases"]


def _private_directory(path: str) -> Path:
    target = Path(path)
    if not target.is_absolute() or target.is_symlink():
        raise ValueError("unsafe_output_path")
    if target.exists():
        if not target.is_dir() or any(target.iterdir()):
            raise ValueError("output_directory_not_empty")
    else:
        if not target.parent.is_dir() or target.parent.is_symlink():
            raise ValueError("unsafe_output_parent")
        target.mkdir(mode=0o700)
    mode = target.stat()
    if (not stat.S_ISDIR(mode.st_mode)
        or mode.st_uid != os.geteuid()
        or mode.st_mode & 0o077):
        raise ValueError("output_directory_permissions_invalid")
    return target


def validate_result_line(
    line: str, planned: Mapping[str, str], previous_calls: int, call_limit: int,
) -> tuple[dict[str, Any], int]:
    if len(line.encode("utf-8")) > RECORD_MAX_BYTES:
        raise ValueError("record_size_invalid")
    msg = json.loads(line)
    if (not isinstance(msg, dict)
        or set(msg) != {
            "case_id", "agent_run_id", "record", "http_status",
            "status", "provider_calls_total",
        }
        or msg["case_id"] != planned["case_id"]
        or msg["agent_run_id"] != planned["agent_run_id"]
        or type(msg["provider_calls_total"]) is not int
        or not previous_calls <= msg["provider_calls_total"] <= call_limit
        or type(msg["http_status"]) is not int
        or msg["http_status"] not in (200, 422, 503)
        or msg["status"] not in ("success", "rejected", "infrastructure_error")):
        raise ValueError("record_receipt_invalid")
    record = validate_shadow_run_record(msg["record"])
    if (record.get("agent_run_id") != planned["agent_run_id"]
        or record.get("question") != planned["question"]
        or record.get("event_type") != "generate"
        or record.get("status") != msg["status"]
        or not isinstance(record.get("principal"), Mapping)):
        raise ValueError("record_fingerprint_or_origin_invalid")
    return record, msg["provider_calls_total"]


def _run(args: Any, manifest: dict, receipt: dict, plan: dict) -> int:
    if (args.approve != APPROVAL
        or os.environ.get(LIVE_FLAG) != "true"
        or os.environ.get("LANGGRAPH_ALLOW_REAL_SQL_EXECUTION", "false") != "false"):
        print("LANGGRAPH_63=BLOCKED_EXPLICIT_LLM_AUTHORIZATION_REQUIRED")
        return 3
    if os.name != "posix" or os.geteuid() != 0:
        print("LANGGRAPH_63=BLOCKED_LOCAL_ROOT_REQUIRED")
        return 3
    if (not SAFE_CONTAINER.fullmatch(args.shadow_container)
        or not SAFE_NAME.fullmatch(args.principal_id)
        or not SAFE_NAME.fullmatch(args.organization_id)
        or not SAFE_NAME.fullmatch(args.expected_provider)
        or not SAFE_NAME.fullmatch(args.expected_model)
        or "gemini" in args.expected_provider.casefold()
        or "gemini" in args.expected_model.casefold()
        or type(args.max_provider_calls) is not int
        or args.max_provider_calls < len(plan["cases"])
        or args.max_provider_calls > len(plan["cases"]) * 3):
        print("LANGGRAPH_63=BLOCKED_RUNTIME_CONFIGURATION_INVALID")
        return 3

    output_dir = _private_directory(args.output_dir)
    # This process receives ONLY blind case questions and operator scope.
    payload = {
        "cases":plan["cases"],
        "suite":plan["suite"],
        "principal_id":args.principal_id,
        "organization_id":args.organization_id,
        "expected_provider":args.expected_provider,
        "expected_model":args.expected_model,
        "max_provider_calls":args.max_provider_calls,
    }
    process = subprocess.Popen(
        ["docker", "exec", "-i",
         "-e", "GEMINI_API_KEY=",
         args.shadow_container, "python", "-u", "-c", CHILD],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
        text=True, encoding="utf-8",
    )
    records: list[dict[str, Any]] = []
    last_calls = 0
    try:
        if process.stdin is None or process.stdout is None:
            raise ValueError("child_stream_unavailable")
        process.stdin.write(json.dumps(
            payload, separators=(",", ":"), ensure_ascii=False,
        ) + "\n")
        process.stdin.close()
        for index, case in enumerate(plan["cases"], 1):
            line = process.stdout.readline(RECORD_MAX_BYTES + 1)
            if not line:
                raise ValueError("langgraph_child_did_not_complete_all_cases")
            record, last_calls = validate_result_line(
                line, case, last_calls, args.max_provider_calls,
            )
            _write_exclusive(
                str(output_dir / f"{index:03}-signed-record.json"), record,
            )
            records.append(record)
            print("LANGGRAPH_63_CASE=" + str(index) + "/" +
                  str(len(plan["cases"])) +
                  " STATUS=" + record["status"], flush=True)
        if process.wait(timeout=30) != 0:
            raise ValueError("langgraph_child_failed")
    except (OSError, ValueError, TypeError, KeyError,
            subprocess.SubprocessError, UnicodeError):
        if process.poll() is None:
            process.kill()
        process.wait(timeout=15)
        print("LANGGRAPH_63=BLOCKED_PARTIAL_EVIDENCE_RETAINED")
        print("LANGGRAPH_63_CASES_RECORDED=" + str(len(records)))
        print("LANGGRAPH_63_PROVIDER_CALLS_OBSERVED=" + str(last_calls))
        return 2

    export = {"contract_version":"1", "records":records}
    if len(json.dumps(export, ensure_ascii=False).encode("utf-8")) > EXPORT_MAX_BYTES:
        print("LANGGRAPH_63=BLOCKED_EVIDENCE_SIZE_LIMIT")
        return 2
    _write_exclusive(str(output_dir / "shadow-records-v1.json"), export)

    # Official n8n answers are first loaded AFTER all LangGraph generations.
    frozen = load_baseline(_read_private_json(args.baseline))
    correlations = collect_post_generation_correlations(
        manifest, receipt, plan, export,
    )
    scored = evaluate_blind_benchmark(
        frozen, manifest, export, receipt,
        dispatch_plan=plan, correlation=correlations,
    )
    _write_exclusive(
        str(output_dir / "post-generation-correlation-v1.json"), correlations,
    )
    _write_exclusive(
        str(output_dir / "structural-evaluation-v1.json"), scored,
    )
    print("LANGGRAPH_63=PASS")
    print("LANGGRAPH_63_CASES=" + str(len(records)))
    print("LANGGRAPH_63_PROVIDER_CALLS_OBSERVED=" + str(last_calls))
    print("LANGGRAPH_63_STRUCTURAL_SUMMARY=" +
          json.dumps(scored["summary"], sort_keys=True))
    print("LANGGRAPH_63_GEMINI_CALLS=0")
    print("LANGGRAPH_63_N8N_OFFICIAL_RERUN=false")
    print("LANGGRAPH_63_FINANCIAL_SQL_EXECUTED=false")
    print("LANGGRAPH_63_SHADOW_DATABASE_WRITTEN=false")
    print("LANGGRAPH_63_PROVIDER_COST=UNATTESTED")
    print("LANGGRAPH_63_N8N_INTEGRATION_TESTED=false")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Replay blind historical n8n questions through existing LangGraph private model"
    )
    parser.add_argument("action", choices=("preflight", "run"))
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--receipt", required=True)
    parser.add_argument("--dispatch-plan", required=True)
    parser.add_argument("--expected-cases", type=int, required=True)
    parser.add_argument("--baseline")
    parser.add_argument("--output-dir")
    parser.add_argument("--shadow-container")
    parser.add_argument("--principal-id")
    parser.add_argument("--organization-id")
    parser.add_argument("--expected-provider")
    parser.add_argument("--expected-model")
    parser.add_argument("--max-provider-calls", type=int)
    parser.add_argument("--approve")
    args = parser.parse_args()
    try:
        manifest = _read_private_json(args.manifest)
        receipt = _read_private_json(args.receipt)
        plan = _read_private_json(args.dispatch_plan)
        cases = validate_blind_inputs(
            manifest, receipt, plan, args.expected_cases,
        )
        if args.action == "preflight":
            print("LANGGRAPH_63_PREFLIGHT=PASS")
            print("LANGGRAPH_63_CASES=" + str(len(cases)))
            print("LANGGRAPH_63_PROVIDER_CALLS=0")
            print("LANGGRAPH_63_GEMINI_CALLS=0")
            print("LANGGRAPH_63_FINANCIAL_SQL_EXECUTED=false")
            return 0
        if not all((
            args.baseline, args.output_dir, args.shadow_container,
            args.principal_id, args.organization_id, args.expected_provider,
            args.expected_model, args.max_provider_calls,
        )):
            raise ValueError("live_arguments_missing")
        return _run(args, manifest, receipt, plan)
    except (OSError, ValueError, TypeError, KeyError, UnicodeError):
        print("LANGGRAPH_63=BLOCKED_INVALID_INPUT")
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
