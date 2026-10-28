"""G5 isolated restore safety tests; no real database or Docker resources."""
from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import MagicMock, patch

MODULE = Path(__file__).resolve().parent / "operations" / "g5_restore_isolated_rehearsal.py"
SPEC = importlib.util.spec_from_file_location("g5_restore_isolated_rehearsal", MODULE)
m = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(m)
SOURCE = "nywxpvzhlpqjtcafpdfe"
IMAGE = "sha256:" + "a" * 64
PASSWORD = "S" * 40  # Synthetic only, never use as a real archive password.


class G5IsolatedRehearsalTests(unittest.TestCase):
    def test_image_must_be_cached_exact_sha_without_pull(self):
        docker = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]
        with patch.object(m, "docker_query", return_value=MagicMock(
                returncode=0, stdout=(IMAGE + "\n").encode())) as probe:
            self.assertEqual(m.image_id(docker), IMAGE)
            probe.assert_called_once_with(
                docker, ["image", "inspect", "--format", "{{.Id}}", "postgres:17"]
            )
        for invalid in (b"", b"postgres:17\n", b"sha256:bad\n"):
            with patch.object(m, "docker_query", return_value=MagicMock(
                    returncode=1, stdout=invalid)):
                with self.assertRaises(m.ArchiveBlocked):
                    m.image_id(docker)

    def test_no_remote_context_credential_or_connection_is_inherited(self):
        with patch.dict(os.environ, {
            "DOCKER_HOST": "tcp://external.example:2375",
            "DOCKER_CONTEXT": "prod",
            "PGPASSWORD": "secret",
            "DATABASE_URL": "postgres://private",
            "PATH": "/bin:/usr/bin",
            "HOME": "/root",
        }):
            env = m.isolated_docker_env()
            self.assertNotIn("DOCKER_HOST", env)
            self.assertNotIn("DOCKER_CONTEXT", env)
            self.assertNotIn("PGPASSWORD", env)
            self.assertNotIn("DATABASE_URL", env)
            self.assertEqual(env["HOME"], "/nonexistent")

    def test_run_is_networkless_unprivileged_memory_backed_and_ephemeral(self):
        argv = m.isolated_run_args(IMAGE, "g5-restore-1234567890abcdef")
        combined = " ".join(argv)
        for safe_flag in (
            "--network=none", "--read-only", "--user=999:999",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pids-limit=128", "--memory=1g", "--cpus=1",
            "--pull=never", "--rm", "--log-driver=none",
            "--env=POSTGRES_HOST_AUTH_METHOD=trust",
            "listen_addresses=",
        ):
            self.assertIn(safe_flag, argv)
        self.assertEqual(sum(p.startswith("--tmpfs=") for p in argv), 3)
        self.assertFalse(any(p in ("-v", "--volume", "-p", "-P", "--mount",
                                   "--privileged", "--network=host") for p in argv))
        self.assertNotIn("/root/.local/share", combined)
        self.assertNotIn(SOURCE, combined)
        with self.assertRaises(m.ArchiveBlocked):
            m.isolated_run_args("postgres:17", "g5-restore-1234567890abcdef")
        with self.assertRaises(m.ArchiveBlocked):
            m.isolated_run_args(IMAGE, "prod")

    @unittest.skipUnless(os.name == "posix", "Linux Unix-domain Docker socket only")
    def test_only_local_unix_socket_is_allowed(self):
        with patch.object(m.shutil, "which", return_value="/usr/bin/docker"):
            with patch.object(type(m.DOCKER_SOCKET), "lstat") as st:
                st.return_value = MagicMock(st_mode=0o140600, st_uid=0)
                self.assertEqual(m.docker_executable(), [
                    "/usr/bin/docker", "--host=unix:///var/run/docker.sock",
                ])
                st.return_value = MagicMock(st_mode=0o100600, st_uid=0)
                with self.assertRaises(m.ArchiveBlocked):
                    m.docker_executable()

    def test_inspection_rejects_bind_network_port_privileged_and_images(self):
        def base():
            return {
                "Image": IMAGE,
                "HostConfig": {
                    "NetworkMode": "none", "ReadonlyRootfs": True,
                    "Privileged": False, "AutoRemove": True,
                    "UsernsMode": "", "PidMode": "",
                    "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                    "Binds": None, "Devices": [], "PortBindings": {},
                },
                "Config": {
                    "User": "999:999",
                    "Labels": {"agente-sql-langgraph.g5": "isolated-rehearsal"},
                },
                "Mounts": [
                    {"Type": "tmpfs", "Destination": "/var/lib/postgresql/data"},
                    {"Type": "tmpfs", "Destination": "/var/run/postgresql"},
                ],
                "NetworkSettings": {"Ports": {"5432/tcp": None}},
            }
        def attest(payload):
            with patch.object(m, "docker_query", return_value=MagicMock(
                    returncode=0, stdout=json.dumps(payload).encode())):
                return m.check_container_isolation(
                    ["/usr/bin/docker"], "g5-restore-1234567890abcdef", IMAGE
                )
        self.assertIsNone(attest(base()))
        for modify in (
            lambda x: x["HostConfig"].update(NetworkMode="bridge"),
            lambda x: x["HostConfig"].update(Privileged=True),
            lambda x: x["HostConfig"].update(ReadonlyRootfs=False),
            lambda x: x["HostConfig"].update(Binds=["/root:/host"]),
            lambda x: x["HostConfig"].update(PortBindings={"5432/tcp": [{"HostPort": "5432"}]}),
            lambda x: x["NetworkSettings"].update(Ports={"5432/tcp": [{"HostPort": "5432"}]}),
            lambda x: x["Mounts"].append({"Type": "volume", "Destination": "/var/lib/postgresql"}),
            lambda x: x.update(Image="sha256:" + "b" * 64),
            lambda x: x["Config"].update(User="root"),
        ):
            payload = base()
            modify(payload)
            with self.subTest(change=repr(modify)), self.assertRaises(m.ArchiveBlocked):
                attest(payload)

    def test_restore_command_has_no_external_dsn_or_pg_dump_runtime_credentials(self):
        args = m.isolated_exec_args(
            "g5-restore-1234567890abcdef", "pg_restore",
            "--host=/var/run/postgresql", "--username=postgres",
            "--dbname=postgres", "--no-owner", "--no-acl",
            "--single-transaction", "--exit-on-error",
            interactive=True,
        )
        self.assertIn("--interactive", args)
        self.assertIn("--dbname=postgres", args)
        self.assertNotIn("--jobs", args)
        self.assertNotIn("cenhadslwxgykqtuobgc", " ".join(args))
        self.assertNotIn("nywxpvzhlpqjtcafpdfe", " ".join(args))
        with self.assertRaises(m.ArchiveBlocked):
            m.isolated_exec_args("g5-restore-1234567890abcdef", "sh", "-c", "rm -rf /")

    def test_cleanup_is_required_for_success_even_if_restore_succeeded(self):
        response = MagicMock(returncode=0, stdout=b"postgres (PostgreSQL) 17.11\n")
        def docker_fake(prefix, args):
            if args[:2] == ["container", "inspect"]:
                return MagicMock(returncode=1, stdout=b"")
            return response
        with patch.object(m.os, "geteuid", return_value=0, create=True):
            with patch.object(m, "docker_query", side_effect=docker_fake):
                with patch.object(m, "check_container_isolation"):
                    with patch.object(m, "restore_stream"):
                        with patch.object(m, "verify_restored_tables", return_value=47):
                            with patch.object(m, "cleanup_container", return_value=True):
                                self.assertEqual(m.rehearsed_restore(
                                    Path("/encrypted.gpg"), PASSWORD,
                                    ["/usr/bin/docker"], IMAGE,
                                ), 47)
                            with patch.object(m, "cleanup_container", return_value=False):
                                with self.assertRaises(m.ArchiveBlocked) as err:
                                    m.rehearsed_restore(
                                        Path("/encrypted.gpg"), PASSWORD,
                                        ["/usr/bin/docker"], IMAGE,
                                    )
                                self.assertEqual(str(err.exception), "ISOLATED_CLEANUP_UNVERIFIED")

    def test_sql_restore_failure_is_not_concealed_or_retried(self):
        with patch.object(m.os, "geteuid", return_value=0, create=True):
            with patch.object(m, "docker_query", return_value=MagicMock(
                    returncode=0, stdout=b"postgres (PostgreSQL) 17.11")):
                with patch.object(m, "check_container_isolation"):
                    with patch.object(m, "restore_stream",
                                      side_effect=m.ArchiveBlocked("ISOLATED_RESTORE_SQL_FAILED")) as step:
                        with patch.object(m, "cleanup_container", return_value=True):
                            with self.assertRaises(m.ArchiveBlocked) as err:
                                m.rehearsed_restore(
                                    Path("/encrypted.gpg"), PASSWORD,
                                    ["/usr/bin/docker"], IMAGE,
                                )
                            self.assertEqual(str(err.exception), "ISOLATED_RESTORE_SQL_FAILED")
                            step.assert_called_once()

    def test_plan_is_no_capture_no_password_no_container(self):
        import sys
        args = ["g5_restore_isolated_rehearsal", "--plan",
                "--manifest", "/root/private/manifest.json",
                "--source-project-ref", SOURCE]
        with patch.object(sys, "argv", args):
            with patch.object(m, "validated_archive", return_value=Path("/encrypted.gpg")):
                with patch.object(m, "docker_executable", return_value=["/usr/bin/docker"]):
                    with patch.object(m, "image_id", return_value=IMAGE):
                        with patch.object(m.getpass, "getpass") as prompt:
                            with patch.object(m, "rehearsed_restore") as rehearsal:
                                with contextlib.redirect_stdout(io.StringIO()) as output:
                                    self.assertEqual(m.main(), 0)
                                prompt.assert_not_called()
                                rehearsal.assert_not_called()
                                self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED", output.getvalue())

    def test_restore_requires_new_explicit_operator_confirmation_before_password(self):
        import sys
        args = ["g5_restore_isolated_rehearsal", "--restore",
                "--manifest", "/root/private/manifest.json",
                "--source-project-ref", SOURCE]
        with patch.object(sys, "argv", args):
            with patch.object(m, "validated_archive", return_value=Path("/encrypted.gpg")):
                with patch.object(m, "docker_executable", return_value=["/usr/bin/docker"]):
                    with patch.object(m, "image_id", return_value=IMAGE):
                        with patch.object(m.sys.stdin, "isatty", return_value=True):
                            with patch("builtins.input", return_value="NO"):
                                with patch.object(m.getpass, "getpass") as secret:
                                    with patch.object(m, "rehearsed_restore") as action:
                                        with contextlib.redirect_stdout(io.StringIO()) as output:
                                            self.assertEqual(m.main(), 2)
                                        secret.assert_not_called()
                                        action.assert_not_called()
                                        self.assertIn("ISOLATED_RESTORE_NOT_AUTHORIZED", output.getvalue())

    def test_cleanup_does_not_treat_docker_outage_as_proof(self):
        def fake(prefix, args):
            if args[:1] == ["version"]:
                return MagicMock(returncode=1)
            return MagicMock(returncode=0)
        with patch.object(m, "docker_query", side_effect=fake):
            self.assertFalse(m.cleanup_container(["/usr/bin/docker"],
                                                 "g5-restore-1234567890abcdef"))

    @unittest.skipUnless(os.name == "posix" and shutil.which("gpg"), "Requires POSIX/GPG")
    def test_gpg_to_fake_docker_pipe_with_synthetic_encrypted_archive(self):
        """No database: real decryption streams to a fake Docker stdin reader."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            encrypted = root / "fixture.gpg"
            reader, writer = os.pipe()
            try:
                gpg = subprocess.Popen(
                    [shutil.which("gpg"), "--batch", "--no-tty", "--pinentry-mode",
                     "loopback", "--no-symkey-cache", "--passphrase-fd", str(reader),
                     "--symmetric", "--output", str(encrypted)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, pass_fds=(reader,),
                )
                os.close(reader)
                reader = None
                os.write(writer, PASSWORD.encode() + b"\n")
                os.close(writer)
                writer = None
                gpg.communicate(b"PGDMP" + b"synthetic_only_" * 4000, timeout=25)
                self.assertEqual(gpg.returncode, 0)
            finally:
                for fd in (reader, writer):
                    if fd is not None:
                        os.close(fd)
            fake_docker = root / "fake-docker"
            fake_docker.write_text(
                "#!/bin/sh\n"
                "cat >/dev/null\n"
                "exit 0\n",
                encoding="ascii",
            )
            fake_docker.chmod(0o700)
            with patch.dict(os.environ, {"GNUPGHOME": str(root / "gnupg")}):
                (root / "gnupg").mkdir(mode=0o700)
                with patch.object(m, "isolated_docker_env", return_value={
                    "PATH": "/usr/bin:/bin", "HOME": "/nonexistent",
                    "LANG": "C",
                }):
                    m.restore_stream(
                        [str(fake_docker), "--host=unix:///var/run/docker.sock"],
                        "g5-restore-1234567890abcdef", encrypted, PASSWORD,
                    )
            with patch.dict(os.environ, {"GNUPGHOME": str(root / "gnupg")}):
                with self.assertRaises(m.ArchiveBlocked) as err:
                    m.restore_stream([str(fake_docker)],
                                     "g5-restore-1234567890abcdef",
                                     encrypted, "W" * 40)
                self.assertEqual(str(err.exception), "GPG_DECRYPTION_FAILED")


    def test_restore_failure_categories_are_structural_and_never_echo_identifiers(self):
        examples = {
            "EXTENSION_UNAVAILABLE": (
                "pg_restore: error: could not execute query: ERROR: "
                "extension 'private_extension' is not available"
            ),
            "EXTENSION_LIBRARY_UNAVAILABLE": (
                "pg_restore: error: could not execute query: ERROR: "
                "could not access file '$libdir/private_library'"
            ),
            "ROLE_MISSING": (
                "pg_restore: error: could not execute query: ERROR: "
                "role 'customer_account' does not exist"
            ),
            "OBJECT_DEPENDENCY_MISSING": (
                "pg_restore: error: could not execute query: ERROR: "
                "function private_schema.private_function does not exist"
            ),
            "PERMISSION_DENIED": (
                "pg_restore: error: could not execute query: ERROR: "
                "permission denied for schema private_data"
            ),
            "OBJECT_CONFLICT": (
                "pg_restore: error: could not execute query: ERROR: "
                "relation 'private_table' already exists"
            ),
            "RESOURCE_LIMIT": (
                "pg_restore: error: could not execute query: ERROR: "
                "could not extend file private_file: No space left on device"
            ),
            "SERVER_SETTING_UNSUPPORTED": (
                "pg_restore: error: could not execute query: ERROR: "
                "unrecognized configuration parameter 'private_setting'"
            ),
            "ARCHIVE_INVALID": (
                "pg_restore: error: input file does not appear to be a valid archive"
            ),
            "SQL_SYNTAX_UNSUPPORTED": (
                "pg_restore: error: could not execute query: ERROR: "
                "syntax error at or near 'PRIVATE_STATEMENT'"
            ),
        }
        for category, message in examples.items():
            with self.subTest(category=category):
                result = m.classify_restore_stderr(message.encode("utf-8"))
                self.assertEqual(result, category)
                self.assertIn(result, m.RESTORE_FAILURE_CATEGORIES)
                self.assertNotIn("private", result.lower())
                self.assertNotIn("customer", result.lower())
        self.assertIsNone(m.classify_restore_stderr(
            b"pg_restore: error: Command was: SELECT 'private_password';"
        ))
        self.assertIsNone(m.classify_restore_stderr(
            b"pg_restore: context: COPY top_secret_table, line 3"
        ))
        self.assertEqual(m.IsolatedRestoreSQLFailure("INJECT_PRIVATE_VALUE").category,
                         "UNCLASSIFIED")

    def test_restore_failure_labels_are_bounded_and_no_raw_errors_persist(self):
        raw = io.BytesIO(
            b"pg_restore: error: could not execute query: ERROR: "
            b"extension 'PRIVATE_EXT' is not available\n"
            b"pg_restore: error: Command was: CREATE EXTENSION PRIVATE_EXT\n"
            b"pg_restore: error: ERROR: role PRIVATE_ROLE does not exist\n"
        )
        categories = []
        m.consume_restore_stderr(raw, categories)
        self.assertEqual(categories, ["EXTENSION_UNAVAILABLE"])
        self.assertNotIn("PRIVATE", repr(categories))
        self.assertEqual(str(m.IsolatedRestoreSQLFailure(categories[0])),
                         "ISOLATED_RESTORE_SQL_FAILED")

    def test_cli_emits_safe_sql_category_without_object_or_sql_content(self):
        import sys
        argv = ["g5_restore_isolated_rehearsal.py", "--restore",
                "--manifest", "/private/archive.json",
                "--source-project-ref", SOURCE]
        with patch.object(sys, "argv", argv):
            with patch.object(m, "validated_archive", return_value=Path("/encrypted.gpg")):
                with patch.object(m, "docker_executable", return_value=["/usr/bin/docker"]):
                    with patch.object(m, "image_id", return_value=IMAGE):
                        with patch.object(m.sys.stdin, "isatty", return_value=True):
                            with patch("builtins.input", return_value="RESTORE-G5-ISOLATED"):
                                with patch.object(m.getpass, "getpass", return_value=PASSWORD):
                                    with patch.object(m, "rehearsed_restore",
                                                      side_effect=m.IsolatedRestoreSQLFailure(
                                                          "ROLE_MISSING")):
                                        with contextlib.redirect_stdout(io.StringIO()) as output:
                                            self.assertEqual(m.main(), 2)
        content = output.getvalue()
        self.assertIn("G5_REHEARSAL_ERROR=ISOLATED_RESTORE_SQL_FAILED", content)
        self.assertIn("G5_RESTORE_FAILURE_CATEGORY=ROLE_MISSING", content)
        self.assertIn("G5_RESTORE_TEST=NOT_VERIFIED", content)
        self.assertNotIn("G5_RESTORE_TEST=PASS", content)
        self.assertNotIn(PASSWORD, content)
        self.assertNotIn("/encrypted.gpg", content)

    @unittest.skipUnless(os.name == "posix" and shutil.which("gpg"), "POSIX/GPG required")
    def test_actual_gpg_stream_fake_pg_restore_error_reports_only_category(self):
        """A simulated Docker failure is classified without leaking raw stderr."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            encrypted = root / "fake_captured.gpg"
            reader, writer = os.pipe()
            try:
                gpg = subprocess.Popen(
                    [shutil.which("gpg"), "--batch", "--no-tty",
                     "--pinentry-mode", "loopback", "--no-symkey-cache",
                     "--passphrase-fd", str(reader), "--symmetric",
                     "--output", str(encrypted)],
                    stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL, pass_fds=(reader,),
                )
                os.close(reader)
                reader = None
                os.write(writer, PASSWORD.encode("ascii") + b"\n")
                os.close(writer)
                writer = None
                gpg.communicate(b"PGDMP" + b"OFFLINE_SYNTHETIC_ONLY" * 12000,
                                timeout=30)
                self.assertEqual(gpg.returncode, 0)
            finally:
                for fd in (reader, writer):
                    if fd is not None:
                        os.close(fd)
            fake_docker = root / "fake-docker"
            fake_docker.write_text(
                "#!/bin/sh\n"
                "cat >/dev/null\n"
                "echo 'pg_restore: error: could not execute query: "
                "ERROR: extension SECRET_PRIVATE_EXT is not available' >&2\n"
                "echo 'pg_restore: error: Command was: "
                "CREATE EXTENSION SECRET_PRIVATE_EXT' >&2\n"
                "exit 1\n", encoding="ascii",
            )
            fake_docker.chmod(0o700)
            with patch.dict(os.environ, {"GNUPGHOME": str(root / "gnupg")}):
                (root / "gnupg").mkdir(mode=0o700)
                with contextlib.redirect_stdout(io.StringIO()) as captured:
                    with self.assertRaises(m.IsolatedRestoreSQLFailure) as error:
                        m.restore_stream(
                            [str(fake_docker), "--host=unix:///var/run/docker.sock"],
                            "g5-restore-1234567890abcdef", encrypted, PASSWORD,
                        )
            self.assertEqual(error.exception.category, "EXTENSION_UNAVAILABLE")
            self.assertEqual(str(error.exception), "ISOLATED_RESTORE_SQL_FAILED")
            self.assertEqual(captured.getvalue(), "")
            self.assertNotIn("SECRET_PRIVATE_EXT", repr(error.exception.__dict__))


    def test_supabase_images_require_allowlisted_ref_and_sha_fingerprint(self):
        docker = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]
        image_ref = "supabase/postgres:17.6.1.136"
        with patch.object(m, "docker_query", return_value=MagicMock(
                returncode=0, stdout=(IMAGE + "\n").encode())) as metadata:
            self.assertEqual(m.image_id(docker, image_ref), IMAGE)
            metadata.assert_called_once_with(
                docker, ["image", "inspect", "--format", "{{.Id}}", image_ref]
            )
        for malicious in (
            "postgres:latest", "supabase/postgres:15.9.1.1",
            "supabase/postgres:17.6.1.136;sh", "evilregistry/postgres:17",
            "supabase/postgres:17.6.1.136\n", "postgres:17 --privileged",
        ):
            with self.subTest(malicious=malicious):
                with patch.object(m, "docker_query") as called:
                    with self.assertRaises(m.ArchiveBlocked) as blocked:
                        m.image_id(docker, malicious)
                    self.assertEqual(str(blocked.exception),
                                     "ISOLATED_IMAGE_REF_INVALID")
                    called.assert_not_called()

    def test_probe_supabase_image_uid_is_rootless_from_image_not_hardcoded(self):
        prefix = ["/usr/bin/docker", "--host=unix:///var/run/docker.sock"]
        with patch.object(m, "docker_query", return_value=MagicMock(
                returncode=0, stdout=b"70\n71\n")) as query:
            self.assertEqual(m.supabase_image_user(prefix, IMAGE), "70:71")
            argv = query.call_args.args[1]
            for required in (
                "--network=none", "--pull=never", "--read-only",
                "--user=65534:65534", "--cap-drop=ALL",
                "--security-opt=no-new-privileges", "--entrypoint=/bin/sh", IMAGE,
            ):
                self.assertIn(required, argv)
            self.assertNotIn("--privileged", argv)
            self.assertNotIn("--mount", argv)
            self.assertNotIn("-v", argv)
            self.assertNotIn("-p", argv)
        for invalid in (
            b"0\n70\n", b"70\n0\n", b"not-a-number\n71\n",
            b"700000\n71\n", b"70\n71\nextra\n", b"",
        ):
            with self.subTest(payload=invalid):
                with patch.object(m, "docker_query", return_value=MagicMock(
                        returncode=0, stdout=invalid)):
                    with self.assertRaises(m.ArchiveBlocked):
                        m.supabase_image_user(prefix, IMAGE)

    def test_supabase_rootless_boot_uses_tmpfs_and_bypasses_dangerous_init(self):
        argv = m.isolated_run_args(
            IMAGE, "g5-restore-1234567890abcdef", runtime_user="70:71",
        )
        joined = " ".join(argv)
        for required in (
            "--network=none", "--read-only", "--user=70:71",
            "--cap-drop=ALL", "--security-opt=no-new-privileges",
            "--pull=never", "--rm", "--log-driver=none",
            "--entrypoint=/bin/sh", IMAGE, "initdb",
            "listen_addresses=", "unix_socket_directories=/var/run/postgresql",
            "--auth-local=trust", "--auth-host=reject",
        ):
            self.assertIn(required, joined)
        self.assertEqual(sum(x.startswith("--tmpfs=") for x in argv), 3)
        self.assertTrue(any("uid=70,gid=71" in x for x in argv))
        self.assertNotIn("docker-entrypoint.sh", joined)
        self.assertNotIn("migrations", joined)
        self.assertNotIn("POSTGRES_HOST_AUTH_METHOD=trust", joined)
        self.assertNotIn("POSTGRES_PASSWORD", joined)
        self.assertNotIn("DSN", joined)
        self.assertNotIn("--privileged", argv)
        self.assertNotIn("--publish", argv)
        for bad_uid in ("0:0", "700000:70", "70", "70:0", "root:70", "70:70;sh"):
            with self.subTest(runtime_uid=bad_uid):
                with self.assertRaises(m.ArchiveBlocked):
                    m.isolated_run_args(
                        IMAGE, "g5-restore-1234567890abcdef",
                        runtime_user=bad_uid,
                    )

    def test_supabase_inspect_requires_exact_sandbox_uid_and_no_network(self):
        def snapshot(user="70:71", network="none"):
            return {
                "Image": IMAGE,
                "HostConfig": {
                    "NetworkMode": network,
                    "ReadonlyRootfs": True,
                    "Privileged": False, "AutoRemove": True,
                    "UsernsMode": "", "PidMode": "",
                    "CapDrop": ["ALL"], "SecurityOpt": ["no-new-privileges"],
                    "Binds": None, "Devices": [], "PortBindings": {},
                },
                "Config": {
                    "User": user,
                    "Labels": {"agente-sql-langgraph.g5": "isolated-rehearsal"},
                },
                "Mounts": [
                    {"Type": "tmpfs", "Destination": "/var/lib/postgresql/data"},
                    {"Type": "tmpfs", "Destination": "/var/run/postgresql"},
                    {"Type": "tmpfs", "Destination": "/tmp"},
                ],
                "NetworkSettings": {"Ports": {"5432/tcp": None}},
            }
        with patch.object(m, "docker_query", return_value=MagicMock(
                returncode=0, stdout=json.dumps(snapshot()).encode())):
            self.assertIsNone(m.check_container_isolation(
                ["docker"], "g5-restore-1234567890abcdef", IMAGE,
                runtime_user="70:71",
            ))
        for bad in (snapshot(user="root"), snapshot(network="bridge")):
            with patch.object(m, "docker_query", return_value=MagicMock(
                    returncode=0, stdout=json.dumps(bad).encode())):
                with self.assertRaises(m.ArchiveBlocked):
                    m.check_container_isolation(
                        ["docker"], "g5-restore-1234567890abcdef", IMAGE,
                        runtime_user="70:71",
                    )

    def test_boot_only_never_uses_archive_password_gpg_or_restored_sql(self):
        response = MagicMock(returncode=0, stdout=b"postgres (PostgreSQL) 17.6\n")
        def docker_fake(prefix, args):
            return response
        with patch.object(m.os, "geteuid", return_value=0, create=True):
            with patch.object(m, "docker_query", side_effect=docker_fake):
                with patch.object(m, "check_container_isolation"):
                    with patch.object(m, "cleanup_container", return_value=True):
                        with patch.object(m, "restore_stream") as restoration:
                            with patch.object(m, "verify_restored_tables") as data:
                                self.assertEqual(m.rehearsed_restore(
                                    Path("/private/never_read.dump.gpg"), "", ["docker"],
                                    IMAGE, runtime_user="70:71", boot_only=True,
                                ), 0)
                                restoration.assert_not_called()
                                data.assert_not_called()

    def test_supabase_plan_does_not_run_container_or_request_backup_password(self):
        import sys
        argv = [
            "g5_restore_isolated_rehearsal", "--plan",
            "--manifest", "/private/fixture.manifest.json",
            "--source-project-ref", SOURCE,
            "--image-ref", "supabase/postgres:17.6.1.136",
            "--expected-image-sha", IMAGE,
        ]
        with patch.object(sys, "argv", argv):
            with patch.object(m, "validated_archive", return_value=Path("/fixture.gpg")):
                with patch.object(m, "docker_executable", return_value=["docker"]):
                    with patch.object(m, "image_id", return_value=IMAGE):
                        with patch.object(m, "supabase_image_user", return_value="70:71"):
                            with patch.object(m.getpass, "getpass") as secret:
                                with patch.object(m, "rehearsed_restore") as boot:
                                    with contextlib.redirect_stdout(io.StringIO()) as out:
                                        self.assertEqual(m.main(), 0)
                                    secret.assert_not_called()
                                    boot.assert_not_called()
                                    self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED",
                                                  out.getvalue())

    def test_new_image_requires_explicit_sha_before_even_boot_test(self):
        import sys
        argv = [
            "g5_restore_isolated_rehearsal", "--boot-test",
            "--manifest", "/private/fixture.manifest.json",
            "--source-project-ref", SOURCE,
            "--image-ref", "supabase/postgres:17.6.1.136",
        ]
        with patch.object(sys, "argv", argv):
            with patch.object(m, "validated_archive", return_value=Path("/fixture.gpg")):
                with patch.object(m, "docker_executable", return_value=["docker"]):
                    with patch.object(m, "image_id", return_value=IMAGE):
                        with patch.object(m, "supabase_image_user") as probe:
                            with patch.object(m, "rehearsed_restore") as boot:
                                with contextlib.redirect_stdout(io.StringIO()) as out:
                                    self.assertEqual(m.main(), 2)
                                probe.assert_not_called()
                                boot.assert_not_called()
                                self.assertIn("G5_REHEARSAL_ERROR=ISOLATED_IMAGE_SHA_NOT_ATTESTED",
                                              out.getvalue())
                                self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED",
                                              out.getvalue())

    def test_boot_test_only_starts_disposable_cluster_not_restore(self):
        import sys
        argv = [
            "g5_restore_isolated_rehearsal", "--boot-test",
            "--manifest", "/private/fixture.manifest.json",
            "--source-project-ref", SOURCE,
            "--image-ref", "supabase/postgres:17.6.1.136",
            "--expected-image-sha", IMAGE,
        ]
        with patch.object(sys, "argv", argv):
            with patch.object(m, "validated_archive", return_value=Path("/fixture.gpg")):
                with patch.object(m, "docker_executable", return_value=["docker"]):
                    with patch.object(m, "image_id", return_value=IMAGE):
                        with patch.object(m, "supabase_image_user", return_value="70:71"):
                            with patch.object(m, "rehearsed_restore", return_value=0) as boot:
                                with patch.object(m.getpass, "getpass") as password:
                                    with contextlib.redirect_stdout(io.StringIO()) as out:
                                        self.assertEqual(m.main(), 0)
                                password.assert_not_called()
                                self.assertIn("G5_BOOT_TEST=PASS", out.getvalue())
                                self.assertIn("G5_RESTORE_TEST=NOT_PERFORMED", out.getvalue())
                                boot.assert_called_once_with(
                                    Path("/fixture.gpg"), "", ["docker"], IMAGE,
                                    runtime_user="70:71", boot_only=True,
                                )

    def test_supabase_real_restore_requires_distinct_confirmation_token(self):
        import sys
        argv = [
            "g5_restore_isolated_rehearsal", "--restore",
            "--manifest", "/private/fixture.manifest.json",
            "--source-project-ref", SOURCE,
            "--image-ref", "supabase/postgres:17.6.1.136",
            "--expected-image-sha", IMAGE,
        ]
        with patch.object(sys, "argv", argv):
            with patch.object(m, "validated_archive", return_value=Path("/fixture.gpg")):
                with patch.object(m, "docker_executable", return_value=["docker"]):
                    with patch.object(m, "image_id", return_value=IMAGE):
                        with patch.object(m, "supabase_image_user", return_value="70:71"):
                            with patch.object(m.sys.stdin, "isatty", return_value=True):
                                with patch("builtins.input", return_value="RESTORE-G5-ISOLATED"):
                                    with patch.object(m.getpass, "getpass") as passphrase:
                                        with patch.object(m, "rehearsed_restore") as restore:
                                            with contextlib.redirect_stdout(io.StringIO()) as out:
                                                self.assertEqual(m.main(), 2)
                                            passphrase.assert_not_called()
                                            restore.assert_not_called()
                                            self.assertIn("ISOLATED_RESTORE_NOT_AUTHORIZED",
                                                          out.getvalue())
                                            self.assertIn("G5_RESTORE_TEST=NOT_VERIFIED",
                                                          out.getvalue())


if __name__ == "__main__":
    unittest.main()
