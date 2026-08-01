from __future__ import annotations

import contextlib
import io
import tempfile
from pathlib import Path

import scripts.manual_watson_flow_probe as probe


def _run(args, env=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = probe.main(args, environ=env or {})
    return code, out.getvalue()


def main() -> None:
    code, output = _run([])
    assert code == probe.EXIT_OK and "dry-run" in output
    assert _run(["--execute-live"])[0] == probe.EXIT_USAGE
    assert _run(["--confirm-test-environment"])[0] == probe.EXIT_OK
    assert _run(["--execute-live", "--confirm-test-environment"])[0] == probe.EXIT_USAGE
    assert _run(["--sql-file", "missing.sql"])[0] == probe.EXIT_USAGE
    with tempfile.TemporaryDirectory() as tmp:
        huge = Path(tmp) / "huge.sql"
        huge.write_bytes(b"x" * 200_001)
        assert _run(["--sql-file", str(huge)])[0] == probe.EXIT_USAGE
        sql = Path(tmp) / "query.sql"
        sql.write_text("SELECT 1", encoding="utf-8")
        assert _run(["--execute-live", "--confirm-test-environment", "--sql-file", str(sql)])[0] == probe.EXIT_CONFIG
        env = {
            "WATSON_API_BASE_URL": "https://example.invalid",
            "WATSON_FLOW_ID": "00e0284a-d785-448b-aed3-95672dd4d189",
            "IBM_CLOUD_API_KEY": "test-secret",
        }
        code, output = _run(["--sql-file", str(sql)], env)
        assert code == probe.EXIT_OK
        assert "test-secret" not in output
        assert "Bearer" not in output
        assert "Authorization" not in output
        assert "SELECT 1" not in output
        assert "sql_sha256=" in output and "sql_bytes=8" in output
        assert "preview" not in output
        assert _run(["--show-rows"])[0] == probe.EXIT_USAGE
        code, output = _run(["--show-rows", "--confirm-show-rows"], env)
        assert code == probe.EXIT_OK
        assert "dry-run" in output
    assert probe.EXIT_OK == 0 and probe.EXIT_USAGE == 2
    assert hasattr(probe, "main")
    assert "__main__" in Path("scripts/manual_watson_flow_probe.py").read_text(encoding="utf-8")
    check_all = Path("scripts/check_all.py").read_text(encoding="utf-8")
    assert "testar_manual_watson_flow_probe.py" in check_all
    assert "scripts/manual_watson_flow_probe.py" not in check_all
    assert _run(["--execute-live", "--confirm-test-environment", "--sql-file", __file__], env={})[0] == probe.EXIT_CONFIG
    print("testar_manual_watson_flow_probe.py: 20/20 OK")


if __name__ == "__main__":
    main()
