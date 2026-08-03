from __future__ import annotations

import contextlib
import io
import os
from pathlib import Path

import scripts.offline_watson_test_composition_check as runner


def _run():
    output = io.StringIO()
    with contextlib.redirect_stdout(output):
        code = runner.main()
    return code, output.getvalue()


def main() -> None:
    assert hasattr(runner, "main")
    text = Path("scripts/offline_watson_test_composition_check.py").read_text(encoding="utf-8")
    assert "__main__" in text

    before = dict(os.environ)
    code, output = _run()
    assert code == 0
    assert "offline_status=success" in output
    assert "secret_calls=2" in output
    assert "http_calls=4" in output
    assert "network=false" in output
    assert "test-token" not in output
    assert "test-api-key" not in output
    assert "Authorization" not in output
    assert "SELECT " not in output
    assert dict(os.environ) == before

    code2, output2 = _run()
    assert code2 == 0
    assert output == output2

    assert "IBM_CLOUD_API_KEY" in text
    assert "os.environ" not in text
    assert "StdlibHttpTransport" not in text
    assert "socket" not in text
    assert "curl" not in text
    print("testar_offline_watson_test_composition_check.py: 12/12 OK")


if __name__ == "__main__":
    main()
