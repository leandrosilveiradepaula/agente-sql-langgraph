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
                "TEST_SECRET_KEY": "fake",
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
        assert sanitized["TEST_SECRET_KEY"] == "fake"
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
    print("testar_clean_room.py: 11/11 OK")


if __name__ == "__main__":
    main()
