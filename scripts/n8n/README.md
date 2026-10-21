# Isolated n8n -> LangGraph correlation and parallel Shadow

- \`shadow_correlation_manual_test.workflow.json\`: six-node, manual,
  intentionally empty-question test; never runs the model.
- \`parallel_langgraph_shadow_v1.workflow.json\`: separate, inactive
  webhook candidate for **real parallel requests**: Product/BFF -> n8n
  Shadow -> LangGraph -> persisted evidence. Requires an operator to
  provision credentials, network route and authorize activation. It
  does not change or clone the 68-node official workflow.
- \`PARALLEL-SHADOW-RUNBOOK.md\`: detailed deployment and test gates.
- \`testar_n8n_parallel_shadow_workflow.py\` at repository root tests
  the candidate offline without Gemini/SQL/cost.

Read \`PARALLEL-SHADOW-RUNBOOK.md\` before import or activation.
- `audit_parallel_shadow_bindings_readonly.sh` + `verify_parallel_shadow_bindings_export.py`: read-only inspection of the **imported inactive** seven-node candidate's credential references and structural integrity; prints only sanitized statuses, no credential values, no SQL/LLM.
