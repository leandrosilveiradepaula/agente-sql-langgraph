#!/usr/bin/env bash
# CIA/J1 #557: root-controlled OFF-by-default, rollback-safe MCP auditor update.
# This script is NOT run by CI or by the CIA collector. A production release
# still requires independent operator authorization and preflight validation.
# It replaces ONLY the read-only Python auditor; never the broker, finance
# module, socket, systemd unit, collector, database or any trading code.
set -Eeuo pipefail
umask 077

BASE=/opt/agente-financeiro-mcp
AUDIT="$BASE/crypto_j1_readonly.py"
BROKER="$BASE/operations_broker.py"
MCP="$BASE/mcp_server.py"
FINANCE="$BASE/benchmark_ops.py"
SIDECAR="$BASE/cia_j1_sqlite_owner_sidecar.py"
OWNER_UNIT=/etc/systemd/system/cia-j1-owner-sqlite.service
SOCKET_UNIT=/etc/systemd/system/cia-j1-owner-sqlite.socket
OWNER_SOCKET=/run/cia-j1-owner/readonly.sock
BROKER_SOCKET=/run/agente-financeiro-mcp/operations.sock
OWNER_SERVICE=cia-j1-owner-sqlite.service
OWNER_SOCKET_UNIT=cia-j1-owner-sqlite.socket
OPS_SERVICE=agente-financeiro-mcp-ops.service
TUNNEL_SERVICE=agente-financeiro-mcp-tunnel.service
BACKUP="$BASE/backup-before-cia-j1-recurring-auditor-d284"

# Independently checked actual 12/11/2026 VPS file identities.
OLD_AUDIT=e876c2ae46d1164b05b76b323a527f2a31dcceea
NEW_AUDIT=c01c55e381ce444eacb31be70eb5613326b09d21
BROKER_BLOB=1699b553d174b90f208fc9878ebb3d157ed13312
MCP_BLOB=52c03b32367985593e3207f0131cd48165bb58e7
FINANCE_BLOB=c8b18cdeeba39d101fe92457f69da5b1c5af231d
SIDECAR_BLOB=499c396c6936c6c63c5551c4d4e7956a198d3c45
OWNER_UNIT_BLOB=ee67803955d03692404d5e0cbe81baf0d47c52a9
SOCKET_UNIT_BLOB=ba4ecc763f932d868c0772bb679ab55270008374

# Fixed, immutable main commit whose auditor blob is the tested D284 source.
SOURCE_COMMIT=955eda46015d35dbe44a40f9240b821b1f493201
SOURCE="https://raw.githubusercontent.com/leandrosilveiradepaula/agente-sql-langgraph/$SOURCE_COMMIT/deploy/vps-mcp-g5/crypto_j1_readonly.py"

reject() { printf 'CIA_J1_RECURRENT_AUDIT_RELEASE=BLOCKED\nREASON=%s\n' "$1" >&2; exit 2; }

test "$(id -u)" = 0 || reject ROOT_REQUIRED
test "$(hostname)" = srv1319424 || reject HOST_MISMATCH
for cmd in /usr/bin/git /usr/bin/curl /usr/bin/python3 /usr/bin/systemctl /usr/bin/install /usr/sbin/runuser /usr/bin/mktemp /usr/bin/rm; do
  test -x "$cmd" || reject DEPENDENCY_UNAVAILABLE
done
test -d "$BASE" && test ! -L "$BASE" || reject INSTALL_DIRECTORY_UNTRUSTED
for path in "$AUDIT" "$BROKER" "$MCP" "$FINANCE" "$SIDECAR" "$OWNER_UNIT" "$SOCKET_UNIT"; do
  test -f "$path" && test ! -L "$path" || reject INSTALLED_COMPONENT_UNTRUSTED
done

hash_is() { test "$(/usr/bin/git hash-object "$1")" = "$2"; }
hash_is "$BROKER" "$BROKER_BLOB" || reject BROKER_DRIFT
hash_is "$MCP" "$MCP_BLOB" || reject GATEWAY_DRIFT
hash_is "$FINANCE" "$FINANCE_BLOB" || reject FINANCIAL_MODULE_DRIFT
hash_is "$SIDECAR" "$SIDECAR_BLOB" || reject OWNER_SIDECAR_DRIFT
hash_is "$OWNER_UNIT" "$OWNER_UNIT_BLOB" || reject OWNER_UNIT_DRIFT
hash_is "$SOCKET_UNIT" "$SOCKET_UNIT_BLOB" || reject OWNER_SOCKET_UNIT_DRIFT

for unit in "$OWNER_SERVICE" "$OWNER_SOCKET_UNIT" "$OPS_SERVICE" "$TUNNEL_SERVICE"; do
  /usr/bin/systemctl is-active --quiet "$unit" || reject EXISTING_SERVICE_UNHEALTHY
done
test -S "$OWNER_SOCKET" && test -S "$BROKER_SOCKET" || reject SOCKET_UNAVAILABLE

# Unambiguous modes: safe read-only inspection by default; --apply requires
# both separate affirmative arguments. No environment variable shortcuts.
if test "$#" -eq 0 || { test "$#" -eq 1 && test "$1" = "--preflight"; }; then
  if hash_is "$AUDIT" "$NEW_AUDIT"; then
    printf 'CIA_J1_RECURRENT_AUDIT_PREFLIGHT=ALREADY_INSTALLED\n'
    exit 0
  fi
  hash_is "$AUDIT" "$OLD_AUDIT" || reject OLD_AUDITOR_VERSION_UNEXPECTED
  test ! -e "$BACKUP" && test ! -L "$BACKUP" || reject BACKUP_PATH_ALREADY_PRESENT
  printf 'CIA_J1_RECURRENT_AUDIT_PREFLIGHT=PASS\n'
  printf 'MODIFICATIONS=none\n'
  printf 'RELEASE_AUTHORIZATION_REQUIRED=true\n'
  exit 0
fi

test "$#" -eq 2 || reject EXPLICIT_RELEASE_FLAGS_REQUIRED
test "$1" = "--confirm-owner-auditor-release" || reject EXPLICIT_RELEASE_FLAGS_REQUIRED
test "$2" = "--allow-service-restarts" || reject EXPLICIT_RELEASE_FLAGS_REQUIRED

# Idempotence is restricted to the exact single approved module version.
if hash_is "$AUDIT" "$NEW_AUDIT"; then
  printf 'CIA_J1_RECURRENT_AUDIT_RELEASE=ALREADY_INSTALLED\n'
  exit 0
fi
hash_is "$AUDIT" "$OLD_AUDIT" || reject OLD_AUDITOR_VERSION_UNEXPECTED
test ! -e "$BACKUP" && test ! -L "$BACKUP" || reject BACKUP_PATH_ALREADY_PRESENT

TMP="$(/usr/bin/mktemp -d "$BASE/.j1-auditor-stage.XXXXXXXX")"
changed=0
completed=0
cleanup() {
  code=$?
  trap - EXIT
  if test "$changed" = 1 && test "$completed" != 1; then
    /usr/bin/install -o root -g root -m 0644 "$BACKUP/crypto_j1_readonly.py" "$AUDIT" || true
    /usr/bin/systemctl restart "$OWNER_SERVICE" || true
    /usr/bin/systemctl restart "$OPS_SERVICE" || true
    printf 'CIA_J1_RECURRENT_AUDIT_RELEASE=ROLLED_BACK\n' >&2
  fi
  /usr/bin/rm -rf -- "$TMP"
  exit "$code"
}
trap cleanup EXIT

# No branch tip or mutable URL. No downloaded code can run before SHA check.
/usr/bin/curl --fail --location --silent --show-error \
  --proto '=https' --proto-redir '=https' --tlsv1.2 --max-time 40 \
  --output "$TMP/crypto_j1_readonly.py" "$SOURCE" || reject PINNED_SOURCE_FETCH_FAILED
hash_is "$TMP/crypto_j1_readonly.py" "$NEW_AUDIT" || reject PINNED_AUDITOR_HASH_MISMATCH
/usr/bin/python3 -B -m py_compile "$TMP/crypto_j1_readonly.py" || reject PYTHON_SYNTAX_INVALID

/usr/bin/install -d -o root -g root -m 0700 "$BACKUP"
/usr/bin/install -o root -g root -m 0600 "$AUDIT" "$BACKUP/crypto_j1_readonly.py"
hash_is "$BACKUP/crypto_j1_readonly.py" "$OLD_AUDIT" || reject BACKUP_MISMATCH
changed=1
/usr/bin/install -o root -g root -m 0644 "$TMP/crypto_j1_readonly.py" "$AUDIT"
hash_is "$AUDIT" "$NEW_AUDIT" || reject AUDITOR_INSTALL_MISMATCH

# Reload only the two readers of the replaced Python module. Never restart
# the financial tunnel, any J1 collector or the socket-activation unit.
/usr/bin/systemctl restart "$OWNER_SERVICE"
/usr/bin/systemctl restart "$OPS_SERVICE"
/usr/bin/systemctl is-active --quiet "$OWNER_SERVICE" || reject OWNER_SERVICE_FAILED
/usr/bin/systemctl is-active --quiet "$OWNER_SOCKET_UNIT" || reject OWNER_SOCKET_FAILED
/usr/bin/systemctl is-active --quiet "$OPS_SERVICE" || reject BROKER_FAILED
/usr/bin/systemctl is-active --quiet "$TUNNEL_SERVICE" || reject FINANCIAL_TUNNEL_FAILED

# Peer UID0 -> owner-only sidecar: bounded response, no prices or raw symbols.
/usr/bin/python3 -B - <<'PY' || reject OWNER_RECURRENCE_AUDIT_FAILED
import json
import socket

with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
    sock.settimeout(15)
    sock.connect("/run/cia-j1-owner/readonly.sock")
    sock.sendall(b'{"op":"cia_sqlite"}\n')
    chunks = bytearray()
    while b"\\n" not in chunks and len(chunks) < 4096:
        part = sock.recv(min(1024, 4096 - len(chunks)))
        if not part:
            break
        chunks.extend(part)
raw = bytes(chunks).split(b"\\n", 1)[0]
report = json.loads(raw)
expected = {
    "status", "contracts", "stored_candles", "published_checkpoints",
    "last_published_end_ms", "sqlite_integrity", "contiguous_candles",
    "digest_replay", "halted", "trading_enabled", "marketwide_top50_verified",
}
assert set(report) == expected
assert report["status"] == "pass"
assert report["contracts"] == 2
assert type(report["stored_candles"]) is int and report["stored_candles"] >= 100
assert type(report["published_checkpoints"]) is int and report["published_checkpoints"] >= 26
assert all(report[k] is True for k in ("sqlite_integrity", "contiguous_candles", "digest_replay"))
assert all(report[k] is False for k in ("halted", "trading_enabled", "marketwide_top50_verified"))
PY

# The broker requires the existing agente-mcp UID. No access expansion.
/usr/sbin/runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY' || reject BROKER_RECURRENCE_AUDIT_FAILED
import json
import socket

def call(op):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
        sock.settimeout(15)
        sock.connect("/run/agente-financeiro-mcp/operations.sock")
        sock.sendall((json.dumps({"op": op}) + "\n").encode("ascii"))
        chunks = bytearray()
        while b"\n" not in chunks and len(chunks) < 4096:
            part = sock.recv(1024)
            if not part:
                break
            chunks.extend(part)
        return json.loads(bytes(chunks).split(b"\n", 1)[0])

sql = call("cia_sqlite")
assert sql["status"] == "pass"
assert sql["contracts"] == 2 and sql["stored_candles"] >= 100
assert sql["published_checkpoints"] >= 26
assert sql["trading_enabled"] is False
assert sql["marketwide_top50_verified"] is False
journal = call("cia_journal")
assert journal.get("status") == "pass"
assert journal.get("trading_enabled") is False
finance = call("benchmark_status")
assert isinstance(finance, dict)
PY

# Verify no unrelated source/unit changes, and leave the existing backup.
hash_is "$BROKER" "$BROKER_BLOB" || reject BROKER_CHANGED
hash_is "$MCP" "$MCP_BLOB" || reject GATEWAY_CHANGED
hash_is "$FINANCE" "$FINANCE_BLOB" || reject FINANCIAL_CHANGED
hash_is "$SIDECAR" "$SIDECAR_BLOB" || reject OWNER_SIDECAR_CHANGED
hash_is "$OWNER_UNIT" "$OWNER_UNIT_BLOB" || reject OWNER_UNIT_CHANGED
hash_is "$SOCKET_UNIT" "$SOCKET_UNIT_BLOB" || reject OWNER_SOCKET_UNIT_CHANGED
hash_is "$AUDIT" "$NEW_AUDIT" || reject AUDITOR_CHANGED
completed=1
printf 'CIA_J1_RECURRENT_AUDIT_RELEASE=PASS\n'
printf 'RECURRENT_OWNER_SQLITE_AUDIT=PASS\n'
printf 'CIA_COLLECTOR_AND_TRADING_UNCHANGED=true\n'
printf 'FINANCIAL_MODULE_AND_TUNNEL_UNCHANGED=true\n'
