from __future__ import annotations

from pathlib import Path


WORKFLOW = Path(".github/workflows/offline-validation.yml")


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")
    lowered = text.casefold()
    assert "pull_request:" in text
    assert "push:" in text and "master" in text
    assert "workflow_dispatch:" in text
    assert "windows-latest" in text
    assert "actions/setup-python" in text
    assert "permissions:" in text and "contents: read" in text
    assert ("${{ " + "secrets" + ".") not in lowered
    assert "--execute-live" not in text
    assert "manual_watson_flow_probe.py" not in text
    assert "continue-on-error" not in lowered
    assert "environment:" not in lowered and "environments:" not in lowered
    for checker in [
        "scripts/check_imports.py",
        "scripts/check_no_network.py",
        "scripts/check_all.py",
        "scripts/check_hardcodes.py",
        "scripts/check_secrets.py",
        "scripts/check_clean_room.py",
        "git diff --check",
    ]:
        assert checker in text
    assert "upload-artifact" not in lowered
    assert "IBM_CLOUD_API_KEY" not in text
    print("testar_offline_ci_contract.py: 15/15 OK")


if __name__ == "__main__":
    main()
