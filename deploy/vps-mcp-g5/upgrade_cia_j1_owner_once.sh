#!/usr/bin/env bash
# One-shot CIA owner-sidecar rollout, root only, approved code SHA and root-only
# rollback. Requires the previously deployed read-only CIA gateway. Never
# changes the financial benchmark module, CIA collector, DB or timer.
set -Eeuo pipefail
umask 077

BASE=/opt/agente-financeiro-mcp
BROKER="$BASE/operations_broker.py"
AUDIT="$BASE/crypto_j1_readonly.py"
SIDECAR="$BASE/cia_j1_sqlite_owner_sidecar.py"
UNIT=/etc/systemd/system/cia-j1-owner-sqlite.service
SOCKET_UNIT=/etc/systemd/system/cia-j1-owner-sqlite.socket
GATEWAY="$BASE/mcp_server.py"
FINANCE="$BASE/benchmark_ops.py"
ORIG_UNIT=/etc/systemd/system/agente-financeiro-mcp-ops.service
BACKUP="$BASE/backup-before-cia-j1-owner"
SOCKET=/run/cia-j1-owner/readonly.sock
BROKER_SOCKET=/run/agente-financeiro-mcp/operations.sock

SOURCE_COMMIT=a1ef5778e125fd749fbacf235a648a7b22bbea9f
SOURCE="https://raw.githubusercontent.com/leandrosilveiradepaula/agente-sql-langgraph/$SOURCE_COMMIT/deploy/vps-mcp-g5"
OLD_BROKER=08566865997db33e888b4a474fa1fd129c9e5073
OLD_AUDIT=19b2f724419acf5cbb6c6d923633376493aa023a
NEW_BROKER=65f966f4eb947fca91b7cf3f23f9541347dab632
NEW_AUDIT=e876c2ae46d1164b05b76b323a527f2a31dcceea
NEW_SIDECAR=499c396c6936c6c63c5551c4d4e7956a198d3c45
NEW_UNIT=ee67803955d03692404d5e0cbe81baf0d47c52a9
NEW_SOCKET_UNIT=ba4ecc763f932d868c0772bb679ab55270008374
GATEWAY_BLOB=334d9c22bcf7b160867ab0755ad3f898f361ea25
FINANCE_BLOB=c8b18cdeeba39d101fe92457f69da5b1c5af231d
ORIG_UNIT_BLOB=64fb7d4567952eccefa8b9b3ad74b392e12cdad2

reject() { printf 'CIA_J1_OWNER_UPGRADE=BLOCKED\nREASON=%s\n' "$1" >&2; exit 2; }
test "$(id -u)" -eq 0 || reject ROOT_REQUIRED
test "$(hostname)" = srv1319424 || reject HOST_MISMATCH
for cmd in /usr/bin/git /usr/bin/curl /usr/bin/python3 /usr/bin/systemctl /usr/bin/install /usr/sbin/runuser; do
  test -x "$cmd" || reject DEPENDENCY_MISSING
done
test -d "$BASE" && test ! -L "$BASE" || reject INSTALL_DIR_UNTRUSTED
for path in "$BROKER" "$AUDIT" "$GATEWAY" "$FINANCE" "$ORIG_UNIT"; do
  test -f "$path" && test ! -L "$path" || reject CURRENT_COMPONENT_UNTRUSTED
done
test "$(/usr/bin/git hash-object "$GATEWAY")" = "$GATEWAY_BLOB" || reject MCP_DRIFT
test "$(/usr/bin/git hash-object "$FINANCE")" = "$FINANCE_BLOB" || reject FINANCIAL_DRIFT
test "$(/usr/bin/git hash-object "$ORIG_UNIT")" = "$ORIG_UNIT_BLOB" || reject FINANCIAL_UNIT_DRIFT
/usr/bin/systemctl is-active --quiet agente-financeiro-mcp-ops.service || reject BROKER_NOT_ACTIVE
/usr/bin/systemctl is-active --quiet agente-financeiro-mcp-tunnel.service || reject TUNNEL_NOT_ACTIVE
test -S "$BROKER_SOCKET" || reject BROKER_SOCKET_MISSING

if test "$(/usr/bin/git hash-object "$BROKER")" = "$NEW_BROKER" &&
   test "$(/usr/bin/git hash-object "$AUDIT")" = "$NEW_AUDIT" &&
   test -f "$SIDECAR" && test "$(/usr/bin/git hash-object "$SIDECAR")" = "$NEW_SIDECAR" &&
   test -f "$UNIT" && test "$(/usr/bin/git hash-object "$UNIT")" = "$NEW_UNIT" &&
   test -f "$SOCKET_UNIT" && test "$(/usr/bin/git hash-object "$SOCKET_UNIT")" = "$NEW_SOCKET_UNIT" &&
   /usr/bin/systemctl is-active --quiet cia-j1-owner-sqlite.socket &&
   /usr/bin/systemctl is-active --quiet cia-j1-owner-sqlite.service; then
  printf 'CIA_J1_OWNER_UPGRADE=ALREADY_CURRENT\n'
  exit 0
fi

test "$(/usr/bin/git hash-object "$BROKER")" = "$OLD_BROKER" || reject BROKER_VERSION_UNEXPECTED
test "$(/usr/bin/git hash-object "$AUDIT")" = "$OLD_AUDIT" || reject AUDIT_VERSION_UNEXPECTED
for path in "$SIDECAR" "$UNIT" "$SOCKET_UNIT" "$BACKUP"; do
  test ! -e "$path" && test ! -L "$path" || reject OWNER_COMPONENT_ALREADY_PRESENT
done
test ! -e "$SOCKET" || reject OWNER_SOCKET_ALREADY_PRESENT
test ! -L "$SOCKET" || reject OWNER_SOCKET_UNTRUSTED

TMP="$(mktemp -d "$BASE/.cia-owner-stage.XXXXXXXX")"
changed=0
done_ok=0
cleanup() {
  rc=$?
  trap - EXIT
  if test "$changed" = 1 && test "$done_ok" != 1; then
    /usr/bin/systemctl stop cia-j1-owner-sqlite.service >/dev/null 2>&1 || true
    /usr/bin/systemctl disable --now cia-j1-owner-sqlite.socket >/dev/null 2>&1 || true
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/operations_broker.py" "$BROKER" || true
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/crypto_j1_readonly.py" "$AUDIT" || true
    /usr/bin/rm -f -- "$SIDECAR" "$UNIT" "$SOCKET_UNIT" || true
    /usr/bin/systemctl daemon-reload || true
    /usr/bin/systemctl restart agente-financeiro-mcp-ops.service || true
    printf 'CIA_J1_OWNER_UPGRADE=ROLLED_BACK\n' >&2
  fi
  /usr/bin/rm -rf -- "$TMP"
  exit "$rc"
}
trap cleanup EXIT

for entry in \
  "operations_broker.py:$NEW_BROKER" \
  "crypto_j1_readonly.py:$NEW_AUDIT" \
  "cia_j1_sqlite_owner_sidecar.py:$NEW_SIDECAR" \
  "cia-j1-owner-sqlite.service:$NEW_UNIT" \
  "cia-j1-owner-sqlite.socket:$NEW_SOCKET_UNIT"; do
  name="${entry%%:*}"
  expected="${entry#*:}"
  /usr/bin/curl --fail --location --silent --show-error \
    --proto '=https' --proto-redir '=https' --tlsv1.2 --max-time 40 \
    --output "$TMP/$name" "$SOURCE/$name" || reject PINNED_SOURCE_FETCH_FAILED
  test "$(/usr/bin/git hash-object "$TMP/$name")" = "$expected" || reject PINNED_BLOB_MISMATCH
done
/usr/bin/python3 -B -m py_compile "$TMP/"*.py || reject PYTHON_SYNTAX_FAILED

/usr/bin/install -d -m 0700 -o root -g root "$BACKUP"
/usr/bin/install -m 0600 -o root -g root "$BROKER" "$BACKUP/operations_broker.py"
/usr/bin/install -m 0600 -o root -g root "$AUDIT" "$BACKUP/crypto_j1_readonly.py"
test "$(/usr/bin/git hash-object "$BACKUP/operations_broker.py")" = "$OLD_BROKER" || reject BACKUP_BROKER_MISMATCH
test "$(/usr/bin/git hash-object "$BACKUP/crypto_j1_readonly.py")" = "$OLD_AUDIT" || reject BACKUP_AUDIT_MISMATCH

changed=1
/usr/bin/install -m 0644 -o root -g root "$TMP/operations_broker.py" "$BROKER"
/usr/bin/install -m 0644 -o root -g root "$TMP/crypto_j1_readonly.py" "$AUDIT"
/usr/bin/install -m 0644 -o root -g root "$TMP/cia_j1_sqlite_owner_sidecar.py" "$SIDECAR"
/usr/bin/install -m 0644 -o root -g root "$TMP/cia-j1-owner-sqlite.service" "$UNIT"
/usr/bin/install -m 0644 -o root -g root "$TMP/cia-j1-owner-sqlite.socket" "$SOCKET_UNIT"
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl start cia-j1-owner-sqlite.socket

# The owner service must work independently BEFORE replacing the root broker.
owner_ok=0
for attempt in $(seq 1 30); do
  if test -S "$SOCKET" &&
     /usr/bin/python3 -B - <<'PY' >/dev/null 2>&1
import json,socket
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as s:
    s.settimeout(10)
    s.connect("/run/cia-j1-owner/readonly.sock")
    s.sendall(b'{"op":"cia_sqlite"}\n')
    result=json.loads(s.recv(4096))
assert result.get("status") == "pass"
assert result.get("contracts") == 2
assert result.get("stored_candles") == 100
assert result.get("published_checkpoints") == 26
assert result.get("trading_enabled") is False
assert result.get("marketwide_top50_verified") is False
PY
  then owner_ok=1; break; fi
  sleep 1
done
test "$owner_ok" = 1 || reject OWNER_SQLITE_READ_ONLY_AUDIT_FAILED

/usr/bin/systemctl restart agente-financeiro-mcp-ops.service
broker_ok=0
for attempt in $(seq 1 30); do
  if test -S "$BROKER_SOCKET" &&
     /usr/sbin/runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY' >/dev/null 2>&1
import json,socket
path="/run/agente-financeiro-mcp/operations.sock"
for op in ("cia_timer","cia_journal","cia_sqlite","benchmark_status"):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as sock:
        sock.settimeout(30)
        sock.connect(path)
        sock.sendall((json.dumps({"op":op})+"\n").encode("ascii"))
        parts=bytearray()
        while b"\n" not in parts and len(parts)<4096:
            chunk=sock.recv(1024)
            if not chunk:
                break
            parts.extend(chunk)
        result=json.loads(bytes(parts).split(b"\n",1)[0])
        if op=="cia_timer":
            assert result.get("status")=="ok"
        if op in ("cia_journal","cia_sqlite"):
            assert result.get("status")=="pass"
            assert result.get("trading_enabled") is False
            assert result.get("marketwide_top50_verified") is False
        if op=="benchmark_status":
            assert isinstance(result,dict)
PY
  then broker_ok=1; break; fi
  sleep 1
done
test "$broker_ok" = 1 || reject BROKER_PROBE_FAILED
/usr/bin/systemctl is-active --quiet agente-financeiro-mcp-tunnel.service || reject TUNNEL_HEALTH_FAILED
/usr/bin/systemctl is-active --quiet cia-j1-owner-sqlite.service || reject OWNER_SERVICE_NOT_ACTIVE
/usr/bin/systemctl is-active --quiet cia-j1-owner-sqlite.socket || reject OWNER_SOCKET_NOT_ACTIVE
test "$(/usr/bin/git hash-object "$FINANCE")" = "$FINANCE_BLOB" || reject FINANCE_CHANGED
test "$(/usr/bin/git hash-object "$GATEWAY")" = "$GATEWAY_BLOB" || reject GATEWAY_CHANGED
test "$(/usr/bin/git hash-object "$BROKER")" = "$NEW_BROKER" || reject BROKER_INSTALL_CHANGED
test "$(/usr/bin/git hash-object "$AUDIT")" = "$NEW_AUDIT" || reject AUDIT_INSTALL_CHANGED
/usr/bin/systemctl enable cia-j1-owner-sqlite.socket >/dev/null || reject OWNER_SOCKET_ENABLE_FAILED
/usr/bin/systemctl is-enabled --quiet cia-j1-owner-sqlite.socket || reject OWNER_SOCKET_NOT_ENABLED
done_ok=1
printf 'CIA_J1_OWNER_UPGRADE=PASS\n'
printf 'OWNER_SQLITE_AUDIT=PASS\n'
printf 'FINANCIAL_MODULE_UNCHANGED=true\n'
printf 'MCP_TUNNEL_ACTIVE=true\n'
printf 'CIA_COLLECTOR_SQLITE_TIMER_UNCHANGED=true\n'
