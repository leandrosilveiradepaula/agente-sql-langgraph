"""Offline coverage for rendering an inactive n8n Shadow workflow.

All URLs, IDs and model names in these tests are synthetic. Never accesses
the VPS, n8n, database, provider APIs, or the official financial workflow.
"""

from __future__ import annotations

import copy
import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

from scripts.n8n.render_parallel_shadow_workflow import (
    TEMPLATE,
    ShadowPreparationError,
    load_validated_template,
    render_private_candidate,
    validate_internal_base_url,
    write_private_candidate,
)


class N8nPrivateShadowRendererTests(unittest.TestCase):
    def test_template_is_inactive_and_does_not_embed_secrets_or_workflow_id(self):
        source = load_validated_template()
        self.assertIs(source["active"], False)
        self.assertNotIn("id", source)
        self.assertEqual(source["pinData"], {})
        self.assertFalse(any("credentials" in n for n in source["nodes"]))
        self.assertEqual(len(source["nodes"]), 7)

    def test_render_changes_only_two_structural_url_parameters(self):
        template_before = TEMPLATE.read_bytes()
        before = load_validated_template()
        rendered = render_private_candidate(
            "http://shadow-internal:8000/"
        )
        expected = copy.deepcopy(before)
        targets = {
            "Call LangGraph Shadow",
            "Read Correlated Evidence",
        }
        for n in expected["nodes"]:
            if n["name"] in targets:
                n["parameters"]["url"] = next(
                    m["parameters"]["url"] for m in rendered["nodes"]
                    if m["name"] == n["name"]
                )
        self.assertEqual(expected, rendered)
        self.assertEqual(template_before, TEMPLATE.read_bytes())
        self.assertFalse(rendered["active"])
        self.assertNotIn("id", rendered)
        text = json.dumps(rendered)
        self.assertNotIn("$env", text)
        self.assertNotIn("credentials", text)
        self.assertNotIn("api_key", text.lower())
        self.assertNotIn("http://shadow-internal:8000/", text)

    def test_rendered_javascript_urls_resolve_without_env_access(self):
        binary = shutil.which("node")
        if binary is None:
            self.skipTest("Node unavailable; separate n8n node tests require it")
        rendered = render_private_candidate(
            "http://shadow-internal:8000"
        )
        nodes = {n["name"]: n for n in rendered["nodes"]}
        expressions = [
            nodes["Call LangGraph Shadow"]["parameters"]["url"],
            nodes["Read Correlated Evidence"]["parameters"]["url"],
        ]
        script = r"""
const assert = require("node:assert/strict");
const data = JSON.parse(process.argv[1]);
const source = data.map(x => {
  assert.ok(x.startsWith("={{") && x.endsWith("}}"));
  assert.equal(x.includes("$env"), false);
  return new Function("$json", "return (" + x.slice(3, -2) + ");");
});
assert.equal(source[0]({
  target_path: "/v1/internal/sql-agent/generate"
}), "http://shadow-internal:8000/v1/internal/sql-agent/generate");
assert.equal(source[1]({agent_run_id: "agent:one/two"}),
  "http://shadow-internal:8000/v1/internal/agent-runs/agent%3Aone%2Ftwo/shadow-runs?limit=10");
console.log("PRIVATE_N8N_ENDPOINT_EXPRESSIONS=PASS");
"""
        completed = subprocess.run(
            [binary, "-e", script, json.dumps(expressions)],
            capture_output=True, text=True, timeout=15,
            encoding="utf-8", errors="replace",
        )
        self.assertEqual(completed.returncode, 0, completed.stderr[-1500:])
        self.assertIn("PRIVATE_N8N_ENDPOINT_EXPRESSIONS=PASS", completed.stdout)

    def test_accepts_only_private_network_endpoints(self):
        for url in [
            "http://shadow-internal:8000",
            "http://agente-sql-langgraph-shadow-test-langgraph-shadow-test-1:8000/",
            "http://10.3.9.21:8000",
            "http://172.19.0.12:8000",
            "http://192.168.1.100:8000",
            "https://shadow.agent.svc.cluster.local:8443",
            "http://[fd00::1234]:8000",
        ]:
            with self.subTest(url=url):
                self.assertEqual(validate_internal_base_url(url), url.rstrip("/"))
        for url in [
            "",
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://2130706433:8000",  # numeric loopback spelling
            "http://0x7f000001:8000",  # hex loopback spelling
            "http://169.254.169.254:80",
            "http://0.0.0.0:8000",
            "http://8.8.8.8:443",
            "https://example.com:8000",
            "http://shadow.internal:8000",  # internal FQDN not allowlisted by renderer
            "http://host.docker.internal:8000",
            "http://shadow-internal:99999",
            "http://shadow-internal:0",
            "http://shadow-internal:8000/v1",
            "http://shadow-internal:8000?token=sensitive",
            "http://shadow-internal:8000/#fragment",
            "http://admin:secret@shadow-internal:8000",
            "http://shadow-internal:8000\\evil",
            " http://shadow-internal:8000",
        ]:
            with self.subTest(url=url):
                with self.assertRaises(ShadowPreparationError):
                    validate_internal_base_url(url)

    def test_rejects_mutated_template(self):
        original = load_validated_template()
        for mutation in ("id", "active", "credentials", "url", "storage"):
            data = copy.deepcopy(original)
            if mutation == "id":
                data["id"] = "existing-workflow-id"
            elif mutation == "active":
                data["active"] = True
            elif mutation == "credentials":
                data["nodes"][0]["credentials"] = {"x": {"id": "secret"}}
            elif mutation == "url":
                next(n for n in data["nodes"] if n["name"] == "Call LangGraph Shadow")[
                    "parameters"
                ]["url"] = "http://untrusted.example/path"
            else:
                data["settings"]["saveDataSuccessExecution"] = "all"

            with tempfile.TemporaryDirectory() as tmp:
                path = pathlib.Path(tmp) / "bad.json"
                path.write_text(json.dumps(data), encoding="utf-8")
                with self.subTest(mutation=mutation):
                    with self.assertRaises(ShadowPreparationError):
                        load_validated_template(path)

    def test_output_new_file_only_and_private_permissions(self):
        rendered = render_private_candidate("http://shadow-internal:8000")
        with tempfile.TemporaryDirectory() as tmp:
            target = pathlib.Path(tmp) / "inactive-shadow.json"
            write_private_candidate(rendered, target)
            self.assertEqual(json.loads(target.read_text(encoding="utf-8")), rendered)
            if os.name != "nt":
                self.assertEqual(stat.S_IMODE(target.stat().st_mode), 0o600)
            with self.assertRaises(ShadowPreparationError):
                write_private_candidate(rendered, target)
            with self.assertRaises(ShadowPreparationError):
                write_private_candidate(rendered, pathlib.Path(tmp) / "bad.txt")

    def test_cli_checks_template_and_renders_without_secrets(self):
        tool = TEMPLATE.with_name("render_parallel_shadow_workflow.py")
        check = subprocess.run(
            [sys.executable, str(tool), "--check-template"],
            capture_output=True, text=True, timeout=15,
        )
        self.assertEqual(check.returncode, 0, check.stderr)
        self.assertIn("SHADOW_TEMPLATE=PASS", check.stdout)

        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / "shadow-only.json"
            run = subprocess.run(
                [
                    sys.executable, str(tool),
                    "--internal-base-url", "http://shadow-internal:8000",
                    "--output", str(out),
                ],
                capture_output=True, text=True, timeout=15,
            )
            self.assertEqual(run.returncode, 0, run.stderr)
            self.assertIn("SHADOW_RENDER=PASS", run.stdout)
            self.assertIn("N8N_WORKFLOW_IMPORTED=false", run.stdout)
            self.assertNotIn("shadow-internal:8000", run.stdout)
            self.assertFalse(json.loads(out.read_text(encoding="utf-8"))["active"])


if __name__ == "__main__":
    unittest.main()
