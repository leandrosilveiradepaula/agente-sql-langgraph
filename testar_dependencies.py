from __future__ import annotations

import tempfile
from pathlib import Path

import scripts.check_dependencies as deps


def main() -> None:
    parsed = deps.parse_requirements()
    assert "langgraph" in parsed
    assert "psycopg" in parsed
    with tempfile.TemporaryDirectory() as tmp:
        req = Path(tmp) / "requirements.txt"
        req.write_text("requests==1.0.0\n", encoding="utf-8")
        assert "requests" in deps.parse_requirements(req)
        req.write_text("pkg @ https://example.invalid/pkg.whl\n", encoding="utf-8")
        try:
            deps.parse_requirements(req)
        except ValueError:
            pass
        else:
            raise AssertionError("remote requirement aceito")
        mod = Path(tmp) / "module.py"
        mod.write_text("import os\nimport psycopg\nfrom app.bootstrap import x\n", encoding="utf-8")
        assert deps.external_imports([mod]) == {"psycopg"}
        mod.write_text("import requests\n", encoding="utf-8")
        assert "requests" in deps.external_imports([mod])
    assert "tenacity" in deps.FORBIDDEN_DEPENDENCIES
    assert "urllib3" in deps.FORBIDDEN_DEPENDENCIES
    assert deps.main() == 0
    print("testar_dependencies.py: 9/9 OK")


if __name__ == "__main__":
    main()
