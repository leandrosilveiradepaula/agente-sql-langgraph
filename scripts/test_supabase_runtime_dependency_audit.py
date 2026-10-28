"""Pure offline coverage: no Docker, n8n, Supabase or Vercel contact."""
import importlib.util
from pathlib import Path
import unittest
from unittest.mock import patch

PATH = Path(__file__).resolve().parent / "operations" / "audit_supabase_runtime_dependencies_readonly.py"
SPEC = importlib.util.spec_from_file_location("runtime_dependency_audit", PATH)
module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(module)

SOURCE = "aaaaaaaaaaaaaaaaaaaa"
DEMO = "bbbbbbbbbbbbbbbbbbbb"
SCHEME = "postgresql" + "://"


class RuntimeDependencyTests(unittest.TestCase):
    def test_direct_project_source(self):
        dsn = SCHEME + "postgres:fake@db." + SOURCE + ".supabase.co:5432/postgres?sslmode=verify-full"
        self.assertEqual(module.classify_dsn(dsn, source=SOURCE, demo=DEMO), "SOURCE")

    def test_pooler_project_demo(self):
        dsn = (SCHEME + "postgres." + DEMO +
               ":fake@aws-0-sa-east-1.pooler.supabase.com:5432/postgres")
        self.assertEqual(module.classify_dsn(dsn, source=SOURCE, demo=DEMO), "DEMO")

    def test_connection_unsupported_or_private_proxy_not_assumed_clean(self):
        for dsn in (SCHEME + "postgres:fake@192.168.1.10:5432/postgres",
                    SCHEME + "postgres:fake@proxy.example.org:5432/postgres",
                    SCHEME + "postgres:fake@aws-0-sa-east-1.pooler.supabase.com:5432/postgres",
                    "sqlite:///a", "not-an-url", "", None):
            with self.subTest(dsn=bool(dsn)):
                self.assertEqual(
                    module.classify_dsn(dsn, source=SOURCE, demo=DEMO), "UNKNOWN"
                )

    def test_other_supabase_project_not_certified(self):
        ref = "cccccccccccccccccccc"
        dsn = SCHEME + "postgres:fake@db." + ref + ".supabase.co/postgres"
        self.assertEqual(
            module.classify_dsn(dsn, source=SOURCE, demo=DEMO),
            "OTHER_SUPABASE_UNVERIFIED",
        )

    def test_conflicting_identity_rejected(self):
        host = "db." + SOURCE + ".supabase.co"
        self.assertIsNone(module.project_for_host_user(host, "postgres." + DEMO))

    def test_pg_credential_classified_without_exposing_other_fields(self):
        data = {"host": "aws-0-sa-east-1.pooler.supabase.com",
                "user": "postgres." + SOURCE, "password": "dummy-do-not-print"}
        self.assertEqual(
            module.classify_pg_credential(data, source=SOURCE, demo=DEMO), "SOURCE"
        )

    def test_malformed_decrypted_credential_rejected(self):
        self.assertEqual(
            module.classify_pg_credential({"host": "proxy.local", "user": "postgres"},
                                          source=SOURCE, demo=DEMO),
            "UNKNOWN",
        )

    def test_workflow_extracts_unique_postgres_ids_only(self):
        wf = {"nodes": [
            {"credentials": {"postgres": {"id": "abc", "name": "metadata"}}},
            {"credentials": {"postgres": {"id": "abc"}}},
            {"credentials": {"postgres": {"id": "xyz"}}},
            {"credentials": {"httpHeaderAuth": {"id": "token-ignored"}}},
        ]}
        self.assertEqual(module.find_pg_credentials(wf), (4, ["abc", "xyz"]))

    def test_invalid_workflow_credentials_fail_closed(self):
        with self.assertRaises(module.AuditBlocked):
            module.find_pg_credentials({"nodes": [{"credentials": {"postgres": {"name": "no id"}}}]})

    def test_n8n_decrypted_export_is_forced_to_stdout_only(self):
        command = module.n8n_exec_prefix("n8n-sample")
        self.assertEqual(command[:4], ["docker", "exec", "-u", "node"])
        self.assertIn("N8N_LOG_OUTPUT=console", command)
        self.assertIn("N8N_LOG_LEVEL=info", command)
        self.assertEqual(command[-2:], ["n8n-sample", "n8n"])

    def test_n8n_version_drift_blocks_without_decrypted_export(self):
        with patch.object(module, "run_private_cli", return_value="2.5.0") as runner:
            with self.assertRaises(module.AuditBlocked):
                module.n8n_credentials_targets(
                    "n8n-sample", "wf1", source=SOURCE, demo=DEMO
                )
            self.assertEqual(runner.call_count, 1)

    def test_n8n_stdout_unambiguous(self):
        safe = '{"id":"abc","type":"postgres","data":{"host":"db.' + DEMO + '.supabase.co","user":"postgres"}}'
        self.assertEqual(
            module.parse_n8n_one("info\n[" + safe + "]", "abc", decrypted=True)["id"],
            "abc",
        )
        with self.assertRaises(module.AuditBlocked):
            module.parse_n8n_one("[" + safe + "]", "different", decrypted=True)

    def test_runtime_scan_does_not_probe_database(self):
        env = {
            "LANGGRAPH_SHADOW_DATABASE_DSN":
                SCHEME + "postgres:fake@db." + SOURCE + ".supabase.co/postgres",
            "CONTEXT_POSTGRES_DSN":
                SCHEME + "postgres." + DEMO +
                ":fake@aws-0-sa-east-1.pooler.supabase.com:5432/postgres",
            "LANGGRAPH_ALLOW_REAL_SQL_EXECUTION": "false",
        }
        with patch.object(module, "running_docker_environment", return_value=env):
            result = module.audit(
                source=SOURCE, demo=DEMO, shadow_container="shadow-local",
                n8n_container=None, workflow_id=None, inspect_n8n=False,
            )
        self.assertEqual(result["SHADOW_EVIDENCE_TARGET"], "SOURCE")
        self.assertEqual(result["SHADOW_CONTEXT_TARGET"], "DEMO")
        self.assertEqual(result["SHADOW_REAL_SQL_EXECUTION_DISABLED"], "PASS")
        self.assertEqual(result["N8N_OFFICIAL_CREDENTIAL_TARGET"], "NOT_AUDITED")

    def test_invalid_project_ref_blocks_before_docker_inspect(self):
        with patch.object(module, "running_docker_environment") as runner:
            with self.assertRaises(module.AuditBlocked):
                module.audit(
                    source="invalid", demo=DEMO, shadow_container="shadow",
                    n8n_container=None, workflow_id=None, inspect_n8n=False
                )
            runner.assert_not_called()

    def test_no_local_tty_disallows_decrypted_n8n_export(self):
        with patch.object(module, "running_docker_environment", return_value={}):
            with patch.object(module.sys.stdin, "isatty", return_value=False):
                with patch.object(module, "n8n_credentials_targets") as secret_reader:
                    with self.assertRaises(module.AuditBlocked):
                        module.audit(
                            source=SOURCE, demo=DEMO, shadow_container="shadow",
                            n8n_container="n8n-test", workflow_id="flow1",
                            inspect_n8n=True,
                        )
                    secret_reader.assert_not_called()

    def test_n8n_cli_errors_never_include_sensitive_stdout(self):
        import subprocess
        fake = subprocess.CompletedProcess(["safe"], 1, "password-like-value", "secret")
        with patch.object(module.subprocess, "run", return_value=fake):
            with self.assertRaises(module.AuditBlocked) as caught:
                module.run_private_cli(["no-network"])
            self.assertEqual(str(caught.exception), "PRIVATE_CLI_INVALID_RESULT")


if __name__ == "__main__":
    unittest.main()
