"""Single-capability, local Unix socket reader for the private J1 SQLite.

Runs as Unix user cia-probe, NEVER as the financial MCP broker. The only
accepted wire operation is the constant literal 'cia_sqlite'. No paths, SQL,
symbol names or timestamps are caller-controlled. No network or writes.
"""
from __future__ import annotations

import json
import os
import pwd
import grp
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
    """Serve exactly the one fd3 listener allocated by systemd root.

    No filesystem bind/chown, no ownership of the financial Unix group.
    """
    expected_uid = pwd.getpwnam("cia-probe").pw_uid
    expected_gid = pwd.getpwnam("cia-probe").pw_gid
    if (os.getuid() != expected_uid or os.geteuid() != expected_uid
            or os.getgid() != expected_gid or os.getegid() != expected_gid):
        raise RuntimeError("owner_user_and_group_required")
    if (os.environ.get("LISTEN_FDS") != "1"
            or os.environ.get("LISTEN_PID") != str(os.getpid())):
        raise RuntimeError("systemd_socket_activation_required")
    directory = os.path.dirname(SOCKET)
    dstat = os.lstat(directory)
    statinfo = os.lstat(SOCKET)
    if (not stat.S_ISDIR(dstat.st_mode) or dstat.st_uid != 0
            or stat.S_IMODE(dstat.st_mode) != 0o755
            or not stat.S_ISSOCK(statinfo.st_mode)
            or statinfo.st_uid != 0
            or statinfo.st_gid != grp.getgrnam(CLIENT_GROUP).gr_gid
            or stat.S_IMODE(statinfo.st_mode) != 0o660):
        raise RuntimeError("systemd_socket_untrusted")
    with socket.socket(fileno=3) as server:
        if server.family != socket.AF_UNIX or server.getsockname() != SOCKET:
            raise RuntimeError("unexpected_listener")
        print("cia_j1_owner_sidecar=ready", flush=True)
        while True:
            conn, _addr = server.accept()
            with conn:
                _serve_client(conn)


if __name__ == "__main__":
    main()
