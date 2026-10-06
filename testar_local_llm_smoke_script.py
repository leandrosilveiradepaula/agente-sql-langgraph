from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SCRIPT = ROOT / "scripts" / "smoke_local_llm_provider.py"


class LocalLlmSmokeScriptTests(unittest.TestCase):
    def test_network_smoke_is_disabled_by_default(self):
        env = os.environ.copy()
        env.pop("LOCAL_LLM_SMOKE_ENABLED", None)

        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("NO-GO: network smoke is disabled.", result.stdout)


if __name__ == "__main__":
    unittest.main()
