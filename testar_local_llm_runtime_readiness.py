from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "check_local_llm_runtime.py"


class LocalLlmRuntimeReadinessTests(unittest.TestCase):
    def _run(self, env: dict[str, str]):
        clean = os.environ.copy()
        clean.update(env)
        return subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            env=clean,
            text=True,
            capture_output=True,
            check=False,
        )

    def test_disabled_provider_is_no_go(self):
        result = self._run({
            "OPENAI_COMPATIBLE_SQL_ENABLED": "false",
        })
        self.assertEqual(result.returncode, 1)
        self.assertIn("NO-GO: local LLM provider is disabled.", result.stdout)

    def test_incomplete_enabled_provider_is_no_go(self):
        result = self._run({
            "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
            "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
            "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
            "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
            "OPENAI_COMPATIBLE_SQL_BASE_URL": "",
        })
        self.assertEqual(result.returncode, 2)
        self.assertIn("NO-GO: local LLM configuration is invalid or incomplete.", result.stdout)

    def test_complete_provider_is_go_without_network_call(self):
        result = self._run({
            "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
            "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
            "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
            "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
            "OPENAI_COMPATIBLE_SQL_BASE_URL": "https://llm.example.test",
        })
        self.assertEqual(result.returncode, 0)
        self.assertIn("GO: local LLM runtime configuration is complete.", result.stdout)
        self.assertIn("network_call_performed=false", result.stdout)
        self.assertNotIn("https://llm.example.test", result.stdout)


if __name__ == "__main__":
    unittest.main()
