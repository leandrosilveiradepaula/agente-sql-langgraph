#!/usr/bin/env bash
# Upgrade ONLY the reviewed fixed-read-only CIA J1 capabilities of the
# existing financial MCP gateway. No CIA collector/timer/SQLite modifications.
# Runs on VPS as root after the separate operational access gate.
set -Eeuo pipefail
umask 077

BASE=/opt/agente-financeiro-mcp
MCP="$BASE/mcp_server.py"
BROKER="$BASE/operations_broker.py"
CIA="$BASE/crypto_j1_readonly.py"
BENCHMARK="$BASE/benchmark_ops.py"
UNIT=/etc/systemd/system/agente-financeiro-mcp-ops.service
SOCKET=/run/agente-financeiro-mcp/operations.sock
BACKUP="$BASE/backup-before-cia-j1-readonly"
OPS_SERVICE=agente-financeiro-mcp-ops.service
TUNNEL_SERVICE=agente-financeiro-mcp-tunnel.service

# Immutable source from merged PR #222 + #221; NEVER use mutable main.
SOURCE_COMMIT=26b9b8fa9b3f5a027fb82199c8bc77dc7f83734e
SOURCE="https://raw.githubusercontent.com/leandrosilveiradepaula/agente-sql-langgraph/$SOURCE_COMMIT/deploy/vps-mcp-g5"
OLD_MCP=050f1fb4771265cd394c9b2797d570d7eb0d6b30
OLD_BROKER=6f814a7bda5262dd85db0c4032dcee56d289ec9c
NEW_MCP=334d9c22bcf7b160867ab0755ad3f898f361ea25
NEW_BROKER=08566865997db33e888b4a474fa1fd129c9e5073
NEW_CIA=19b2f724419acf5cbb6c6d923633376493aa023a
ORIGINAL_G5=0d3fc77cd862780cd9008601d905d6d63122cd5f
UPDATED_G5=c8b18cdeeba39d101fe92457f69da5b1c5af231d
UNIT_BLOB=64fb7d4567952eccefa8b9b3ad74b392e12cdad2

reject() { printf 'CIA_J1_MCP_UPGRADE=BLOCKED\nREASON=%s\n' "$1"; exit 2; }
[[ $(id -u) == 0 ]] || reject ROOT_REQUIRED
for cmd in /usr/bin/git /usr/bin/curl /usr/bin/python3 /usr/bin/systemctl /usr/sbin/runuser; do
  [[ -x "$cmd" ]] || reject REQUIRED_EXECUTABLE_MISSING
done
[[ -d "$BASE" && ! -L "$BASE" ]] || reject PACKAGE_DIRECTORY_UNTRUSTED
for file in "$MCP" "$BROKER" "$BENCHMARK" "$UNIT"; do
  [[ -f "$file" && ! -L "$file" ]] || reject PACKAGE_COMPONENT_UNTRUSTED
done
[[ "$(/usr/bin/git hash-object "$UNIT")" == "$UNIT_BLOB" ]] || reject SERVICE_VERSION_UNEXPECTED
bench_blob="$(/usr/bin/git hash-object "$BENCHMARK")"
[[ "$bench_blob" == "$ORIGINAL_G5" || "$bench_blob" == "$UPDATED_G5" ]] || reject FINANCIAL_MODULE_DRIFT
/usr/bin/systemctl is-active --quiet "$OPS_SERVICE" || reject BROKER_SERVICE_NOT_ACTIVE
/usr/bin/systemctl is-active --quiet "$TUNNEL_SERVICE" || reject TUNNEL_SERVICE_NOT_ACTIVE
[[ -S "$SOCKET" ]] || reject BROKER_SOCKET_NOT_PRESENT

actual_mcp="$(/usr/bin/git hash-object "$MCP")"
actual_broker="$(/usr/bin/git hash-object "$BROKER")"
if [[ "$actual_mcp" == "$NEW_MCP" && "$actual_broker" == "$NEW_BROKER" ]]; then
  [[ -f "$CIA" && ! -L "$CIA" ]] || reject CIA_MODULE_MISSING
  [[ "$(/usr/bin/git hash-object "$CIA")" == "$NEW_CIA" ]] || reject CIA_MODULE_DRIFT
  printf 'CIA_J1_MCP_UPGRADE=ALREADY_CURRENT\n'
  exit 0
fi
[[ "$actual_mcp" == "$OLD_MCP" && "$actual_broker" == "$OLD_BROKER" ]] || reject GATEWAY_VERSION_UNEXPECTED
[[ ! -e "$CIA" && ! -L "$CIA" ]] || reject CIA_MODULE_PREEXISTS
[[ ! -e "$BACKUP" && ! -L "$BACKUP" ]] || reject BACKUP_ALREADY_EXISTS

# Stage three immutable blobs; no changes to active services on fetch failure.
TMP="$(mktemp -d "$BASE/.cia-j1-mcp-stage.XXXXXXXX")"
rollback_armed=0
complete=0
cleanup() {
  rc=$?
  trap - EXIT
  if [[ "$rollback_armed" == 1 && "$complete" != 1 ]]; then
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/mcp_server.py" "$MCP" || true
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/operations_broker.py" "$BROKER" || true
    /usr/bin/rm -f -- "$CIA" || true
    /usr/bin/systemctl restart "$OPS_SERVICE" || true
    /usr/bin/systemctl restart "$TUNNEL_SERVICE" || true
    printf 'CIA_J1_MCP_UPGRADE=ROLLED_BACK\n' >&2
  fi
  /usr/bin/rm -rf -- "$TMP"
  exit "$rc"
}
trap cleanup EXIT

for row in "mcp_server.py:$NEW_MCP" "operations_broker.py:$NEW_BROKER" "crypto_j1_readonly.py:$NEW_CIA"; do
  name="${row%%:*}"
  expected="${row#*:}"
  /usr/bin/curl --fail --location --silent --show-error --proto '=https' --tlsv1.2 \
    --proto-redir '=https' --max-time 40 --output "$TMP/$name" "$SOURCE/$name" \
    || reject APPROVED_SOURCE_FETCH_FAILED
  [[ "$(/usr/bin/git hash-object "$TMP/$name")" == "$expected" ]] \
    || reject APPROVED_SOURCE_DIGEST_MISMATCH
done
/usr/bin/python3 -B -m py_compile "$TMP/"*.py || reject APPROVED_SOURCE_INVALID_PYTHON

/usr/bin/install -d -m 0700 -o root -g root "$BACKUP"
/usr/bin/install -m 0600 -o root -g root "$MCP" "$BACKUP/mcp_server.py"
/usr/bin/install -m 0600 -o root -g root "$BROKER" "$BACKUP/operations_broker.py"
[[ "$(/usr/bin/git hash-object "$BACKUP/mcp_server.py")" == "$OLD_MCP" ]] || reject BACKUP_VERIFICATION_FAILED
[[ "$(/usr/bin/git hash-object "$BACKUP/operations_broker.py")" == "$OLD_BROKER" ]] || reject BACKUP_VERIFICATION_FAILED

rollback_armed=1
for name in mcp_server.py operations_broker.py crypto_j1_readonly.py; do
  /usr/bin/install -m 0644 -o root -g root "$TMP/$name" "$BASE/$name"
done

/usr/bin/systemctl restart "$OPS_SERVICE"
ready=0
for attempt in $(seq 1 30); do
  if [[ -S "$SOCKET" ]] && /usr/sbin/runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY' >/dev/null 2>&1
import json, socket
path = "/run/agente-financeiro-mcp/operations.sock"
for op in ("cia_timer", "cia_journal", "cia_sqlite", "benchmark_status"):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(30)
        s.connect(path)
        s.sendall((json.dumps({"op": op}) + "\n").encode("ascii"))
        data = bytearray()
        while b"\n" not in data and len(data) < 16384:
            block = s.recv(4096)
            if not block:
                break
            data.extend(block)
    result = json.loads(bytes(data).split(b"\n", 1)[0])
    assert isinstance(result, dict)
    assert result.get("status") in (
        ("pass", "incomplete", "blocked", "ok") if op != "benchmark_status"
        else ("pass", "blocked", "not_recovered")
    )
    if op.startswith("cia_"):
        assert result.get("trading_enabled") is False
        assert result.get("marketwide_top50_verified") is False
PY
  then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]] || reject BROKER_RESTART_OR_PROBE_FAILED

/usr/bin/systemctl restart "$TUNNEL_SERVICE"
ready=0
for attempt in $(seq 1 20); do
  if /usr/bin/systemctl is-active --quiet "$TUNNEL_SERVICE" &&
     /usr/bin/curl --fail --silent --show-error --max-time 2 http://127.0.0.1:8080/readyz >/dev/null 2>&1; then
    ready=1
    break
  fi
  sleep 1
done
[[ "$ready" == 1 ]] || reject TUNNEL_NOT_READY
[[ "$(/usr/bin/git hash-object "$MCP")" == "$NEW_MCP" ]] || reject INSTALL_DIGEST_MISMATCH
[[ "$(/usr/bin/git hash-object "$BROKER")" == "$NEW_BROKER" ]] || reject INSTALL_DIGEST_MISMATCH
[[ "$(/usr/bin/git hash-object "$CIA")" == "$NEW_CIA" ]] || reject INSTALL_DIGEST_MISMATCH
[[ "$(/usr/bin/git hash-object "$BENCHMARK")" == "$bench_blob" ]] || reject FINANCIAL_MODULE_CHANGED

complete=1
printf 'CIA_J1_MCP_UPGRADE=PASS\n'
printf 'BROKER_AND_TUNNEL=PASS\n'
printf 'FINANCIAL_MODULE_UNCHANGED=true\n'
printf 'CIA_COLLECTOR_AND_SQLITE_UNCHANGED=true\n'
printf 'FINANCIAL_SQL_EXECUTED=false\n'
printf 'NEXT=REFRESH_CHATGPT_PLUGIN_TOOLS\n'
