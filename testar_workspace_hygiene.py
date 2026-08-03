from __future__ import annotations

import tempfile
from pathlib import Path

import scripts.check_workspace_hygiene as hygiene


def main() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        (root / ".env").write_text("x", encoding="utf-8")
        (root / "secret-note.txt").write_text("x", encoding="utf-8")
        (root / "response_watson_raw.json").write_text("{}", encoding="utf-8")
        (root / "query.sql").write_text("SELECT 1", encoding="utf-8")
        (root / "cert.pem").write_text("fake", encoding="utf-8")
        findings = hygiene.inspect_workspace(root)
        categories = {item[1] for item in findings}
        assert "env_file" in categories
        assert "suspicious_name" in categories
        assert "watson_output" in categories
        assert "temporary_sql" in categories
        assert "forbidden_artifact" in categories
    assert hygiene.MAX_EXPECTED_FILE_BYTES > 0
    assert ".pfx" in hygiene.FORBIDDEN_SUFFIXES
    assert "api_key" in hygiene.SUSPICIOUS_NAME_MARKERS
    assert hygiene.inspect_workspace(Path(tempfile.mkdtemp())) == []
    print("testar_workspace_hygiene.py: 9/9 OK")


if __name__ == "__main__":
    main()
