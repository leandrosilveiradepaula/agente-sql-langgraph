#!/usr/bin/env bash
# CIA/J1 #235: owner-only D323 MCP extension. OFF by default.
# Changes only three read-only gateway modules and adds one fixed proxy.
# No collector changes, DB mutation, trading or data-provider network.
set -Eeuo pipefail
umask 077

# Existing root checkout may contain unrelated in-progress untracked G5 files.
# Source from one exact, root-only detached Git worktree instead; never touch them.
PRIMARY_REPO=/docker/agente-sql-langgraph-repo
SOURCE_PARENT=/var/lib/agente-financeiro-mcp-admin
REPO=$SOURCE_PARENT/cia-ws-d323-235-source
SRC=$REPO/deploy/vps-mcp-g5
DST=/opt/agente-financeiro-mcp
BACKUP=$DST/backup-before-cia-ws-d323-235
OWNER_SVC=cia-j1-owner-sqlite.service
OWNER_SOCKET=cia-j1-owner-sqlite.socket
BROKER_SVC=agente-financeiro-mcp-ops.service
TUNNEL_SVC=agente-financeiro-mcp-tunnel.service
NEW_MODULE=crypto_j1_ws_d323.py
test "$#" -eq 2 || { echo D323_MCP_RELEASE=INVALID_ARGUMENTS; exit 77; }
MODE=$1
EXPECTED=$2

fail() { echo "D323_MCP_RELEASE=BLOCKED"; echo "REASON=$1"; exit 77; }
case "$MODE" in --preflight|--confirm-readonly-owner-release) ;; *) fail MODE_NOT_ALLOWED ;; esac
[[ "$EXPECTED" =~ ^[0-9a-f]{40}$ ]] || fail EXACT_SHA_REQUIRED
test "$(id -u)" -eq 0 || fail ROOT_REQUIRED
test "$(hostname)" = srv1319424 || fail HOSTNAME_MISMATCH
test -d "$PRIMARY_REPO" && test ! -L "$PRIMARY_REPO" || fail PRIMARY_REPOSITORY_UNTRUSTED
test -d "$SOURCE_PARENT" && test ! -L "$SOURCE_PARENT" || fail SOURCE_PARENT_UNTRUSTED
test "$(stat -c %U:%G:%a "$SOURCE_PARENT")" = root:root:700 || fail SOURCE_PARENT_NOT_PRIVATE
test -d "$REPO" && test ! -L "$REPO" || fail SOURCE_WORKTREE_MISSING
test "$(stat -c %U:%G:%a "$REPO")" = root:root:700 || fail SOURCE_WORKTREE_NOT_PRIVATE
test "$(/usr/bin/git -C "$PRIMARY_REPO" remote get-url origin)" = \
  https://github.com/leandrosilveiradepaula/agente-sql-langgraph.git || fail ORIGIN_UNTRUSTED
test "$(/usr/bin/git -C "$PRIMARY_REPO" rev-parse refs/remotes/origin/main)" = "$EXPECTED" || fail ORIGIN_MAIN_MISMATCH
/usr/bin/git -C "$PRIMARY_REPO" merge-base --is-ancestor HEAD "$EXPECTED" || fail UNEXPECTED_ANCESTRY
test "$(/usr/bin/git -C "$REPO" rev-parse --show-toplevel)" = "$REPO" || fail WORKTREE_ROOT_MISMATCH
test "$(/usr/bin/git -C "$REPO" rev-parse --git-common-dir)" = "$PRIMARY_REPO/.git" || fail WORKTREE_ORIGIN_MISMATCH
test -z "$(/usr/bin/git -C "$REPO" branch --show-current)" || fail WORKTREE_NOT_DETACHED
test "$(/usr/bin/git -C "$REPO" rev-parse HEAD)" = "$EXPECTED" || fail HEAD_SHA_MISMATCH
test -z "$(/usr/bin/git -C "$REPO" status --porcelain)" || fail SOURCE_WORKTREE_DIRTY
test -d "$DST" && test ! -L "$DST" || fail GATEWAY_DIRECTORY_UNTRUSTED
test ! -e "$BACKUP" && test ! -L "$BACKUP" || fail BACKUP_ALREADY_EXISTS
test ! -e "$DST/$NEW_MODULE" && test ! -L "$DST/$NEW_MODULE" || fail D323_MODULE_ALREADY_PRESENT

# Exact baseline Git blobs read on VPS 14/11/2026. Refuse drift.
test "$(/usr/bin/git hash-object "$DST/mcp_server.py")" = \
  52c03b32367985593e3207f0131cd48165bb58e7 || fail MCP_VERSION_CHANGED
test "$(/usr/bin/git hash-object "$DST/operations_broker.py")" = \
  1699b553d174b90f208fc9878ebb3d157ed13312 || fail BROKER_VERSION_CHANGED
test "$(/usr/bin/git hash-object "$DST/cia_j1_sqlite_owner_sidecar.py")" = \
  499c396c6936c6c63c5551c4d4e7956a198d3c45 || fail SIDECAR_VERSION_CHANGED
test "$(/usr/bin/git hash-object "$DST/crypto_j1_readonly.py")" = \
  e876c2ae46d1164b05b76b323a527f2a31dcceea || fail REST_AUDITOR_DRIFT
for file in mcp_server.py operations_broker.py cia_j1_sqlite_owner_sidecar.py; do
  test -f "$DST/$file" && test ! -L "$DST/$file" || fail INSTALLED_FILE_UNTRUSTED
  test "$(stat -c %U:%G "$DST/$file")" = root:root || fail INSTALLED_OWNER_MISMATCH
done
for file in mcp_server.py operations_broker.py cia_j1_sqlite_owner_sidecar.py "$NEW_MODULE"; do
  test -f "$SRC/$file" && test ! -L "$SRC/$file" || fail SOURCE_MISSING
  expected_blob=$(/usr/bin/git -C "$REPO" rev-parse "$EXPECTED:deploy/vps-mcp-g5/$file") \
    || fail SOURCE_NOT_TRACKED_AT_SHA
  test "$(/usr/bin/git hash-object "$SRC/$file")" = "$expected_blob" || fail SOURCE_BLOB_MISMATCH
done

for unit in "$OWNER_SVC" "$OWNER_SOCKET" "$BROKER_SVC" "$TUNNEL_SVC"; do
  test "$(/usr/bin/systemctl show "$unit" -p ActiveState --value)" = active \
    || fail REQUIRED_READER_NOT_ACTIVE
done
test "$(/usr/bin/systemctl show "$OWNER_SVC" -p User --value)" = cia-probe \
  || fail OWNER_IDENTITY_MISMATCH
test "$(/usr/bin/systemctl show "$OWNER_SVC" -p ProtectHome --value)" = read-only \
  || fail OWNER_HOME_NOT_READONLY
test "$(/usr/bin/systemctl show "$OWNER_SVC" -p ProtectSystem --value)" = strict \
  || fail OWNER_FILESYSTEM_NOT_READONLY
test "$(/usr/bin/systemctl show "$OWNER_SVC" -p RestrictAddressFamilies --value)" = AF_UNIX \
  || fail OWNER_NETWORK_NOT_ISOLATED
test "$(/usr/bin/systemctl show "$OWNER_SOCKET" -p UnitFileState --value)" = enabled \
  || fail OWNER_SOCKET_NOT_ENABLED

SRC="$SRC" /usr/bin/python3 -B - <<'PY'
import ast, os
from pathlib import Path
base=Path(os.environ["SRC"])
for name in ("mcp_server.py", "operations_broker.py",
             "cia_j1_sqlite_owner_sidecar.py", "crypto_j1_ws_d323.py"):
    ast.parse((base/name).read_text(encoding="utf-8"), filename=name)
PY
echo D323_MCP_PREFLIGHT=PASS
if test "$MODE" = --preflight; then
  echo D323_MCP_DEPLOYED=NO
  exit 0
fi

phase=$(( $(/usr/bin/date -u +%s) % 3600 ))
if test "$phase" -lt 240 || test "$phase" -gt 3300; then
  fail CLOSE_WINDOW_UNSAFE
fi

installed=0
completed=0
restore() {
  original=$?
  trap - EXIT
  if test "$installed" = 1 && test "$completed" != 1; then
    echo D323_MCP_RELEASE=ROLLBACK >&2
    for file in mcp_server.py operations_broker.py cia_j1_sqlite_owner_sidecar.py; do
      /usr/bin/install -m 0644 -o root -g root "$BACKUP/$file" "$DST/$file" || true
    done
    /usr/bin/rm -f -- "$DST/$NEW_MODULE"
    /usr/bin/systemctl restart "$OWNER_SVC" || true
    /usr/bin/systemctl restart "$BROKER_SVC" || true
    /usr/bin/systemctl restart "$TUNNEL_SVC" || true
    verified=1
    for file in mcp_server.py operations_broker.py cia_j1_sqlite_owner_sidecar.py; do
      test "$(/usr/bin/git hash-object "$DST/$file")" = \
           "$(/usr/bin/git hash-object "$BACKUP/$file")" || verified=0
    done
    test ! -e "$DST/$NEW_MODULE" || verified=0
    for unit in "$OWNER_SVC" "$OWNER_SOCKET" "$BROKER_SVC" "$TUNNEL_SVC"; do
      test "$(/usr/bin/systemctl show "$unit" -p ActiveState --value)" = active || verified=0
    done
    if test "$verified" != 1; then
      echo D323_MCP_ROLLBACK=UNVERIFIED >&2
      exit 75
    fi
    echo D323_MCP_ROLLBACK=PASS >&2
  fi
  exit "$original"
}
trap restore EXIT
trap 'exit 130' INT
trap 'exit 143' TERM
/usr/bin/install -d -m 0700 -o root -g root "$BACKUP"
for file in mcp_server.py operations_broker.py cia_j1_sqlite_owner_sidecar.py; do
  /usr/bin/install -m 0600 -o root -g root "$DST/$file" "$BACKUP/$file"
done
installed=1
for file in "$NEW_MODULE" cia_j1_sqlite_owner_sidecar.py operations_broker.py mcp_server.py; do
  /usr/bin/install -m 0644 -o root -g root "$SRC/$file" "$DST/$file"
done

/usr/bin/systemctl restart "$OWNER_SVC"
/usr/bin/systemctl restart "$BROKER_SVC"
/usr/bin/systemctl restart "$TUNNEL_SVC"
for unit in "$OWNER_SVC" "$OWNER_SOCKET" "$BROKER_SVC" "$TUNNEL_SVC"; do
  test "$(/usr/bin/systemctl show "$unit" -p ActiveState --value)" = active \
    || fail READER_RESTART_FAILED
done

# Probe over the existing broker socket, as its authenticated client user.
/usr/sbin/runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY'
import json, socket
with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(105)
    client.connect("/run/agente-financeiro-mcp/operations.sock")
    client.sendall(b'{"op":"cia_ws_d323"}\n')
    raw = bytearray()
    while b"\n" not in raw and len(raw) <= 4096:
        block = client.recv(min(1024,4097-len(raw)))
        if not block:
            break
        raw.extend(block)
if not raw.endswith(b"\n") or raw.count(b"\n") != 1 or len(raw)>4096:
    raise SystemExit("D323_MCP_SMOKE=BLOCKED")
report=json.loads(raw[:-1])
if (report.get("schema_version") != "j1-n50-ws-closed24h-owner-witness-v1"
        or report.get("orders_sent") is not False
        or report.get("live_trading_authorized") is not False
        or report.get("marketwide_top50_verified") is not False):
    raise SystemExit("D323_MCP_SMOKE=BLOCKED")
print("D323_MCP_SMOKE=PASS")
PY
completed=1
trap - EXIT
echo D323_MCP_DEPLOYED=PASS
echo D323_MCP_ORDERS=DISABLED
echo D323_MCP_NEXT=REFRESH_PLUGIN_TOOLS
