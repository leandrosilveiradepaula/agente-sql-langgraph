from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

file = Path(__file__).parent / "scripts" / "n8n" / "official_sql_infodive_provider_candidate.py"
spec = importlib.util.spec_from_file_location("provider_candidate", file)
m = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(m)


def sample():
    def http(name, node_id):
        return {"id": node_id, "name": name, "type": "n8n-nodes-base.httpRequest",
                "parameters": {
                    "method": "POST",
                    "url": "https://generativelanguage.googleapis.com/v1beta/models/model:generateContent",
                    "sendQuery": True,
                    "queryParameters": {"parameters": [{"name": "key", "value": "demo-secret-not-for-logs"}]},
                    "sendBody": True, "specifyBody": "json",
                    "jsonBody": "={{ $json.body }}",
                }, "retryOnFail": True}
    return {
        "id": "workflow-a", "name": "Test", "active": True,
        "settings": {"executionOrder": "v1"},
        "nodes": [
            {"id": "start", "name": "Trigger", "type": "n8n-nodes-base.webhook",
             "parameters": {}},
            http("Generate", "generate-http"),
            {"id": "generate-code", "name": "Parse Generate", "type": "n8n-nodes-base.code",
             "parameters": {"jsCode": "const sqlBruto = respostaGemini.candidates?.[0]?.content?.parts?.[0]?.text || null;"}},
            http("Repair", "repair-http"),
            {"id": "repair-code", "name": "Parse Repair", "type": "n8n-nodes-base.code",
             "parameters": {"jsCode": "const raw = obj.candidates?.[0]?.content?.parts?.[0]?.text || null;"}}
        ],
        "connections": {
            "Generate": {"main": [[{"node": "Parse Generate", "type": "main", "index": 0}]]},
            "Repair": {"main": [[{"node": "Parse Repair", "type": "main", "index": 0}]]},
        },
    }


def configuration():
    return {
        "url": "https://llm.example.test/api/chat/completions",
        "model": "private-model",
        "max_tokens": 4096,
        "credential_type": "httpBearerAuth",
        "credential_id": "cred-a",
        "credential_name": "Private Provider Credential",
    }


class TestOfficialProviderCandidate(unittest.TestCase):
    def test_contracts_and_invariants(self):
        before = sample()
        after, report = m.prepare_candidate(before, "workflow-a", configuration())
        self.assertEqual(report["changed_nodes"], 4)
        self.assertEqual(report["llm_calls"], 0)
        self.assertFalse(report["financial_sql_executed"])
        self.assertFalse(report["published_attested"])
        self.assertEqual(after["connections"], before["connections"])
        self.assertEqual(after["settings"], before["settings"])
        self.assertEqual(after["nodes"][0], before["nodes"][0])
        self.assertEqual(before, sample())
        for index in (1, 3):
            node = after["nodes"][index]
            self.assertEqual(node["parameters"]["url"], configuration()["url"])
            self.assertFalse(node["parameters"]["sendQuery"])
            self.assertEqual(node["parameters"]["authentication"], "genericCredentialType")
            self.assertEqual(node["parameters"]["genericAuthType"], "httpBearerAuth")
            self.assertEqual(node["credentials"]["httpBearerAuth"]["id"], "cred-a")
            self.assertTrue(node["retryOnFail"])
            self.assertIn("$json.body.contents[0].parts[0].text", node["parameters"]["jsonBody"])
            self.assertNotIn("demo-secret-not-for-logs", repr(node))
        self.assertIn(".choices?.[0]?.message?.content", after["nodes"][2]["parameters"]["jsCode"])
        self.assertIn(".choices?.[0]?.message?.content", after["nodes"][4]["parameters"]["jsCode"])
        self.assertNotIn("demo-secret-not-for-logs", repr(report))

    def test_rejects_missing_or_duplicated_source(self):
        workflow = sample()
        workflow["nodes"][1]["parameters"]["url"] = "https://provider.other/api"
        with self.assertRaises(m.Blocked):
            m.prepare_candidate(workflow, "workflow-a", configuration())
        workflow = sample()
        workflow["nodes"][1]["id"] = workflow["nodes"][3]["id"]
        with self.assertRaises(m.Blocked):
            m.discover_pairs(workflow, "workflow-a")

    def test_rejects_contract_and_link_drift(self):
        workflow = sample()
        workflow["nodes"][1]["parameters"]["jsonBody"] = "={{ $json }}"
        with self.assertRaises(m.Blocked):
            m.prepare_candidate(workflow, "workflow-a", configuration())
        workflow = sample()
        workflow["connections"]["Generate"]["main"] = []
        with self.assertRaises(m.Blocked):
            m.prepare_candidate(workflow, "workflow-a", configuration())
        workflow = sample()
        workflow["nodes"][2]["parameters"]["jsCode"] = "return 1"
        with self.assertRaises(m.Blocked):
            m.prepare_candidate(workflow, "workflow-a", configuration())

    def test_rejects_credential_query_and_client_specific_hardcode(self):
        config = configuration()
        config["url"] = "http://8.8.8.8/api/chat/completions"
        with self.assertRaises(m.Blocked):
            m.prepare_candidate(sample(), "workflow-a", config)
        config = configuration()
        config["url"] = "https://host.test/api/chat/completions?key=abc"
        with self.assertRaises(m.Blocked):
            m.prepare_candidate(sample(), "workflow-a", config)
        for forbidden in ("rivatti", "demo_lakehouse", "grupo_horizonte", "golden_answer"):
            self.assertNotIn(forbidden, file.read_text().lower())

    def test_private_http_and_header_auth(self):
        config = configuration()
        config["url"] = "http://10.0.0.4:8080/api/chat/completions"
        config["host"] = "chat.internal"
        config["credential_type"] = "httpHeaderAuth"
        candidate, report = m.prepare_candidate(sample(), "workflow-a", config)
        self.assertEqual(candidate["nodes"][1]["parameters"]["genericAuthType"], "httpHeaderAuth")
        self.assertEqual(candidate["nodes"][1]["credentials"]["httpHeaderAuth"]["id"], "cred-a")
        self.assertEqual(candidate["nodes"][1]["parameters"]["headerParameters"]["parameters"][1]["value"], "chat.internal")
        self.assertEqual(report["changed_nodes"], 4)


if __name__ == "__main__":
    unittest.main()
