from __future__ import annotations

import contextlib
import io

import scripts.offline_watson_failure_rehearsal as rehearsal


def main() -> None:
    items = rehearsal.scenarios()
    assert len(items) == 36
    names = {item.name for item in items}
    assert "IAM missing secret" in names
    assert "Flow 429 Retry-After valid" in names
    assert "execution failure no repair" in names
    assert "preflight failure blocks execution" in names
    assert "rate limit no retry" in names
    assert "timeout no retry" in names
    assert "no compact transport crosses" in names
    assert all(rehearsal._passed(item) for item in items)
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        assert rehearsal.main() == 0
    output = out.getvalue()
    assert "FAILURE_REHEARSAL_OK" in output
    for marker in rehearsal.FORBIDDEN_OUTPUT:
        assert marker not in output
    print("testar_offline_watson_failure_rehearsal.py: 11/11 OK")


if __name__ == "__main__":
    main()
