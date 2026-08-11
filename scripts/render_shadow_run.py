from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
GENERATED_DIR = ROOT / "docs" / "architecture" / "generated"
EXAMPLE_OUTPUTS = {
    "generate": GENERATED_DIR / "shadow-run-generate-example.mmd",
    "execute": GENERATED_DIR / "shadow-run-execute-example.mmd",
}

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.adapters.testing.shadow_run_visualization_fixtures import examples
from app.application.shadow_run_visualization_renderers import (
    render_mermaid,
    render_timeline,
)
from app.domain.shadow_evidence_types import ShadowRunRecord
from app.domain.shadow_run_visualization import (
    visualize_shadow_run,
)


def render_record(record: ShadowRunRecord, *, output_format: str) -> str:
    visualization = visualize_shadow_run(record)
    if output_format == "timeline":
        return render_timeline(visualization)
    if output_format == "mermaid":
        return render_mermaid(visualization)
    raise ValueError("unsupported output format")


def write_examples() -> None:
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for name, path in EXAMPLE_OUTPUTS.items():
        path.write_text(
            render_record(examples()[name], output_format="mermaid"),
            encoding="utf-8",
        )
        print(f"SHADOW_RUN_EXAMPLE_WRITTEN: {_display_path(path)}")


def check_examples() -> bool:
    ok = True
    for name, path in EXAMPLE_OUTPUTS.items():
        expected = render_record(examples()[name], output_format="mermaid")
        actual = path.read_text(encoding="utf-8")
        if _normalize(actual) != _normalize(expected):
            print(f"SHADOW_RUN_EXAMPLE_DRIFT: {_display_path(path)}")
            ok = False
        else:
            print(f"SHADOW_RUN_EXAMPLE_OK: {_display_path(path)}")
    return ok


def _load_input(path: Path) -> ShadowRunRecord:
    return json.loads(path.read_text(encoding="utf-8"))


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render a sanitized shadow evidence run visualization."
    )
    source = parser.add_mutually_exclusive_group(required=False)
    source.add_argument("--input", type=Path, help="ShadowRunRecord JSON file")
    source.add_argument(
        "--example",
        choices=sorted(EXAMPLE_OUTPUTS),
        help="synthetic built-in example",
    )
    parser.add_argument(
        "--format",
        choices=("mermaid", "timeline"),
        default="mermaid",
        help="output format",
    )
    parser.add_argument("--output", type=Path, help="write rendered output")
    parser.add_argument(
        "--write-examples",
        action="store_true",
        help="write deterministic versioned Mermaid examples",
    )
    parser.add_argument(
        "--check-examples",
        action="store_true",
        help="compare deterministic examples with versioned files",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    if args.write_examples:
        write_examples()
        return 0
    if args.check_examples:
        return 0 if check_examples() else 1

    if args.input is None and args.example is None:
        raise SystemExit("--input or --example is required")
    record = _load_input(args.input) if args.input else examples()[args.example]
    output = render_record(record, output_format=args.format)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(output, encoding="utf-8")
        print(f"SHADOW_RUN_RENDERED: {_display_path(args.output)}")
    else:
        print(output, end="")
    return 0


def _normalize(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


if __name__ == "__main__":
    raise SystemExit(main())
