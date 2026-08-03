from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    failures: list[tuple[str, str]] = []
    for path in sorted((ROOT / "app").rglob("*.py")):
        relative = path.relative_to(ROOT).as_posix()
        try:
            source = path.read_text(encoding="utf-8")
            compile(source, relative, "exec")
        except SyntaxError as exc:
            failures.append((relative, f"{exc.msg} at line {exc.lineno}"))
        except UnicodeDecodeError as exc:
            failures.append((relative, f"encoding error: {exc.reason}"))
    if failures:
        print("COMPILE_CHECK_FAILED")
        for relative, reason in failures:
            print(f"- {relative}: {reason}")
        return 1
    print("COMPILE_CHECK_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
