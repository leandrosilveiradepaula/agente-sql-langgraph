#!/usr/bin/env bash
# One-time installation of the owner-authorized VPS MCP administration tools.
# Installation changes only the existing MCP gateway/broker, not n8n or Shadow.
set -Eeuo pipefail
umask 077

REPO=/docker/agente-sql-langgraph-repo
SOURCE="$REPO/deploy/vps-mcp-g5"
TARGET=/opt/agente-financeiro-mcp
UNIT=/etc/systemd/system/agente-financeiro-mcp-ops.service
STATE=/var/lib/agente-financeiro-mcp-admin
SOCKET=/run/agente-financeiro-mcp/operations.sock
BROKER_SVC=agente-financeiro-mcp-ops.service
TUNNEL_SVC=agente-financeiro-mcp-tunnel.service

CURRENT_GATEWAY_BLOB=334d9c22bcf7b160867ab0755ad3f898f361ea25
CURRENT_BROKER_BLOB=65f966f4eb947fca91b7cf3f23f9541347dab632
CURRENT_UNIT_BLOB=64fb7d4567952eccefa8b9b3ad74b392e12cdad2

reject() { echo "MCP_ADMIN_INSTALL=BLOCKED"; echo "REASON=$1"; exit 2; }

[[ $(id -u) -eq 0 ]] || reject ROOT_REQUIRED
[[ -d "$REPO" && ! -L "$REPO" ]] || reject REPOSITORY_UNTRUSTED
[[ "$(/usr/bin/git -C "$REPO" branch --show-current)" == main ]] || reject MAIN_REQUIRED
/usr/bin/git -C "$REPO" diff --quiet || reject TRACKED_REPO_DIRTY
/usr/bin/git -C "$REPO" diff --cached --quiet || reject STAGED_REPO_DIRTY
for item in "$TARGET/mcp_server.py" "$TARGET/operations_broker.py" "$UNIT"; do
  [[ -f "$item" && ! -L "$item" ]] || reject CURRENT_COMPONENT_INVALID
done
for item in mcp_server.py operations_broker.py vps_admin.py agente-financeiro-mcp-ops.service; do
  [[ -f "$SOURCE/$item" && ! -L "$SOURCE/$item" ]] || reject SOURCE_INCOMPLETE
  /usr/bin/git -C "$REPO" diff --quiet HEAD -- "deploy/vps-mcp-g5/$item" \
    || reject REVIEWED_SOURCE_DIRTY
done
[[ -S "$SOCKET" ]] || reject BROKER_SOCKET_MISSING
/usr/bin/systemctl is-active --quiet "$BROKER_SVC" || reject BROKER_NOT_ACTIVE
/usr/bin/systemctl is-active --quiet "$TUNNEL_SVC" || reject TUNNEL_NOT_ACTIVE
for command in /usr/bin/git /usr/bin/python3 /usr/bin/install /usr/bin/systemctl /usr/bin/systemd-run /usr/sbin/runuser; do
  [[ -x "$command" ]] || reject REQUIRED_COMMAND_MISSING
done
/usr/bin/python3 -B -m py_compile "$SOURCE/vps_admin.py" "$SOURCE/operations_broker.py" "$SOURCE/mcp_server.py" \
  || reject PYTHON_VALIDATION_FAILED

# Verify currently installed gateway, broker and unit before replacing them.
OLD_GATEWAY=$(/usr/bin/git hash-object "$TARGET/mcp_server.py")
OLD_BROKER=$(/usr/bin/git hash-object "$TARGET/operations_broker.py")
OLD_UNIT=$(/usr/bin/git hash-object "$UNIT")
NEW_GATEWAY=$(/usr/bin/git hash-object "$SOURCE/mcp_server.py")
NEW_BROKER=$(/usr/bin/git hash-object "$SOURCE/operations_broker.py")
NEW_UNIT=$(/usr/bin/git hash-object "$SOURCE/agente-financeiro-mcp-ops.service")
NEW_ADMIN=$(/usr/bin/git hash-object "$SOURCE/vps_admin.py")

if [[ "$OLD_GATEWAY" == "$NEW_GATEWAY" &&
      "$OLD_BROKER" == "$NEW_BROKER" &&
      "$OLD_UNIT" == "$NEW_UNIT" &&
      -f "$TARGET/vps_admin.py" &&
      "$(/usr/bin/git hash-object "$TARGET/vps_admin.py")" == "$NEW_ADMIN" ]]; then
  echo "MCP_ADMIN_INSTALL=ALREADY_CURRENT"
  exit 0
fi

[[ "$OLD_GATEWAY" == "$CURRENT_GATEWAY_BLOB" ]] || reject CURRENT_GATEWAY_VERSION_MISMATCH
[[ "$OLD_BROKER" == "$CURRENT_BROKER_BLOB" ]] || reject CURRENT_BROKER_VERSION_MISMATCH
[[ "$OLD_UNIT" == "$CURRENT_UNIT_BLOB" ]] || reject CURRENT_UNIT_VERSION_MISMATCH
[[ ! -e "$TARGET/vps_admin.py" ]] || reject ADMIN_MODULE_ALREADY_EXISTS

BACKUP="$TARGET/backup-before-vps-admin-$(date -u +%Y%m%dT%H%M%SZ)"
[[ ! -e "$BACKUP" ]] || reject BACKUP_COLLISION
/usr/bin/install -d -m 0700 -o root -g root "$BACKUP" "$STATE"
for item in mcp_server.py operations_broker.py; do
  /usr/bin/install -m 0600 -o root -g root "$TARGET/$item" "$BACKUP/$item"
done
/usr/bin/install -m 0600 -o root -g root "$UNIT" "$BACKUP/agente-financeiro-mcp-ops.service"

installed=0
done_ok=0
cleanup() {
  rc=$?
  trap - EXIT
  if [[ "$installed" == 1 && "$done_ok" != 1 ]]; then
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/mcp_server.py" "$TARGET/mcp_server.py" || true
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/operations_broker.py" "$TARGET/operations_broker.py" || true
    /usr/bin/install -m 0644 -o root -g root "$BACKUP/agente-financeiro-mcp-ops.service" "$UNIT" || true
    /usr/bin/rm -f "$TARGET/vps_admin.py" || true
    /usr/bin/systemctl daemon-reload || true
    /usr/bin/systemctl restart "$BROKER_SVC" || true
    /usr/bin/systemctl restart "$TUNNEL_SVC" || true
    echo "MCP_ADMIN_INSTALL=ROLLED_BACK" >&2
  fi
  exit "$rc"
}
trap cleanup EXIT

installed=1
for item in mcp_server.py operations_broker.py vps_admin.py; do
  /usr/bin/install -m 0644 -o root -g root "$SOURCE/$item" "$TARGET/$item"
done
/usr/bin/install -m 0644 -o root -g root "$SOURCE/agente-financeiro-mcp-ops.service" "$UNIT"
/usr/bin/systemctl daemon-reload
/usr/bin/systemctl restart "$BROKER_SVC"

ready=0
for _attempt in $(seq 1 30); do
  if [[ -S "$SOCKET" ]] && /usr/sbin/runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY' >/dev/null 2>&1
import json, socket
socket_path="/run/agente-financeiro-mcp/operations.sock"
with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
    client.settimeout(4)
    client.connect(socket_path)
    client.sendall(json.dumps({
        "op":"admin_exec",
        "argv":["/usr/bin/id","-u"],
        "cwd":"/",
        "timeout_seconds":5,
        "show_output":True
    }).encode("ascii")+b"\n")
    message=bytearray()
    while not message.endswith(b"\n") and len(message)<16384:
        part=client.recv(1024)
        if not part: break
        message.extend(part)
result=json.loads(message)
assert result.get("status")=="completed",result
assert result.get("exit_code")==0,result
assert str(result.get("output","")).strip()=="0",result
PY
  then ready=1; break; fi
  sleep 1
done
[[ "$ready" == 1 ]] || reject ADMIN_BROKER_PROBE_FAILED

# Independently exercise the durable systemd job boundary before success.
/usr/sbin/runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY' >/dev/null 2>&1 || reject ADMIN_JOB_PROBE_FAILED
import json, socket, time

def request(message):
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(10)
        conn.connect("/run/agente-financeiro-mcp/operations.sock")
        conn.sendall(json.dumps(message).encode("ascii")+b"\n")
        data=bytearray()
        while not data.endswith(b"\n") and len(data)<16384:
            part=conn.recv(2048)
            if not part: break
            data.extend(part)
    return json.loads(bytes(data))
start=request({
    "op":"admin_start", "argv":["/usr/bin/true"],"cwd":"/",
    "timeout_seconds":30
})
assert start.get("status")=="queued", start
job_id=start["job_id"]
for _ in range(40):
    state=request({
        "op":"admin_status","job_id":job_id,"show_output":False
    })
    if state.get("status")=="completed":
        assert state.get("exit_code")==0, state
        break
    assert state.get("status") in ("queued","running"),state
    time.sleep(0.25)
else:
    raise RuntimeError("job_not_completed")
PY

/usr/bin/systemctl restart "$TUNNEL_SVC"
tunnel_ready=0
for _attempt in $(seq 1 20); do
  if /usr/bin/systemctl is-active --quiet "$TUNNEL_SVC" && \
     /usr/bin/curl --fail --silent --show-error --max-time 2 http://127.0.0.1:8080/readyz >/dev/null 2>&1; then
    tunnel_ready=1
    break
  fi
  sleep 1
done
[[ "$tunnel_ready" == 1 ]] || reject TUNNEL_PROBE_FAILED
[[ "$(/usr/bin/git hash-object "$TARGET/mcp_server.py")" == "$NEW_GATEWAY" ]] || reject INSTALLED_GATEWAY_DRIFT
[[ "$(/usr/bin/git hash-object "$TARGET/operations_broker.py")" == "$NEW_BROKER" ]] || reject INSTALLED_BROKER_DRIFT
[[ "$(/usr/bin/git hash-object "$TARGET/vps_admin.py")" == "$NEW_ADMIN" ]] || reject INSTALLED_ADMIN_DRIFT
done_ok=1
echo "MCP_ADMIN_INSTALL=PASS"
echo "MCP_ADMIN_EXEC=PASS"
echo "MCP_ADMIN_JOBS=AVAILABLE"
echo "MCP_TUNNEL=PASS"
echo "N8N_AND_SHADOW_UNCHANGED=true"
echo "NEXT=REFRESH_CHATGPT_PLUGIN_TOOLS"
