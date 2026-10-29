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
    def test_execution_login_attestation_is_separate_from_project_classification(self):
        data = {
            "host": "aws-0-sa-east-1.pooler.supabase.com",
            "port": 5432, "database": "postgres",
            "user": "finance_reader." + DEMO,
            "ssl": "require", "allowUnauthorizedCerts": False,
        }
        self.assertEqual(module.classify_pg_credential(data, source=SOURCE, demo=DEMO), "DEMO")
        self.assertTrue(module.attests_n8n_execution_login(
            data, role="finance_reader", database="postgres", project=DEMO
        ))
        for changed in (
            {"user": "postgres." + DEMO},
            {"user": "finance_reader." + SOURCE},
            {"database": "other"},
            {"ssl": "disable"},
            {"sshTunnel": True},
            {"port": 2222},
            {"allowUnauthorizedCerts": True},
            {"connectionString": SCHEME + "postgres:fake@db." + DEMO + ".supabase.co/postgres"},
        ):
            with self.subTest(changed=list(changed)):
                self.assertFalse(module.attests_n8n_execution_login(
                    {**data, **changed}, role="finance_reader",
                    database="postgres", project=DEMO
                ))
        direct = dict(data, host="db." + DEMO + ".supabase.co", user="finance_reader")
        self.assertTrue(module.attests_n8n_execution_login(
            direct, role="finance_reader", database="postgres", project=DEMO
        ))
        self.assertFalse(module.attests_n8n_execution_login(
            dict(direct, user="postgres"), role="finance_reader", database="postgres", project=DEMO
        ))

    def test_execution_binding_ids_reject_invalid_or_other_node_bindings(self):
        flow = {"nodes": [
            {"id": "target-1", "name":"target-1", "type": "n8n-nodes-base.postgres",
             "credentials": {"postgres": {"id": "cred-a"}}},
            {"id": "target-2", "name":"target-2", "type": "n8n-nodes-base.postgres",
             "credentials": {"postgres": {"id": "cred-a"}}},
            {"id": "other", "name":"other", "type": "n8n-nodes-base.postgres",
             "credentials": {"postgres": {"id": "cred-b"}}},
        ]}
        self.assertEqual(module.execution_binding_credentials(
            flow, ("target-1", "target-2")
        ), ["cred-a"])
        for targets in (("target-1","missing"), ("target-1","target-1"), ("invalid;",)):
            with self.subTest(targets=targets):
                with self.assertRaises(module.AuditBlocked):
                    module.execution_binding_credentials(flow, targets)
        flow["nodes"][0]["type"] = "n8n-nodes-base.code"
        with self.assertRaises(module.AuditBlocked):
            module.execution_binding_credentials(flow, ("target-1","target-2"))

    def test_bound_reader_is_attested_even_with_unrelated_nonreader_credential(self):
        import json
        flow = {"id": "workflow-1", "connections": {"start": {"main": [[{"node": "target-1"}, {"node": "other"}]]}, "target-1": {"main": [[{"node": "target-2"}]]}}, "nodes": [
            {"id": "start", "name":"start", "type":"n8n-nodes-base.webhook"},
            {"id": "target-1", "type": "n8n-nodes-base.postgres",
             "credentials": {"postgres": {"id": "cred-a"}}},
            {"id": "target-2", "type": "n8n-nodes-base.postgres",
             "credentials": {"postgres": {"id": "cred-a"}}},
            {"id": "other", "type": "n8n-nodes-base.postgres",
             "credentials": {"postgres": {"id": "cred-b"}}},
        ]}
        good = {"host": "aws-0-sa-east-1.pooler.supabase.com", "port": 5432,
                "user": "finance_reader." + DEMO, "database": "postgres",
                "ssl": "require", "password": "never-display"}
        other = {**good, "user": "postgres." + DEMO}
        def output(cmd, **kwargs):
            if cmd[-1] == "--version":
                return "2.4.8"
            if "export:workflow" in cmd:
                return json.dumps([flow])
            if "export:credentials" in cmd:
                credential_id = cmd[-2].split("=", 1)[1]
                data = good if credential_id == "cred-a" else other
                return json.dumps([{"id": credential_id, "type": "postgres", "data": data}])
            raise AssertionError("unexpected command")
        with patch.object(module, "run_private_cli", side_effect=output):
            nodes, count, target, attested, reachable = module.n8n_credentials_targets(
                "n8n-test", "workflow-1", source=SOURCE, demo=DEMO,
                execution_role="finance_reader", database="postgres",
                binding_ids=("target-1","target-2")
            )
        self.assertEqual((nodes,count,target,attested),(4,2,"DEMO","PASS"))
        self.assertEqual(reachable["DEMO"],2)
        self.assertEqual(reachable["SOURCE"],0)
        good["user"] = "postgres." + DEMO
        with patch.object(module, "run_private_cli", side_effect=output):
            self.assertEqual(module.n8n_credentials_targets(
                "n8n-test", "workflow-1", source=SOURCE, demo=DEMO,
                execution_role="finance_reader", database="postgres",
                binding_ids=("target-1","target-2")
            )[3],"BLOCKED")

    def test_reachable_source_is_separate_from_demonstrated_execution_role(self):
        import json
        flow={"id":"wf", "nodes":[
            {"id":"trigger","name":"trigger","type":"n8n-nodes-base.webhook"},
            {"id":"main","name":"main","type":"n8n-nodes-base.postgres",
             "credentials":{"postgres":{"id":"demo-cred"}}},
            {"id":"legacy","name":"legacy","type":"n8n-nodes-base.postgres",
             "credentials":{"postgres":{"id":"source-cred"}}},
            {"id":"dead","name":"dead","type":"n8n-nodes-base.postgres",
             "credentials":{"postgres":{"id":"source-cred"}}},
        ],"connections":{"trigger":{"main":[[{"node":"main"},{"node":"legacy"}]]}}}
        assert module.reachable_postgres_binding_ids(flow)==["demo-cred","source-cred"]
        def cli(cmd, **kw):
            if cmd[-1]=="--version":return "2.4.8"
            if "export:workflow" in cmd:return json.dumps([flow])
            cid=cmd[-2].split("=",1)[1]
            user=("finance_reader."+DEMO if cid=="demo-cred" else "postgres."+SOURCE)
            return json.dumps([{"id":cid,"type":"postgres","data":{
                "host":"aws-0-sa-east-1.pooler.supabase.com","port":5432,
                "user":user,"database":"postgres","ssl":"require"}}])
        with patch.object(module,"run_private_cli",side_effect=cli):
            nodes, creds, aggregate, login, reachable = module.n8n_credentials_targets(
                "n8n-test","wf",source=SOURCE,demo=DEMO,
                execution_role="finance_reader",database="postgres",binding_ids=("main",))
        self.assertEqual((nodes,creds,aggregate,login),(4,2,"SOURCE","PASS"))
        self.assertEqual(reachable["SOURCE"],1)
        self.assertEqual(reachable["DEMO"],1)

    def test_expected_execution_login_requires_local_tty_audit(self):
        with patch.object(module, "running_docker_environment") as runner:
            with self.assertRaises(module.AuditBlocked):
                module.audit(source=SOURCE,demo=DEMO,
                    shadow_container="shadow-local",n8n_container="n8n-local",
                    workflow_id="workflow-1",inspect_n8n=False,
                    execution_role="finance_reader",database="postgres",
                    binding_ids=("target-1",))
            runner.assert_not_called()

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

    def test_n8n_registry_qualified_image_is_detected(self):
        output = (
            "shadow-test myorg/langgraph-shadow:1.0\n"
            "n8n-main docker.n8n.io/n8nio/n8n:2.4.8\n"
            "postgres postgres:17\n"
        )
        self.assertEqual(module.parse_single_n8n_container(output), "n8n-main")

    def test_n8n_bare_image_is_detected(self):
        for image in ("n8nio/n8n:2.4.8", "n8n:2.4.8",
                      "registry.example.org/n8nio/n8n@sha256:abc"):
            with self.subTest(image=image):
                self.assertEqual(
                    module.parse_single_n8n_container("server " + image),
                    "server",
                )

    def test_n8n_ambiguous_or_missing_blocks(self):
        for output in (
            "server-a docker.n8n.io/n8nio/n8n:2.4.8\n"
            "server-b n8nio/n8n:2.4.8\n",
            "sidecar registry.example.org/notn8n:1\n",
            "invalid-line-without-image\n",
        ):
            with self.subTest(output=output):
                with self.assertRaises(module.AuditBlocked) as caught:
                    module.parse_single_n8n_container(output)
                self.assertEqual(
                    str(caught.exception), "N8N_CONTAINER_MISSING_OR_AMBIGUOUS"
                )

    def test_n8n_detection_uses_existing_reviewed_docker_format(self):
        sample = "n8n-primary docker.n8n.io/n8nio/n8n:2.4.8\n"
        with patch.object(module, "run_private_cli", return_value=sample) as runner:
            self.assertEqual(module.find_n8n_container(), "n8n-primary")
            runner.assert_called_once_with(
                ["docker", "ps", "--format", "{{.Names}} {{.Image}}"],
                timeout=20,
            )

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
