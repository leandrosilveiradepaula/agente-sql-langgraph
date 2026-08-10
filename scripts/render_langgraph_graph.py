from __future__ import annotations

import argparse
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs" / "architecture" / "generated" / "langgraph-graph.mmd"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.adapters.testing.fake_audit_sink import FakeAuditSink
from app.adapters.testing.fake_context_repository import FakeContextRepository
from app.adapters.testing.fake_engine_preflight import FakeEnginePreflight
from app.adapters.testing.fake_observability_sink import FakeObservabilitySink
from app.adapters.testing.fake_run_repository import FakeRunRepository
from app.adapters.testing.fake_sql_executor import FakeSqlExecutor
from app.adapters.testing.fake_sql_generator import FakeSqlGenerator
from app.adapters.testing.fake_sql_repairer import FakeSqlRepairer
from app.graph.builder import create_graph


def render_mermaid() -> str:
    """
    Renderiza a topologia real do StateGraph compilado.
    """

    graph = create_graph(
        FakeContextRepository(),
        FakeSqlGenerator(),
        FakeEnginePreflight(),
        FakeSqlRepairer(),
        FakeSqlExecutor(),
        FakeRunRepository(),
        FakeAuditSink(),
        FakeObservabilitySink(),
    )
    graph_api = getattr(graph, "get_graph", None)
    if not callable(graph_api):
        raise RuntimeError("compiled graph does not expose get_graph")
    drawable = graph_api()
    draw_mermaid = getattr(drawable, "draw_mermaid", None)
    if not callable(draw_mermaid):
        raise RuntimeError("compiled graph does not expose draw_mermaid")
    return _normalize_mermaid(str(draw_mermaid()))


def write_mermaid(path: Path = OUTPUT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(render_mermaid(), encoding="utf-8")


def check_mermaid(path: Path = OUTPUT) -> bool:
    expected = render_mermaid()
    actual = _normalize_mermaid(path.read_text(encoding="utf-8"))
    if actual != expected:
        print(f"MERMAID_DRIFT: regenerate {_display_path(path)}")
        return False
    print(f"MERMAID_OK: {_display_path(path)}")
    return True


def _normalize_mermaid(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").strip() + "\n"


def _display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def _parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Render the real LangGraph StateGraph as Mermaid."
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="compare generated Mermaid with the versioned file",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=OUTPUT,
        help="Mermaid output path",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(list(argv or sys.argv[1:]))
    if args.check:
        return 0 if check_mermaid(args.output) else 1
    write_mermaid(args.output)
    print(f"MERMAID_WRITTEN: {_display_path(args.output)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
