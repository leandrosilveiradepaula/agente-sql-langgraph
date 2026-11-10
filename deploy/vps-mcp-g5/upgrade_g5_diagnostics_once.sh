#!/usr/bin/env bash
# Upgrade ONLY the already installed G5 diagnostic module to reviewed PR #220.
# Does not need or modify the LangGraph checkout, n8n, databases, or tunnel.
set -Eeuo pipefail
umask 077

BASE=/opt/agente-financeiro-mcp
BROKER="$BASE/benchmark_ops.py"
OTHER="$BASE/operations_broker.py"
UNIT=/etc/systemd/system/agente-financeiro-mcp-ops.service
SOCKET=/run/agente-financeiro-mcp/operations.sock
BACKUP="$BASE/backup-before-g5-diagnostics"
OPS_SERVICE=agente-financeiro-mcp-ops.service
TUNNEL_SERVICE=agente-financeiro-mcp-tunnel.service
SOURCE_COMMIT=f3edfba09b687d088a2a4b35dcdc3a66f63bae54
OLD_BLOB=0d3fc77cd862780cd9008601d905d6d63122cd5f
NEW_BLOB=c8b18cdeeba39d101fe92457f69da5b1c5af231d
BROKER_BLOB=6f814a7bda5262dd85db0c4032dcee56d289ec9c
UNIT_BLOB=64fb7d4567952eccefa8b9b3ad74b392e12cdad2
RAW="https://raw.githubusercontent.com/leandrosilveiradepaula/agente-sql-langgraph/$SOURCE_COMMIT/deploy/vps-mcp-g5/benchmark_ops.py"

reject() { printf 'G5_DIAGNOSTIC_UPGRADE=BLOCKED\nREASON=%s\n' "$1"; exit 2; }
[[ "$(id -u)" == 0 ]] || reject ROOT_REQUIRED
for cmd in /usr/bin/git /usr/bin/curl /usr/bin/python3 /usr/bin/systemctl /usr/sbin/runuser; do
  [[ -x "$cmd" ]] || reject REQUIRED_EXECUTABLE_MISSING
done
[[ -d "$BASE" && ! -L "$BASE" ]] || reject PACKAGE_DIRECTORY_UNTRUSTED
for file in "$BROKER" "$OTHER" "$UNIT"; do
  [[ -f "$file" && ! -L "$file" ]] || reject PACKAGE_COMPONENT_UNTRUSTED
done
[[ "$(/usr/bin/git hash-object "$OTHER")" == "$BROKER_BLOB" ]] || reject BROKER_VERSION_UNEXPECTED
[[ "$(/usr/bin/git hash-object "$UNIT")" == "$UNIT_BLOB" ]] || reject SERVICE_VERSION_UNEXPECTED
/usr/bin/systemctl is-active --quiet "$OPS_SERVICE" || reject BROKER_SERVICE_NOT_ACTIVE
/usr/bin/systemctl is-active --quiet "$TUNNEL_SERVICE" || reject TUNNEL_SERVICE_NOT_ACTIVE
[[ -S "$SOCKET" ]] || reject BROKER_SOCKET_NOT_PRESENT

current="$(/usr/bin/git hash-object "$BROKER")"
if [[ "$current" == "$NEW_BLOB" ]]; then
  printf 'G5_DIAGNOSTIC_UPGRADE=ALREADY_CURRENT\n'
  exit 0
fi
[[ "$current" == "$OLD_BLOB" ]] || reject DIAGNOSTIC_VERSION_UNEXPECTED
[[ ! -e "$BACKUP" && ! -L "$BACKUP" ]] || reject DEDICATED_BACKUP_ALREADY_EXISTS

TMP="$(mktemp "$BASE/.benchmark-ops-upgrade.XXXXXXXX")"
rollback_armed=0
complete=0
cleanup() {
  result=$?
  if [[ "$rollback_armed" == 1 && "$complete" != 1 ]]; then
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/benchmark_ops.py" "$BROKER" || true
    /usr/bin/systemctl restart "$OPS_SERVICE" || true
    printf 'G5_DIAGNOSTIC_UPGRADE=ROLLED_BACK\n' >&2
  fi
  rm -f -- "$TMP"
  exit "$result"
}
trap cleanup EXIT

/usr/bin/curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 \
  --proto-redir '=https' --max-time 40 --output "$TMP" "$RAW" || reject APPROVED_SOURCE_FETCH_FAILED
[[ "$(/usr/bin/git hash-object "$TMP")" == "$NEW_BLOB" ]] || reject APPROVED_SOURCE_DIGEST_MISMATCH
/usr/bin/python3 -B -m py_compile "$TMP" || reject APPROVED_SOURCE_INVALID_PYTHON

/usr/bin/install -d -m 0700 -o root -g root "$BACKUP"
/usr/bin/install -m 0600 -o root -g root "$BROKER" "$BACKUP/benchmark_ops.py"
[[ "$(/usr/bin/git hash-object "$BACKUP/benchmark_ops.py")" == "$OLD_BLOB" ]] || reject BACKUP_VERIFICATION_FAILED

rollback_armed=1
/usr/bin/install -m 0644 -o root -g root "$TMP" "$BROKER"
/usr/bin/systemctl restart "$OPS_SERVICE"

# Verify the restarted broker from the actual MCP Unix socket as agente-mcp.
# Status messages are fixed/sanitized; neither secrets nor stdout of the
# underlying G5 CLI cross the broker boundary.
ready=0
for attempt in $(seq 1 30); do
  if [[ -S "$SOCKET" ]] && /usr/sbin/runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY' >/dev/null 2>&1
import json
import socket

path = "/run/agente-financeiro-mcp/operations.sock"
for op in ("benchmark_plan", "benchmark_status"):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        # The plan verifies a potentially large encrypted archive digest.
        # A tiny socket timeout would create overlapping probes.
        sock.settimeout(85 if op == "benchmark_plan" else 12)
        sock.connect(path)
        sock.sendall(json.dumps({"op": op}).encode("ascii") + b"\n")
        payload = bytearray()
        while not payload.endswith(b"\n") and len(payload) < 16384:
            chunk = sock.recv(8192)
            if not chunk:
                break
            payload.extend(chunk)
    data = json.loads(payload)
    assert data["status"] in (
        ("pass", "blocked") if op == "benchmark_plan" else
        ("pass", "blocked", "not_recovered")
    )
    assert data.get("reason") != "command_failed"
PY
  then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == 1 ]] || reject BROKER_RESTART_OR_PROBE_FAILED
/usr/bin/systemctl is-active --quiet "$TUNNEL_SERVICE" || reject TUNNEL_NOT_ACTIVE
[[ "$(/usr/bin/git hash-object "$BROKER")" == "$NEW_BLOB" ]] || reject INSTALL_DIGEST_MISMATCH
complete=1
printf 'G5_DIAGNOSTIC_UPGRADE=PASS\n'
printf 'BROKER_RESTART=PASS\nTUNNEL_PRESERVED=PASS\n'
printf 'LANGGRAPH_CHECKOUT_UNTOUCHED=true\nN8N_UNTOUCHED=true\nFINANCIAL_SQL_EXECUTED=false\n'
