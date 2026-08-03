from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

import scripts.check_clean_room as clean


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(os.environ)
        env.update(
            {
                "IBM_CLOUD_API_KEY": "fake",
                "WATSON_API_BASE_URL": "https://example.invalid",
                "WATSON_FLOW_ID": "fake",
                "HTTP_PROXY": "http://proxy.invalid",
                "https_proxy": "http://proxy.invalid",
            }
        )
        original = os.environ
        os.environ.clear()
        os.environ.update(env)
        try:
            sanitized = clean.clean_environment(Path(tmp))
        finally:
            os.environ.clear()
            os.environ.update(original)
        assert "IBM_CLOUD_API_KEY" not in sanitized
        assert "WATSON_API_BASE_URL" not in sanitized
        assert "HTTP_PROXY" not in sanitized
        assert "https_proxy" not in sanitized
        assert sanitized["PYTHONUTF8"] == "1"
        assert sanitized["PYTHONDONTWRITEBYTECODE"] == "1"
        assert sanitized["SQL_AGENT_DISABLE_NETWORK"] == "1"
        assert sanitized["SQL_AGENT_CLEAN_ROOM"] == "1"
        assert all("pip" not in " ".join(command) for _name, command in clean.STEPS)
        assert all("pull" not in " ".join(command) for _name, command in clean.STEPS)
        assert clean.run_step("tiny", [sys.executable, "-c", "print('ok')"], sanitized) == 0
        assert clean.run_step("failure", [sys.executable, "-c", "raise SystemExit(7)"], sanitized) == 7
        assert "check_clean_room.py" not in repr(clean.STEPS)
    print("testar_clean_room.py: 12/12 OK")


if __name__ == "__main__":
    main()
