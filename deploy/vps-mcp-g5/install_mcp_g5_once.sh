#!/usr/bin/env bash
# Scoped MCP bridge upgrade. Does NOT change n8n or the running LangGraph container.
set -Eeuo pipefail
umask 077

if [[ $(id -u) -ne 0 ]]; then
  echo 'G5_MCP_INSTALL=BLOCKED ROOT_REQUIRED'; exit 2
fi
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$ROOT_DIR"
BASE=/opt/agente-financeiro-mcp
CURRENT_MCP="$BASE/mcp_server.py"
CURRENT_BROKER="$BASE/operations_broker.py"
OPS_UNIT=/etc/systemd/system/agente-financeiro-mcp-ops.service
TUNNEL_UNIT=agente-financeiro-mcp-tunnel.service
OPS_SERVICE=agente-financeiro-mcp-ops.service
BACKUP_DIR="$BASE/backup-before-g5-mcp"

for x in "$CURRENT_MCP" "$CURRENT_BROKER" "$OPS_UNIT"; do
  [[ -f "$x" && ! -L "$x" ]] || { echo 'G5_MCP_INSTALL=BLOCKED ORIGINAL_MISSING'; exit 2; }
done
[[ -S /run/agente-financeiro-mcp/operations.sock ]] || { echo 'G5_MCP_INSTALL=BLOCKED BROKER_NOT_RUNNING'; exit 2; }
id agente-mcp >/dev/null 2>&1 || { echo 'G5_MCP_INSTALL=BLOCKED USER_MISSING'; exit 2; }

# The upgrade is only for the v2 gateway actually installed and verified.
[[ $(sha256sum "$CURRENT_MCP" | cut -d' ' -f1) == ddc9154666bf8cc784de97e2e6ec56b9adcf223719f5f05f702f67660f8962d8 ]] || {
  echo 'G5_MCP_INSTALL=BLOCKED GATEWAY_UNEXPECTED_VERSION'; exit 2;
}
[[ $(sha256sum "$CURRENT_BROKER" | cut -d' ' -f1) == b22e43f345870a1c72895f05fc88494c3bc5535478404051434fb3f85789209c ]] || {
  echo 'G5_MCP_INSTALL=BLOCKED BROKER_UNEXPECTED_VERSION'; exit 2;
}
[[ $(sha256sum "$OPS_UNIT" | cut -d' ' -f1) == e5aeac3ce5abc25967c01a18605bd9906821527677758e4157b3eab17aad9e83 ]] || {
  echo 'G5_MCP_INSTALL=BLOCKED SERVICE_UNEXPECTED_VERSION'; exit 2;
}
[[ ! -e "$BASE/benchmark_ops.py" ]] || { echo 'G5_MCP_INSTALL=BLOCKED OPERATOR_FILE_ALREADY_EXISTS'; exit 2; }
if [[ -e "$BACKUP_DIR" ]]; then
  [[ -d "$BACKUP_DIR" && ! -L "$BACKUP_DIR" ]] || {
    echo 'G5_MCP_INSTALL=BLOCKED UNTRUSTED_BACKUP'; exit 2;
  }
  [[ $(sha256sum "$BACKUP_DIR/mcp_server.py" | cut -d' ' -f1) == ddc9154666bf8cc784de97e2e6ec56b9adcf223719f5f05f702f67660f8962d8 ]] || exit 2
  [[ $(sha256sum "$BACKUP_DIR/operations_broker.py" | cut -d' ' -f1) == b22e43f345870a1c72895f05fc88494c3bc5535478404051434fb3f85789209c ]] || exit 2
  [[ $(sha256sum "$BACKUP_DIR/agente-financeiro-mcp-ops.service" | cut -d' ' -f1) == e5aeac3ce5abc25967c01a18605bd9906821527677758e4157b3eab17aad9e83 ]] || exit 2
  echo 'G5_MCP_BACKUP=REUSED'
else
  echo 'G5_MCP_BACKUP=CREATING'
fi

for name in mcp_server.py operations_broker.py benchmark_ops.py agente-financeiro-mcp-ops.service; do
  [[ -f "$name" && ! -L "$name" ]] || { echo 'G5_MCP_INSTALL=BLOCKED PACKAGE_INCOMPLETE'; exit 2; }
done
/usr/bin/python3 -B -m py_compile mcp_server.py operations_broker.py benchmark_ops.py

install -d -m 0700 -o root -g root /root/.local/share/agente-sql-langgraph/benchmark-private
if [[ ! -d "$BACKUP_DIR" ]]; then
  install -d -m 0700 -o root -g root "$BACKUP_DIR"
  install -m 0600 -o root -g root "$CURRENT_MCP" "$BACKUP_DIR/mcp_server.py"
  install -m 0600 -o root -g root "$CURRENT_BROKER" "$BACKUP_DIR/operations_broker.py"
  install -m 0600 -o root -g root "$OPS_UNIT" "$BACKUP_DIR/agente-financeiro-mcp-ops.service"
fi

complete=0
rollback() {
  if [[ $complete -ne 1 ]]; then
    echo 'G5_MCP_INSTALL=ROLLBACK' >&2
    install -m 0644 -o root -g root "$BACKUP_DIR/mcp_server.py" "$CURRENT_MCP" || true
    install -m 0644 -o root -g root "$BACKUP_DIR/operations_broker.py" "$CURRENT_BROKER" || true
    install -m 0644 -o root -g root "$BACKUP_DIR/agente-financeiro-mcp-ops.service" "$OPS_UNIT" || true
    rm -f "$BASE/benchmark_ops.py"
    systemctl daemon-reload || true
    systemctl restart "$OPS_SERVICE" || true
    systemctl restart "$TUNNEL_UNIT" || true
  fi
}
trap rollback EXIT

install -m 0644 -o root -g root benchmark_ops.py "$BASE/benchmark_ops.py"
install -m 0644 -o root -g root operations_broker.py "$CURRENT_BROKER"
install -m 0644 -o root -g root mcp_server.py "$CURRENT_MCP"
install -m 0644 -o root -g root agente-financeiro-mcp-ops.service "$OPS_UNIT"
systemctl daemon-reload
systemctl restart "$OPS_SERVICE"

# A Type=simple service becomes active before Python creates its socket.
ready=0
for i in $(seq 1 40); do
  if [[ -S /run/agente-financeiro-mcp/operations.sock ]] && \
    runuser -u agente-mcp -- /usr/bin/python3 -B - <<'PY' >/dev/null 2>&1
import json, socket
s=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
s.settimeout(2)
s.connect('/run/agente-financeiro-mcp/operations.sock')
s.sendall(b'{"op":"benchmark_status"}\n')
r=json.loads(s.recv(8192))
assert isinstance(r,dict) and 'status' in r
s.close()
PY
  then ready=1; break; fi
  sleep 0.5
done
if [[ "$ready" -ne 1 ]]; then
  echo 'G5_MCP_INSTALL=BLOCKED BROKER_PROBE_FAILED'; exit 2
fi
systemctl restart "$TUNNEL_UNIT"

ready=0
for i in $(seq 1 15); do
  if curl -fsS --max-time 2 http://127.0.0.1:8080/readyz >/dev/null 2>&1; then ready=1; break; fi
  sleep 1
done
[[ "$ready" -eq 1 ]] || { echo 'G5_MCP_INSTALL=BLOCKED TUNNEL_PROBE_FAILED'; exit 2; }
complete=1
trap - EXIT

echo 'G5_MCP_INSTALL=PASS'
echo 'G5_MCP_BROKER=PASS'
echo 'G5_MCP_TUNNEL=PASS'
echo 'ARBITRARY_SHELL=DENIED'
echo 'FINANCIAL_SQL_EXECUTION=DENIED'
echo 'N8N_MUTATION=DENIED'
echo 'SHADOW_CUTOVER=DENIED'
echo 'BENCHMARK_PRIVATE_RECOVERY=AVAILABLE'
echo 'NEXT=REFRESH_CHATGPT_PLUGIN_TOOLS'