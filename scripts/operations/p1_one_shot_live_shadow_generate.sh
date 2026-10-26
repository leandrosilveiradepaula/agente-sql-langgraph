#!/usr/bin/env bash
set -Eeuo pipefail
cd /docker/agente-sql-langgraph-repo

git fetch -q origin
git checkout -q main
git pull --ff-only -q origin main
printf 'P1_REPO_HEAD=%s\n' "$(git rev-parse --short HEAD)"

SHADOW_CONTAINER=agente-sql-langgraph-shadow-test-langgraph-shadow-test-1
STATUS="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$SHADOW_CONTAINER")"
printf 'P1_SHADOW_CONTAINER_STATUS=%s\n' "$STATUS"
[[ "$STATUS" == healthy ]] || { echo 'P1_ABORT=SHADOW_NOT_HEALTHY'; exit 2; }

# Inspects only public configuration; never prints secrets/DSNs.
docker exec -i -w /app "$SHADOW_CONTAINER" python - <<'PY'
import os
from app.test_runtime.config import load_shadow_test_runtime_config
c = load_shadow_test_runtime_config()
assert os.environ.get('LANGGRAPH_ALLOW_REAL_SQL_EXECUTION') == 'false'
assert c.allow_real_sql_execution is False
assert c.runtime_mode == 'shadow_test'
assert c.shadow_persistence == 'postgres'
assert c.expected_organization_id is None, 'tenant binding requires an authorized principal'
assert os.environ.get('GEMINI_API_KEY'), 'GEMINI_API_KEY missing'
print('P1_RUNTIME_SHADOW_SAFE=TRUE')
print('P1_RUNTIME_COMMIT=' + (c.langgraph_commit or 'UNSET'))
print('P1_SEMANTIC_VERSION=' + c.semantic_agent_version)
print('P1_GEMINI_MODEL=' + os.environ.get('GEMINI_SQL_GENERATOR_MODEL', 'gemini-2.5-flash'))
PY

# Read-only audit: blocks the test if the active n8n candidate has drifted.
bash scripts/n8n/audit_parallel_shadow_bindings_readonly.sh \
  --workflow-id LwUsMRWi34D2ARWu1YzgV --active-version-match

# This block sends exactly ONE webhook request. It never submits SQL for execution.
python3 - <<'PY'
import getpass, json, subprocess, sys, urllib.error, urllib.request, uuid
from datetime import datetime, timezone

CONTAINER = 'agente-sql-langgraph-shadow-test-langgraph-shadow-test-1'
URL = 'https://n8n.srv1319424.hstgr.cloud/webhook/langgraph-shadow-parallel-v1'
agent_id = 'p1-shadow-' + uuid.uuid4().hex
request_id = 'p1-' + uuid.uuid4().hex
secret = getpass.getpass('Token X-Agent-Shadow-Token do webhook n8n (sem eco): ')
if not secret.strip() or secret != secret.strip():
    raise SystemExit('P1_ABORT=WEBHOOK_TOKEN_MISSING_OR_INVALID')

# The candidate relay requires the BFF-shaped envelope. This operator-created
# test envelope does NOT demonstrate a real authenticated Product dispatch.
payload = {
    'contract_version': '1',
    'agent_run_id': agent_id,
    'question': 'Quanto foi a receita liquida realizada em setembro de 2025?',
    'principal': {'id': 'shadow-p1-operator-test', 'profile': 'runtime_validation'},
    'correlation_metadata': {
        'source': 'nextjs_bff',
        'event': 'generate',
        'route': '/api/generate-sql',
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'request_id': request_id,
    },
}
req = urllib.request.Request(
    URL,
    data=json.dumps(payload, ensure_ascii=False).encode('utf-8'),
    method='POST',
    headers={'Content-Type': 'application/json', 'Accept': 'application/json',
             'X-Agent-Shadow-Token': secret},
)
try:
    with urllib.request.urlopen(req, timeout=25) as response:
        code = response.status
        receipt = json.loads(response.read(8192).decode('utf-8'))
except urllib.error.HTTPError as exc:
    print('P1_N8N_HTTP=' + str(exc.code))
    raise SystemExit('P1_ABORT=WEBHOOK_REJECTED')
except Exception as exc:
    print('P1_TRANSPORT_ERROR=' + type(exc).__name__)
    raise SystemExit('P1_ABORT=WEBHOOK_TRANSPORT_FAILED')
finally:
    secret = None
if code != 202 or receipt.get('accepted') is not True or receipt.get('agent_run_id') != agent_id:
    print('P1_N8N_HTTP=' + str(code))
    raise SystemExit('P1_ABORT=INVALID_N8N_RECEIPT')
print('P1_N8N_RECEIPT=HTTP_202', flush=True)
print('P1_AGENT_RUN_ID=' + agent_id, flush=True)

# Run inside LangGraph's container so its existing S2S token never leaves it.
read_evidence = r'''
import json, os, sys, time, urllib.parse, urllib.request, urllib.error
from app.infrastructure.persistence.postgres_shadow_evidence_repository import PostgresShadowEvidenceRepository
from app.test_runtime.config import load_shadow_test_runtime_config

c = load_shadow_test_runtime_config()
if c.allow_real_sql_execution or os.environ.get('LANGGRAPH_ALLOW_REAL_SQL_EXECUTION') != 'false':
    print('P1_ABORT=SQL_EXECUTION_FLAG'); sys.exit(4)
agent_id = os.environ['P1_AGENT_RUN_ID']
root = 'http://127.0.0.1:' + str(c.http_port)
headers = {'Authorization': 'Bearer ' + c.s2s_token, 'Accept': 'application/json'}

def read(path):
    req = urllib.request.Request(root + path, headers=headers)
    with urllib.request.urlopen(req, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError('unexpected read status')
        return json.load(response)

item = None
for attempt in range(42):
    try:
        body = read('/v1/internal/agent-runs/' + urllib.parse.quote(agent_id)
                    + '/shadow-runs?limit=10')
        matches = [x for x in body.get('items', [])
                   if x.get('agent_run_id') == agent_id and x.get('event_type') == 'generate']
        if len(matches) == 1:
            item = matches[0]
            break
    except Exception:
        pass
    time.sleep(3)

if item is None:
    print('P1_EVIDENCE=NOT_FOUND_WITHIN_POLL_WINDOW')
    sys.exit(5)
record_id = item['shadow_record_id']
view = read('/v1/internal/shadow-runs/' + urllib.parse.quote(record_id))
repo = PostgresShadowEvidenceRepository(dsn=c.shadow_database_dsn,
                                        expected_organization_id=c.expected_organization_id)
result = repo.fetch_by_shadow_record_id(record_id)
if result.get('status') != 'ok':
    print('P1_RAW_EVIDENCE_READ=FAILED'); sys.exit(6)
record = result['record']
meta = record.get('langgraph_evidence', {}).get('provider_metadata', {})
provider = meta.get('sql_generation_result_provider_name', 'UNKNOWN')
model = meta.get('sql_generation_result_provider_model', 'UNKNOWN')
usage = meta.get('sql_generation_result_token_usage', {})
if not isinstance(usage, dict): usage = {}
usage = {k: v for k,v in usage.items() if isinstance(k, str) and
         isinstance(v, (int,float)) and not isinstance(v, bool) and
         0 <= v < 10000000}
sql_present = bool(record.get('generated_sql'))
print('P1_RUN_ID=' + item['run_id'])
print('P1_SHADOW_RECORD_ID=' + record_id)
print('P1_EVIDENCE_STATUS=' + str(view.get('status')))
print('P1_SQL_PRESENT=' + str(sql_present).upper())
print('P1_PROVIDER=' + str(provider))
print('P1_PROVIDER_MODEL=' + str(model))
print('P1_GENERATION_TOKEN_USAGE=' + json.dumps(usage, sort_keys=True))
print('P1_SQL_FINGERPRINT_PRESENT=' + str(bool(
    record.get('fingerprints', {}).get('langgraph_sql'))).upper())
print('P1_CONTEXT_VERSION=' + str(view.get('lineage', {}).get('context_version', 'UNKNOWN')))
print('P1_REPAIR_USED=' + str(bool(item.get('has_repair'))).upper())
for gate in ('security', 'contract', 'preflight'):
    print('P1_GATE_' + gate.upper() + '=' + str(view.get('gates', {}).get(gate, {}).get('status', 'UNKNOWN')))
errors = view.get('errors', [])
print('P1_ERROR_CODES=' + json.dumps([x.get('code') for x in errors if isinstance(x,dict)]))
passed = (view.get('status') == 'success' and sql_present and provider == 'google_gemini'
          and bool(record.get('fingerprints', {}).get('langgraph_sql')))
print('P1_GENERATION_PROOF=' + ('PASS' if passed else 'FAIL'))
print('P1_REAL_SQL_EXECUTION=FALSE')
if not passed: sys.exit(7)
'''
try:
    cmd = ['docker', 'exec', '-i', '-w', '/app', '-e', f'P1_AGENT_RUN_ID={agent_id}', CONTAINER, 'python', '-']
    subprocess.run(cmd, input=read_evidence, text=True, check=True, timeout=165)
except subprocess.CalledProcessError as exc:
    print('P1_EVIDENCE_EXIT=' + str(exc.returncode))
    sys.exit(exc.returncode)
except subprocess.TimeoutExpired:
    raise SystemExit('P1_EVIDENCE=TIMEOUT')
PY
