"""Owner-authorized VPS administration, via the existing authenticated Unix broker.

Two execution modes:
* exec: short argv command, no implicit shell, bounded output and runtime
* job: a long-running systemd transient unit with root-private durable receipts

No command or secret value is written to the audit journal. Existing broker
SO_PEERCRED authentication still protects these operations; only the trusted
MCP service identity can request them.

Calls from the assistant are still subject to explicit human approval for
production, cost, privilege expansion, schema changes and real SQL execution.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import re
import resource
import stat
import subprocess
import sys
import time
import uuid
from typing import Any

BASE = Path("/var/lib/agente-financeiro-mcp-admin")
REPO = Path("/docker/agente-sql-langgraph-repo")
CODE = Path("/opt/agente-financeiro-mcp/vps_admin.py")
SYSTEMD_RUN = "/usr/bin/systemd-run"
SYSTEMCTL = "/usr/bin/systemctl"
PYTHON = "/usr/bin/python3"
UNIT_PREFIX = "agente-financeiro-admin-"
MAX_ARGV_BYTES = 12000
MAX_ARG_COUNT = 64
MAX_SYNC_TIMEOUT = 120
MAX_JOB_TIMEOUT = 14400
MAX_LOG_BYTES = 16 * 1024 * 1024
MAX_RETURN_CHARS = 5000
JOB_ID_PATTERN = re.compile(r"^[0-9a-f]{32}$")

# Redact known credentials in bounded *diagnostic* output. Do not run commands
# that print secrets; generic output cannot be guaranteed non-sensitive.
REDACTIONS = (
    (re.compile(r"(?i)\b(bearer\s+)[A-Za-z0-9._~+/\-]+=*"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b((?:api[_-]?key|token|password|passwd|secret|authorization|dsn)\s*[:=]\s*)[^\s,;]+"),
     r"\1[REDACTED]"),
    (re.compile(r"(?i)(?:postgres(?:ql)?|mongodb|redis|mysql)://[^\s\"']+"),
     "[REDACTED_CONNECTION]"),
    (re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"), "[REDACTED_KEY]"),
)
EXEC_ENV = {
    "PATH": "/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin",
    "LANG": "C.UTF-8",
    "PYTHONDONTWRITEBYTECODE": "1",
    "GIT_TERMINAL_PROMPT": "0",
}


class Refused(ValueError):
    pass


def _check_argv(argv: Any) -> list[str]:
    if not isinstance(argv, list) or not 1 <= len(argv) <= MAX_ARG_COUNT:
        raise Refused("argv_invalid")
    if any(not isinstance(arg, str) or not arg or "\x00" in arg
           for arg in argv):
        raise Refused("argv_invalid")
    if not argv[0].startswith("/"):
        raise Refused("argv_executable_must_be_absolute")
    if sum(len(item.encode("utf-8")) for item in argv) > MAX_ARGV_BYTES:
        raise Refused("argv_too_large")
    if not Path(argv[0]).is_file():
        raise Refused("executable_not_found")
    return list(argv)


def _check_cwd(value: Any) -> str:
    if not isinstance(value, str) or not value.startswith("/") or "\x00" in value:
        raise Refused("working_directory_invalid")
    folder = Path(value)
    if not folder.is_dir():
        raise Refused("working_directory_missing")
    return str(folder.resolve())


def _check_timeout(value: Any, *, maximum: int) -> int:
    if type(value) is not int or not 1 <= value <= maximum:
        raise Refused("timeout_invalid")
    return value


def _state() -> Path:
    if BASE.is_symlink() or not BASE.is_dir():
        raise Refused("state_directory_unavailable")
    props = BASE.stat()
    if props.st_uid != 0 or (props.st_mode & 0o077):
        raise Refused("state_permissions_invalid")
    return BASE


def _job_dir(job_id: Any) -> Path:
    if not isinstance(job_id, str) or not JOB_ID_PATTERN.fullmatch(job_id):
        raise Refused("job_id_invalid")
    return _state() / job_id


def _read_json(path: Path) -> dict[str, Any]:
    st = path.lstat()
    if not stat.S_ISREG(st.st_mode) or st.st_uid != os.geteuid() or st.st_mode & 0o077:
        raise Refused("private_state_permissions_invalid")
    if st.st_size > MAX_ARGV_BYTES + 4096:
        raise Refused("state_document_too_large")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise Refused("state_document_invalid")
    return data


def _write_json(path: Path, payload: dict[str, Any], *, exclusive: bool = False) -> None:
    flags = os.O_WRONLY | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    flags |= os.O_EXCL if exclusive else os.O_TRUNC
    descriptor = os.open(path, flags, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as out:
        json.dump(payload, out, separators=(",", ":"), sort_keys=True)
        out.write("\n")


def _receipt(*, op: str, argv: list[str], status: str, job_id: str | None = None,
             exit_code: int | None = None) -> None:
    # The audit contains a command digest, not argv or secret-bearing output.
    payload = {
        "ts": int(time.time()),
        "operation": op,
        "status": status,
        "command_sha256": hashlib.sha256(
            json.dumps(argv, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
        ).hexdigest(),
    }
    if job_id is not None:
        payload["job_id"] = job_id
    if exit_code is not None:
        payload["exit_code"] = exit_code
    path = _state() / "audit.jsonl"
    flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags, 0o600)
    try:
        os.write(descriptor, (json.dumps(payload, separators=(",", ":")) + "\n").encode("utf-8"))
    finally:
        os.close(descriptor)


def _sanitize(text: str, *, maximum: int = MAX_RETURN_CHARS) -> tuple[str, bool]:
    if not isinstance(text, str):
        return "", True
    clipped = len(text) > maximum
    value = text[-maximum:]
    # Remove nonprinting terminal controls and keep structured diagnostics.
    value = "".join(ch for ch in value if ch in "\n\r\t" or 32 <= ord(ch) < 127
                    or ord(ch) >= 160)
    for pattern, replacement in REDACTIONS:
        value = pattern.sub(replacement, value)
    return value, clipped


def _tail(path: Path) -> tuple[str, bool]:
    if not path.is_file() or path.is_symlink():
        return "", False
    size = path.stat().st_size
    with path.open("rb") as stream:
        stream.seek(max(0, size - MAX_RETURN_CHARS))
        raw = stream.read(MAX_RETURN_CHARS)
    msg, clipped = _sanitize(raw.decode("utf-8", errors="replace"))
    return msg, clipped or size > MAX_RETURN_CHARS


def _limit_output_file_size() -> None:
    resource.setrlimit(resource.RLIMIT_FSIZE, (MAX_LOG_BYTES, MAX_LOG_BYTES))


def _execute(argv: list[str], cwd: str, timeout: int, *, output_path: Path) -> tuple[int | None, str]:
    try:
        with output_path.open("xb") as output:
            os.chmod(output_path, 0o600)
            result = subprocess.run(
                argv, cwd=cwd, env=EXEC_ENV, stdin=subprocess.DEVNULL,
                stdout=output, stderr=subprocess.STDOUT,
                timeout=timeout, check=False, shell=False,
                preexec_fn=_limit_output_file_size,
            )
        return result.returncode, "completed"
    except subprocess.TimeoutExpired:
        return None, "timed_out"
    except (OSError, ValueError):
        return None, "failed"


def execute(argv: Any, cwd: Any = str(REPO), timeout_seconds: Any = 60,
            show_output: Any = True) -> dict[str, Any]:
    try:
        args = _check_argv(argv)
        directory = _check_cwd(cwd)
        timeout = _check_timeout(timeout_seconds, maximum=MAX_SYNC_TIMEOUT)
        if type(show_output) is not bool:
            raise Refused("show_output_invalid")
        _state()
        job_id = uuid.uuid4().hex
        output_path = _state() / ("sync-" + job_id + ".log")
        exit_code, status = _execute(args, directory, timeout, output_path=output_path)
        _receipt(op="exec", argv=args, status=status, exit_code=exit_code)
        message, clipped = _tail(output_path) if show_output else ("", False)
        output_path.unlink(missing_ok=True)
        return {
            "status": status, "exit_code": exit_code,
            "output": message, "output_truncated": clipped,
            "command_sha256": hashlib.sha256(
                json.dumps(args, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
            ).hexdigest(),
        }
    except (Refused, OSError) as exc:
        reason = str(exc) if isinstance(exc, Refused) else "exec_unavailable"
        return {"status": "blocked", "reason": reason}


def start(argv: Any, cwd: Any = str(REPO), timeout_seconds: Any = 3600) -> dict[str, Any]:
    try:
        args = _check_argv(argv)
        directory = _check_cwd(cwd)
        timeout = _check_timeout(timeout_seconds, maximum=MAX_JOB_TIMEOUT)
        job_id = uuid.uuid4().hex
        jobdir = _job_dir(job_id)
        jobdir.mkdir(mode=0o700)
        _write_json(jobdir / "request.json", {
            "argv": args, "cwd": directory, "timeout_seconds": timeout,
        }, exclusive=True)
        _write_json(jobdir / "status.json", {
            "state": "queued", "exit_code": None,
        }, exclusive=True)
        unit = UNIT_PREFIX + job_id
        cmd = [
            SYSTEMD_RUN, "--quiet", "--collect", "--unit=" + unit,
            "--property=Type=oneshot",
            "--property=TimeoutStartSec=" + str(timeout + 120),
            PYTHON, str(CODE), "--worker", job_id,
        ]
        result = subprocess.run(
            cmd, cwd="/", env=EXEC_ENV, stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, check=False, shell=False,
        )
        if result.returncode != 0:
            _write_json(jobdir / "status.json", {
                "state": "start_failed", "exit_code": None,
            })
            return {"status": "blocked", "reason": "systemd_job_launch_failed"}
        _receipt(op="job_start", argv=args, status="queued", job_id=job_id)
        return {
            "status": "queued", "job_id": job_id,
            "unit": unit, "timeout_seconds": timeout,
        }
    except (Refused, OSError, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, Refused) else "job_unavailable"
        return {"status": "blocked", "reason": reason}


def worker(job_id: str) -> int:
    try:
        folder = _job_dir(job_id)
        request = _read_json(folder / "request.json")
        args = _check_argv(request.get("argv"))
        cwd = _check_cwd(request.get("cwd"))
        timeout = _check_timeout(request.get("timeout_seconds"), maximum=MAX_JOB_TIMEOUT)
        _write_json(folder / "status.json", {"state": "running", "exit_code": None})
        exit_code, execution_status = _execute(
            args, cwd, timeout, output_path=folder / "output.log",
        )
        _write_json(folder / "status.json", {
            "state": execution_status, "exit_code": exit_code,
        })
        _receipt(op="job_finish", argv=args, status=execution_status,
                 job_id=job_id, exit_code=exit_code)
        return 0 if execution_status == "completed" and exit_code == 0 else 1
    except (Refused, OSError, ValueError, TypeError, KeyError):
        # Never print raw failure context to journal.
        return 2


def status(job_id: Any, show_output: Any = True) -> dict[str, Any]:
    try:
        if type(show_output) is not bool:
            raise Refused("show_output_invalid")
        folder = _job_dir(job_id)
        if folder.is_symlink() or not folder.is_dir():
            raise Refused("job_not_found")
        data = _read_json(folder / "status.json")
        state = data.get("state")
        if state not in ("queued", "running", "completed", "timed_out",
                         "failed", "start_failed", "cancel_requested"):
            raise Refused("job_state_invalid")
        message, clipped = _tail(folder / "output.log") if show_output else ("", False)
        return {
            "status": state, "job_id": job_id,
            "exit_code": data.get("exit_code"),
            "output": message,
            "output_truncated": clipped,
        }
    except (Refused, OSError, ValueError) as exc:
        reason = str(exc) if isinstance(exc, Refused) else "job_status_unavailable"
        return {"status": "blocked", "reason": reason}


def cancel(job_id: Any) -> dict[str, Any]:
    try:
        folder = _job_dir(job_id)
        state = _read_json(folder / "status.json")
        if state.get("state") not in ("queued", "running"):
            return {"status": "blocked", "reason": "job_not_active"}
        result = subprocess.run(
            [SYSTEMCTL, "stop", UNIT_PREFIX + job_id],
            env=EXEC_ENV, cwd="/", stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            timeout=20, check=False, shell=False,
        )
        if result.returncode != 0:
            raise Refused("job_cancel_failed")
        _write_json(folder / "status.json", {
            "state": "cancel_requested", "exit_code": None,
        })
        return {"status": "cancel_requested", "job_id": job_id}
    except (Refused, OSError, subprocess.SubprocessError) as exc:
        reason = str(exc) if isinstance(exc, Refused) else "job_cancel_unavailable"
        return {"status": "blocked", "reason": reason}


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--worker":
        raise SystemExit(worker(sys.argv[2]))
    raise SystemExit(2)
