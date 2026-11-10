"""Four fixed, audited VPS capabilities for historical benchmark recovery.

No general shell, SQL execution, model invocation, arbitrary path, or user input
can cross the MCP boundary. The actual G5 archive passphrase is entered once
by the operator on the VPS, consumed through a local root-only one-shot file,
and never returned to a plugin or logged. Historical benchmark data never
leaves the root-only VPS directory.
"""
from __future__ import annotations

import fcntl
import json
import os
import pty
import re
import select
import stat
import subprocess
import sys
import termios
import time
from pathlib import Path
from typing import Any

REPO = Path('/docker/agente-sql-langgraph-repo')
RUNTIME_DIR = Path('/run/agente-financeiro-mcp')
SECRET = RUNTIME_DIR / 'g5-benchmark-passphrase.once'
DEST = Path('/root/.local/share/agente-sql-langgraph/benchmark-private')
ARCHIVES = Path('/root/.local/share/agente-sql-langgraph/source-archives')
MANIFEST_RE = re.compile(r'source-([a-z]{20})-[0-9]{8}T[0-9]{6}Z-[0-9a-f]{16}\.dump\.gpg\.manifest\.json')
RECOVERY_COMMIT = '6f7d7c70c910b45948dd852e221e45f646e07226'
RECOVERY_BLOB = '2633c1d3b8f950d1740a6ec9f59638bf5fecfd20'
RECOVERY_MODULE = REPO / 'scripts/operations/g5_recover_legacy_benchmark_offline.py'
PYTHON = REPO / '.venv/bin/python'
RECOVERY_TIMEOUT = 3650
HEX40 = re.compile(r'[0-9a-f]{40}')
FOLDER = re.compile(r'legacy63-[0-9a-f]{20}')
REMOTE_ALLOWED = frozenset({
    'https://github.com/leandrosilveiradepaula/agente-sql-langgraph',
    'https://github.com/leandrosilveiradepaula/agente-sql-langgraph.git',
    'git@github.com:leandrosilveiradepaula/agente-sql-langgraph',
    'git@github.com:leandrosilveiradepaula/agente-sql-langgraph.git',
    'ssh://git@github.com/leandrosilveiradepaula/agente-sql-langgraph',
    'ssh://git@github.com/leandrosilveiradepaula/agente-sql-langgraph.git',
})
GIT = ('/usr/bin/git', '-c', 'core.hooksPath=/dev/null',
       '-c', 'protocol.file.allow=never', '-c', 'submodule.recurse=false',
       '-C', str(REPO))
ENVP = {'PATH': '/usr/local/bin:/usr/bin:/bin', 'LANG': 'C',
        'PYTHONDONTWRITEBYTECODE': '1', 'GIT_TERMINAL_PROMPT': '0',
        'GIT_LFS_SKIP_SMUDGE': '1', 'GIT_CONFIG_NOSYSTEM': '1',
        'GIT_CONFIG_GLOBAL': '/dev/null', 'HOME': '/root'}


class Refused(RuntimeError):
    """A safe, non-sensitive classification (never a raw subprocess error)."""


def _exec(args: list[str] | tuple[str, ...], *, timeout: int = 80) -> str:
    try:
        cp = subprocess.run(list(args), text=True, capture_output=True,
                            timeout=timeout, env=ENVP, cwd=str(REPO), check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise Refused('command_unavailable') from None
    if cp.returncode != 0 or len(cp.stdout) > 16000:
        raise Refused('command_failed')
    return cp.stdout.strip()


def _git(*args: str, timeout: int = 80) -> str:
    return _exec([*GIT, *args], timeout=timeout)


def _head() -> str:
    try:
        value = _git('rev-parse', 'HEAD', timeout=5)
    except Refused:
        raise Refused('repo_unavailable') from None
    if not HEX40.fullmatch(value):
        raise Refused('repo_head_invalid')
    return value


def _reviewed_source() -> None:
    _head()
    try:
        _git('merge-base', '--is-ancestor', RECOVERY_COMMIT, 'HEAD', timeout=8)
    except Refused:
        raise Refused('reviewed_recovery_ancestry_required') from None
    if RECOVERY_MODULE.is_symlink() or not RECOVERY_MODULE.is_file():
        raise Refused('reviewed_recovery_code_missing')
    if _git('hash-object', str(RECOVERY_MODULE), timeout=8) != RECOVERY_BLOB:
        raise Refused('reviewed_recovery_code_mismatch')
    if not PYTHON.is_file() or not os.access(PYTHON, os.X_OK):
        raise Refused('venv_python_missing')
    real_python = str(PYTHON.resolve())
    if not (real_python.startswith('/usr/bin/python3') or
            real_python.startswith('/usr/local/bin/python3') or
            real_python.startswith(str(REPO / '.venv/bin/python'))):
        raise Refused('venv_python_untrusted')


def _lock(name: str):
    """Root-owned runtime locks without allowing a caller-supplied path."""
    lockfile = RUNTIME_DIR / name
    fd = os.open(lockfile, os.O_CREAT | os.O_RDWR | getattr(os, 'O_NOFOLLOW', 0), 0o600)
    if not stat.S_ISREG(os.fstat(fd).st_mode):
        os.close(fd)
        raise Refused('unsafe_lock_file')
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        raise Refused('operation_already_running') from None
    return fd


def repo_sync(expected_sha: Any) -> dict[str, object]:
    """Fast-forward main to a SHA *actually* at the GitHub origin main ref."""
    if not isinstance(expected_sha, str) or not HEX40.fullmatch(expected_sha):
        return {'status': 'blocked', 'reason': 'expected_commit_sha_required'}
    try:
        fd = _lock('repo-sync.lock')
    except (OSError, Refused) as e:
        return {'status': 'blocked', 'reason': 'operation_already_running'}
    try:
        if REPO.is_symlink() or not REPO.is_dir() or REPO.stat().st_uid != 0:
            raise Refused('repo_path_untrusted')
        if _git('rev-parse', '--show-toplevel', timeout=5) != str(REPO):
            raise Refused('repo_root_mismatch')
        if _git('branch', '--show-current', timeout=5) != 'main':
            raise Refused('repo_not_on_main')
        if _git('status', '--porcelain', '--untracked-files=normal', timeout=10):
            raise Refused('repo_not_clean')
        if _git('remote', 'get-url', 'origin', timeout=5) not in REMOTE_ALLOWED:
            raise Refused('repo_origin_untrusted')
        previous = _head()
        if previous != expected_sha:
            _git('fetch', '--no-tags', '--no-recurse-submodules', 'origin', 'main', timeout=120)
            fetched = _git('rev-parse', 'FETCH_HEAD', timeout=5)
            if fetched != expected_sha:
                raise Refused('github_main_commit_mismatch')
            _git('merge-base', '--is-ancestor', 'HEAD', 'FETCH_HEAD', timeout=8)
            _git('merge', '--ff-only', 'FETCH_HEAD', timeout=45)
        if _head() != expected_sha or _git('status', '--porcelain', timeout=10):
            raise Refused('repo_sync_verification_failed')
        return {'status': 'pass', 'previous_sha': previous,
                'sha': expected_sha, 'changed': previous != expected_sha}
    except Refused as exc:
        reason = str(exc)
        return {'status': 'blocked', 'reason': reason if reason in {
            'repo_path_untrusted', 'repo_root_mismatch', 'repo_not_on_main',
            'repo_not_clean', 'repo_origin_untrusted', 'github_main_commit_mismatch',
            'repo_sync_verification_failed', 'command_failed', 'command_unavailable',
        } else 'sync_preflight_failed'}
    finally:
        os.close(fd)


def _source_ref() -> str:
    """Discover one verified G5 archive without baking in a client/tenant."""
    if ARCHIVES.is_symlink() or not ARCHIVES.is_dir():
        raise Refused('source_archive_directory_unavailable')
    matches = sorted(ARCHIVES.glob('source-*.dump.gpg.manifest.json'))
    if len(matches) != 1:
        raise Refused('source_archive_missing_or_ambiguous')
    if matches[0].is_symlink():
        raise Refused('source_archive_manifest_untrusted')
    match = MANIFEST_RE.fullmatch(matches[0].name)
    if not match:
        raise Refused('source_archive_manifest_invalid')
    return match.group(1)


def _plan() -> dict[str, object]:
    _reviewed_source()
    out = _exec([str(PYTHON), '-m',
                 'scripts.operations.g5_recover_legacy_benchmark_offline',
                 '--plan', '--source-project-ref', _source_ref()], timeout=70)
    parts = out.splitlines()
    checks = ('BENCHMARK_ARCHIVE_DIGEST=PASS', 'BENCHMARK_IMAGE_PINNED=PASS',
              'BENCHMARK_PLAN=PASS', 'BENCHMARK_SOURCE_DATA_READ=false')
    if not all(s in parts for s in checks):
        raise Refused('archive_plan_not_approved')
    return {'status': 'pass', 'archive_digest': 'pass',
            'postgres_image_cached': True, 'source_data_read': False,
            'financial_sql_executed': False}


def benchmark_plan() -> dict[str, object]:
    try:
        return _plan()
    except Refused as e:
        return {'status': 'blocked', 'reason': str(e)}


def _one_shot_secret() -> bytes:
    """Unlink *before* running untrusted restore; secrets never reach output."""
    try:
        st = SECRET.lstat()
        if not stat.S_ISREG(st.st_mode) or st.st_uid != 0 or (st.st_mode & 0o177):
            raise Refused('local_one_time_secret_permissions_invalid')
        if not 16 <= st.st_size <= 1024 or st.st_nlink != 1:
            raise Refused('local_one_time_secret_size_invalid')
        fd = os.open(SECRET, os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0))
        try:
            if (os.fstat(fd).st_dev, os.fstat(fd).st_ino) != (st.st_dev, st.st_ino):
                raise Refused('local_one_time_secret_changed')
            raw = os.read(fd, 1025)
        finally:
            os.close(fd)
        # The value is never passed via argv, environment, a network socket or logs.
        password = raw.rstrip(b'\r\n')
        if not password or b'\n' in password or b'\r' in password or b'\x00' in password:
            raise Refused('local_one_time_secret_invalid')
        password.decode('ascii')
        return password
    except FileNotFoundError:
        raise Refused('local_one_time_secret_missing') from None
    except (OSError, UnicodeError) as e:
        raise Refused('local_one_time_secret_invalid') from None
    finally:
        # Never retain the secret at rest, including after validation failures.
        try:
            SECRET.unlink(missing_ok=True)
        except OSError:
            raise Refused('secret_cleanup_failed') from None


def _tty_recover(password: bytes) -> dict[str, object]:
    """Drive the CLI's existing human TTY gate from a root-only local secret.

    ECHO is disabled *before* the child starts; we wait for distinct prompt
    strings. No captured terminal output, including failures, reaches MCP.
    """
    master, slave = pty.openpty()
    attrs = termios.tcgetattr(slave)
    attrs[3] &= ~(termios.ECHO | termios.ECHONL)
    termios.tcsetattr(slave, termios.TCSANOW, attrs)
    try:
        child = subprocess.Popen([
            str(PYTHON), '-m', 'scripts.operations.g5_recover_legacy_benchmark_offline',
            '--recover', '--source-project-ref', _source_ref(),
        ], stdin=slave, stdout=slave, stderr=slave, env=ENVP,
           cwd=str(REPO), close_fds=True)
    except OSError:
        os.close(master)
        os.close(slave)
        raise Refused('recovery_command_unavailable') from None
    os.close(slave)
    ack_sent = pwd_sent = False
    output = bytearray()
    deadline = time.monotonic() + RECOVERY_TIMEOUT
    try:
        while True:
            if time.monotonic() > deadline:
                # The reviewed CLI normally cleans up the isolated container
                # in its own finally. Do not forcibly kill it mid-cleanup.
                raise Refused('recovery_deadline_exceeded_review_cleanup')
            ready, _, _ = select.select([master], [], [], 1.0)
            if ready:
                try:
                    block = os.read(master, 4096)
                except OSError:
                    block = b''
                if block:
                    output.extend(block)
                    if len(output) > 20000:
                        raise Refused('recovery_output_limit')
                    if not ack_sent and b'Digite RECOVER-LEGACY-BENCHMARK-63:' in output:
                        os.write(master, b'RECOVER-LEGACY-BENCHMARK-63\n')
                        ack_sent = True
                    if ack_sent and not pwd_sent and b'Senha do arquivo G5 (sem eco):' in output:
                        os.write(master, password + b'\n')
                        pwd_sent = True
                elif child.poll() is not None:
                    break
            if child.poll() is not None and not ready:
                break
        code = child.wait(timeout=5)
        lines = output.decode('utf-8', 'replace').splitlines()
        if code != 0 or 'BENCHMARK_RECOVERY=PASS' not in lines:
            return {'status': 'blocked', 'reason': 'recovery_failed_or_archived_data_absent',
                    'financial_sql_executed': False}
        needed = ('BENCHMARK_CASES=63', 'BENCHMARK_OUTPUT_PRIVATE=PASS',
                  'BENCHMARK_ISOLATED_CONTAINER_CLEANUP=PASS',
                  'BENCHMARK_FINANCIAL_SQL_EXECUTED=false', 'BENCHMARK_LLM_CALLS=0')
        if not all(line in lines for line in needed):
            raise Refused('recovery_postconditions_unverified')
        # The full SQL, questions, raw responses and private files remain local.
        sql_info = [x.removeprefix('BENCHMARK_OFFICIAL_SQL_PRESENT=') for x in lines
                    if x.startswith('BENCHMARK_OFFICIAL_SQL_PRESENT=')]
        return {'status': 'pass', 'cases': 63,
                'historic_sql_present': int(sql_info[0]) if len(sql_info) == 1 and
                sql_info[0].isdigit() else None,
                'isolated_container_cleanup': 'pass', 'financial_sql_executed': False,
                'llm_calls': 0}
    finally:
        os.close(master)
        # The reviewed CLI is responsible for its own cleanup before exiting.
        if child.poll() is not None:
            child.wait(timeout=5)


def benchmark_recover() -> dict[str, object]:
    try:
        lock = _lock('benchmark-recovery.lock')
    except (OSError, Refused):
        return {'status': 'blocked', 'reason': 'operation_already_running'}
    try:
        _plan()
        if DEST.exists() and any(DEST.glob('legacy63-*')):
            raise Refused('private_snapshot_already_exists')
        secret = _one_shot_secret()
        return _tty_recover(secret)
    except Refused as e:
        return {'status': 'blocked', 'reason': str(e)}
    finally:
        os.close(lock)


def _private_json(path: Path, max_size: int) -> Any:
    st = path.lstat()
    if (not stat.S_ISREG(st.st_mode) or st.st_uid != 0
            or (st.st_mode & 0o177) or not 0 < st.st_size <= max_size):
        raise Refused('private_result_permissions_invalid')
    return json.loads(path.read_text(encoding='utf-8'))


def benchmark_status() -> dict[str, object]:
    """Aggregate status only; contents never cross the MCP boundary."""
    try:
        _reviewed_source()
        if not DEST.exists():
            return {'status': 'not_recovered'}
        rootstat = DEST.lstat()
        if not stat.S_ISDIR(rootstat.st_mode) or rootstat.st_uid != 0 or rootstat.st_mode & 0o077:
            raise Refused('private_root_permissions_invalid')
        dirs = list(DEST.glob('legacy63-*'))
        if len(dirs) != 1 or not FOLDER.fullmatch(dirs[0].name):
            raise Refused('recovery_snapshot_missing_or_ambiguous')
        substat = dirs[0].lstat()
        if not stat.S_ISDIR(substat.st_mode) or substat.st_uid != 0 or substat.st_mode & 0o077:
            raise Refused('private_folder_permissions_invalid')
        if {p.name for p in dirs[0].iterdir()} != {
            'questions-only.json', 'official-baseline.json',
            'freeze-receipt.json', 'historical-witness.json',
        }:
            raise Refused('recovery_snapshot_files_invalid')
        manifest = _private_json(dirs[0]/'questions-only.json', 8*1024*1024)
        baseline = _private_json(dirs[0]/'official-baseline.json', 12*1024*1024)
        receipt = _private_json(dirs[0]/'freeze-receipt.json', 4096)
        witness = _private_json(dirs[0]/'historical-witness.json', 64*1024*1024)
        cases = manifest.get('cases') if isinstance(manifest, dict) else None
        base_cases = baseline.get('cases') if isinstance(baseline, dict) else None
        historical = witness.get('benchmark_rows') if isinstance(witness, dict) else None
        if not all(isinstance(x, list) and len(x) == 63 for x in [cases, base_cases, historical]):
            raise Refused('recovery_case_count_invalid')
        if (not all(isinstance(x, dict) and set(x) == {'case_id','question'} for x in cases)
                or {x.get('case_id') for x in cases} != {x.get('case_id') for x in base_cases}):
            raise Refused('questions_only_manifest_inconsistent')
        if not isinstance(receipt, dict) or receipt.get('case_count') != 63:
            raise Refused('freeze_receipt_invalid')
        if not all(x.get('question') == next((b.get('question') for b in base_cases
                                              if b.get('case_id') == x.get('case_id')), None)
                   for x in cases):
            raise Refused('questions_only_manifest_inconsistent')
        # Independently verify the reviewed freeze contract, not just the count.
        if str(REPO) not in sys.path:
            sys.path.insert(0, str(REPO))
        from scripts.blind_shadow_benchmark import verify_freeze_receipt
        try:
            verify_freeze_receipt(baseline, manifest, receipt)
        except (ValueError, TypeError, KeyError):
            raise Refused('freeze_receipt_mismatch') from None
        return {'status': 'pass', 'cases': 63,
                'baseline_case_count': 63, 'history_case_count': 63,
                'questions_only': True, 'recovery_private': True,
                'freeze_receipt_present': True,
                'official_sql_present': sum(isinstance(x.get('official_sql'),str) and
                                            bool(x['official_sql'].strip()) for x in base_cases),
                'financial_sql_executed': False}
    except (OSError, ValueError, KeyError, TypeError, Refused, UnicodeError) as exc:
        return {'status': 'blocked', 'reason': (str(exc) if isinstance(exc, Refused)
                                             else 'private_result_invalid')}