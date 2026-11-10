"""Single-capability, local Unix socket reader for the private J1 SQLite.

Runs as Unix user cia-probe, NEVER as the financial MCP broker. The only
accepted wire operation is the constant literal 'cia_sqlite'. No paths, SQL,
symbol names or timestamps are caller-controlled. No network or writes.
"""
from __future__ import annotations

import json
import os
import pwd
import socket
import stat
import struct
import sys

from crypto_j1_readonly import sqlite_audit

SOCKET = "/run/cia-j1-owner/readonly.sock"
MAX_REQUEST = 128
MAX_REPLY = 4096
CLIENT_GROUP = "agente-mcp"


def _denied() -> dict[str, object]:
    return {
        "status": "blocked", "reason": "owner_audit_request_denied",
        "trading_enabled": False, "marketwide_top50_verified": False,
    }


def _authorized(raw: bytes, peer_uid: int) -> bool:
    if peer_uid != 0 or len(raw) > MAX_REQUEST or not raw.endswith(b"\n"):
        return False
    try:
        obj = json.loads(raw)
    except (ValueError, TypeError, UnicodeError):
        return False
    return type(obj) is dict and obj == {"op": "cia_sqlite"}


def _serve_client(conn: socket.socket) -> None:
    try:
        conn.settimeout(30.0)
        peer = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
        _pid, uid, _gid = struct.unpack("3i", peer)
        raw = bytearray()
        while len(raw) <= MAX_REQUEST:
            block = conn.recv(MAX_REQUEST + 1 - len(raw))
            if not block:
                break
            raw.extend(block)
            if b"\n" in block:
                break
        result = sqlite_audit() if _authorized(bytes(raw), uid) else _denied()
    except (OSError, TimeoutError, ValueError, TypeError):
        result = _denied()
    data = json.dumps(result, sort_keys=True, separators=(",", ":")).encode("ascii") + b"\n"
    if len(data) > MAX_REPLY:
        data = json.dumps(_denied(), separators=(",", ":")).encode("ascii") + b"\n"
    try:
        conn.sendall(data)
    except (OSError, TimeoutError):
        pass


def main() -> None:
    expected_uid = pwd.getpwnam("cia-probe").pw_uid
    if os.getuid() != expected_uid or os.geteuid() != expected_uid:
        raise RuntimeError("owner_user_required")
    directory = os.path.dirname(SOCKET)
    info = os.lstat(directory)
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != expected_uid or stat.S_IMODE(info.st_mode) != 0o750:
        raise RuntimeError("runtime_directory_untrusted")
    if os.path.lexists(SOCKET):
        raise RuntimeError("socket_path_already_exists")
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as server:
        server.bind(SOCKET)
        os.chmod(SOCKET, 0o660)
        server.listen(4)
        print("cia_j1_owner_sidecar=ready", flush=True)
        while True:
            conn, _addr = server.accept()
            with conn:
                _serve_client(conn)


if __name__ == "__main__":
    main()
