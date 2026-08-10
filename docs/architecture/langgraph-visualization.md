# LangGraph Visualization

## Generated From LangGraph

The versioned graph is generated from the real compiled `StateGraph` built by
`app.graph.builder.create_graph`. The renderer constructs the graph with local
testing adapters only, compiles it, and calls
`compiled_graph.get_graph().draw_mermaid()`. It does not hardcode nodes or
edges, does not execute graph nodes, and does not call external services.

Versioned Mermaid source:

- `docs/architecture/generated/langgraph-graph.mmd`

Regenerate it with:

```powershell
.\.venv\Scripts\python.exe scripts\render_langgraph_graph.py
```

Check it for drift with:

```powershell
.\.venv\Scripts\python.exe scripts\render_langgraph_graph.py --check
.\.venv\Scripts\python.exe testar_langgraph_graph_visualization.py
```

## Full Graph Lifecycle

The generated Mermaid file represents the full compiled graph lifecycle:

```text
receive_question -> load_context -> classify_intent -> build_plan
-> generate_sql -> security_gate -> contract_gate -> engine_preflight
-> execute_sql -> normalize_result -> serialize_result
-> build_run_record -> persist_run -> record_audit
-> emit_observability -> build_application_response
```

The graph also includes terminal paths through `finalize_invalid_request`,
`finalize_infrastructure_error`, and direct completion into
`build_run_record`.

The repair loop appears in the real graph as:

```text
engine_preflight -> repair_sql -> security_gate -> contract_gate
-> engine_preflight
```

That loop is structural. A repaired SQL proposal is not the same artifact as
the SQL originally approved by a human.

## Entrypoint Differences

`GenerateSqlUseCase` and `ExecuteApprovedSqlShadowUseCase` reuse real graph
nodes directly. They do not invoke the full compiled graph object today.

`GenerateSqlUseCase` runs the question, context, intent, plan, generation,
gate, preflight, and repair sequence needed to compare LangGraph shadow output
with the official n8n path.

`ExecuteApprovedSqlShadowUseCase` starts from an already approved SQL and runs
the security, contract, preflight, and repair proposal path. If repair is
needed, the repaired SQL is evidence/proposal only and requires a new human
approval before any future execution.

The full graph contains execution nodes (`execute_sql`, `normalize_result`,
`serialize_result`) for the application lifecycle. In the current shadow TEST
runtime, SQL execution is blocked from real execution: preflight is offline,
shadow does not execute real SQL, and user-facing behavior remains owned by
n8n.

## Architecture Diagram

This diagram is manual and architectural. It is not generated from LangGraph.

```mermaid
flowchart LR
    browser[Browser]
    bff[Next.js BFF]
    n8n[n8n official orchestration]
    after[after() async dispatch]
    shadow[LangGraph shadow API]
    persistence[Shadow evidence persistence]

    browser --> bff
    bff --> n8n
    n8n --> bff
    bff --> after
    after --> shadow
    shadow --> persistence
```

The n8n path remains official. Shadow runs are asynchronous, offline at first,
non-blocking, and do not impact the user response if they fail.

## LangSmith And Studio Compatibility

The current implementation is compatible with local structural visualization
through LangGraph's compiled graph API. LangSmith tracing or LangGraph Studio
were not added in this step.

Future Studio or LangSmith use would require explicit operator approval for
the corresponding configuration, runtime command, tracing settings, and any
required credentials. None of those are present in this microstep.
