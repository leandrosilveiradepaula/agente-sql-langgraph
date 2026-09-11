from pathlib import Path


def replace_once(path: str, old: str, new: str) -> None:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if text.count(old) != 1:
        raise RuntimeError(f"anchor count for {path}: {text.count(old)}")
    p.write_text(text.replace(old, new, 1), encoding="utf-8")


replace_once(
    "app/domain/planning.py",
    'PLANNER_VERSION = "v1.1.0-planned-filter-contract"',
    'PLANNER_VERSION = "v1.2.0-planned-filter-generation"',
)
replace_once(
    "app/domain/planning.py",
    '''class ProjectedPlannedFilter(TypedDict, total=False):\n    filter_ref: str\n    filter_concept: str\n    binding_ref: str\n    required: bool\n    scope: str\n    detection_source: str\n    mapping_source: str\n    matched_user_term: str\n    provenance: dict[str, Any]\n\n\nclass ProjectionDiagnostic''',
    '''class ProjectedPlannedFilter(TypedDict, total=False):\n    filter_ref: str\n    filter_concept: str\n    binding_ref: str\n    required: bool\n    scope: str\n    detection_source: str\n    mapping_source: str\n    matched_user_term: str\n    provenance: dict[str, Any]\n\n\nclass ProjectedFilterBinding(TypedDict, total=False):\n    binding_ref: str\n    filter_concept: str\n    target_table: str\n    target_column: str\n    operator: str\n    value: Any\n    join_path: list[dict[str, Any]]\n    required: bool\n    scope: str\n\n\nclass ProjectionDiagnostic''',
)
replace_once(
    "app/domain/planning.py",
    '''    planned_metrics: list[ProjectedPlannedMetric]\n    planned_filters: list[ProjectedPlannedFilter]\n    allowed_schemas: list[str]''',
    '''    planned_metrics: list[ProjectedPlannedMetric]\n    planned_filters: list[ProjectedPlannedFilter]\n    resolved_filter_bindings: list[ProjectedFilterBinding]\n    allowed_schemas: list[str]''',
)

replace_once(
    "app/domain/planner.py",
    '''    ProjectedPlannedFilter,\n    ProjectedPlannedMetric,''',
    '''    ProjectedPlannedFilter,\n    ProjectedFilterBinding,\n    ProjectedPlannedMetric,''',
)
replace_once(
    "app/domain/planner.py",
    '''    planned_filters, planned_filter_diagnostic = _detect_planned_filters(\n        context=context,\n        intent_resolution_result=intent_resolution_result,\n    )\n    operation_projection, metric_binding_diagnostic = (''',
    '''    planned_filters, planned_filter_diagnostic = _detect_planned_filters(\n        context=context,\n        intent_resolution_result=intent_resolution_result,\n    )\n    resolved_filter_bindings = _project_resolved_filter_bindings(\n        entities=context.get("entities", []),\n        planned_filters=planned_filters,\n    )\n    operation_projection, metric_binding_diagnostic = (''',
)
replace_once(
    "app/domain/planner.py",
    '''        "planned_metrics": planned_metrics,\n        "planned_filters": planned_filters,\n        "allowed_schemas": list(context.get("allowed_schemas", [])),''',
    '''        "planned_metrics": planned_metrics,\n        "planned_filters": planned_filters,\n        "resolved_filter_bindings": resolved_filter_bindings,\n        "allowed_schemas": list(context.get("allowed_schemas", [])),''',
)
replace_once(
    "app/domain/planner.py",
    '''def _non_empty_text(value: Any) -> str | None:\n''',
    '''def _project_resolved_filter_bindings(\n    *,\n    entities: Any,\n    planned_filters: list[ProjectedPlannedFilter],\n) -> list[ProjectedFilterBinding]:\n    if not isinstance(entities, list):\n        return []\n    referenced = {\n        str(item.get("binding_ref", "")).strip().casefold(): item\n        for item in planned_filters\n        if isinstance(item, Mapping)\n        and isinstance(item.get("binding_ref"), str)\n        and item["binding_ref"].strip()\n    }\n    candidates: dict[str, list[ProjectedFilterBinding]] = {\n        key: [] for key in referenced\n    }\n    for entity in entities:\n        if not isinstance(entity, Mapping) or str(\n            entity.get("entity_type", "")\n        ).casefold() != "filter_binding":\n            continue\n        rule = entity.get("business_rule")\n        raw = rule.get("filter_binding") if isinstance(rule, Mapping) else None\n        if not isinstance(raw, Mapping):\n            continue\n        binding_ref = _non_empty_text(raw.get("binding_ref"))\n        if binding_ref is None or binding_ref.casefold() not in referenced:\n            continue\n        filter_concept = _non_empty_text(raw.get("filter_concept"))\n        target_table = _non_empty_text(raw.get("target_table"))\n        target_column = _non_empty_text(raw.get("target_column"))\n        operator = _non_empty_text(raw.get("operator"))\n        scope = _non_empty_text(raw.get("scope"))\n        required = raw.get("required")\n        value = raw.get("value")\n        join_path = raw.get("join_path")\n        if not (\n            filter_concept\n            and target_table\n            and target_column\n            and operator\n            and scope\n            and isinstance(required, bool)\n            and _is_filled_json_value(value)\n            and _is_valid_join_path(join_path)\n        ):\n            continue\n        planned = referenced[binding_ref.casefold()]\n        if not (\n            _same_text(planned.get("filter_concept"), filter_concept)\n            and _same_text(planned.get("scope"), scope)\n            and planned.get("required") is required\n        ):\n            continue\n        candidates[binding_ref.casefold()].append(\n            {\n                "binding_ref": binding_ref,\n                "filter_concept": filter_concept,\n                "target_table": target_table,\n                "target_column": target_column,\n                "operator": operator,\n                "value": deepcopy(value),\n                "join_path": deepcopy(join_path),\n                "required": required,\n                "scope": scope,\n            }\n        )\n    output: list[ProjectedFilterBinding] = []\n    for key in sorted(candidates):\n        if len(candidates[key]) == 1:\n            output.append(candidates[key][0])\n    return output\n\n\ndef _non_empty_text(value: Any) -> str | None:\n''',
)

replace_once(
    "app/domain/sql_generation.py",
    '''import hashlib\nimport json\n''',
    '''import hashlib\nimport json\nimport math\n''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''SQL_GENERATION_CONTRACT_VERSION = (\n    "v1.0.0-query-plan-sql-generation"\n)''',
    '''SQL_GENERATION_CONTRACT_VERSION = (\n    "v1.1.0-planned-filter-generation"\n)''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''class SqlGenerationContext(TypedDict):\n''',
    '''class PlannedFilter(TypedDict, total=False):\n    filter_ref: str\n    filter_concept: str\n    binding_ref: str\n    required: bool\n    scope: str\n    detection_source: str\n    mapping_source: str\n    matched_user_term: str\n    provenance: dict[str, Any]\n\n\nclass FilterBinding(TypedDict):\n    binding_ref: str\n    filter_concept: str\n    target_table: str\n    target_column: str\n    operator: str\n    value: Any\n    join_path: list[dict[str, Any]]\n    required: bool\n    scope: str\n\n\nclass SqlGenerationContext(TypedDict):\n''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''    analytical_operations: list[AnalyticalOperation]\n    planned_metrics: list[PlannedMetric]\n    pattern_metadata: dict[str, Any]''',
    '''    analytical_operations: list[AnalyticalOperation]\n    planned_metrics: list[PlannedMetric]\n    planned_filters: list[PlannedFilter]\n    filter_bindings: list[FilterBinding]\n    pattern_metadata: dict[str, Any]''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''    "planning_context.planned_metrics",\n    "sql_pattern_metadata",''',
    '''    "planning_context.planned_metrics",\n    "planning_context.planned_filters",\n    "planning_context.resolved_filter_bindings",\n    "sql_pattern_metadata",''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''    planned_metrics = _planned_metrics(\n        planning_context.get("planned_metrics", [])\n    )\n    analytical_operations = _analytical_operations(''',
    '''    planned_metrics = _planned_metrics(\n        planning_context.get("planned_metrics", [])\n    )\n    planned_filters = _planned_filters(\n        planning_context.get("planned_filters", [])\n    )\n    filter_bindings = _filter_bindings(\n        planning_context.get("resolved_filter_bindings", []),\n        planned_filters=planned_filters,\n    )\n    analytical_operations = _analytical_operations(''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''    if any(\n        operation.get("operation_type") == "ranking"''',
    '''    if any(item.get("required") is True for item in planned_filters):\n        instructions.append(\n            {\n                "name": "required_filters",\n                "content": (\n                    "Aplique todos os planned_filters com required=true no WHERE "\n                    "usando exclusivamente o filter_binding correlacionado por "\n                    "binding_ref. Nao infira tabela, coluna, operador ou valor a "\n                    "partir de normalized_question e nao adicione filtros extras "\n                    "deduzidos do texto."\n                ),\n            }\n        )\n    if any(\n        operation.get("operation_type") == "ranking"''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''            "planned_metrics": planned_metrics,\n            "pattern_metadata": {''',
    '''            "planned_metrics": planned_metrics,\n            "planned_filters": planned_filters,\n            "filter_bindings": filter_bindings,\n            "pattern_metadata": {''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''        "analytical_operations",\n        "planned_metrics",\n    ):''',
    '''        "analytical_operations",\n        "planned_metrics",\n        "planned_filters",\n        "filter_bindings",\n    ):''',
)
replace_once(
    "app/domain/sql_generation.py",
    '''def _binding_cardinality(value: Any) -> dict[str, Any]:\n''',
    '''def _planned_filters(value: Any) -> list[PlannedFilter]:\n    if not isinstance(value, list):\n        raise SqlGenerationInputError("planned_filters deve ser lista.")\n    physical_fields = {\n        "target_table", "target_column", "operator", "value", "join_path"\n    }\n    output: list[PlannedFilter] = []\n    seen_refs: set[str] = set()\n    for item in value:\n        if not isinstance(item, Mapping):\n            raise SqlGenerationInputError("planned_filters contem item invalido.")\n        if physical_fields & set(item):\n            raise SqlGenerationInputError(\n                "planned_filter nao pode conter detalhes fisicos."\n            )\n        filter_ref = _optional_clean_text(item.get("filter_ref"))\n        filter_concept = _optional_clean_text(item.get("filter_concept"))\n        binding_ref = _optional_clean_text(item.get("binding_ref"))\n        scope = _optional_clean_text(item.get("scope"))\n        required = item.get("required")\n        if not (filter_ref and filter_concept and binding_ref and scope):\n            raise SqlGenerationInputError("planned_filter esta incompleto.")\n        if not isinstance(required, bool):\n            raise SqlGenerationInputError("planned_filter.required deve ser booleano.")\n        key = binding_ref.casefold()\n        if key in seen_refs:\n            raise SqlGenerationInputError("planned_filter.binding_ref duplicado.")\n        seen_refs.add(key)\n        output.append(\n            {\n                "filter_ref": filter_ref,\n                "filter_concept": filter_concept,\n                "binding_ref": binding_ref,\n                "required": required,\n                "scope": scope,\n                "detection_source": _optional_clean_text(item.get("detection_source")),\n                "mapping_source": _optional_clean_text(item.get("mapping_source")),\n                "matched_user_term": _optional_clean_text(item.get("matched_user_term")),\n                "provenance": _stable_mapping_copy(item.get("provenance", {}))\n                if isinstance(item.get("provenance", {}), Mapping)\n                else {},\n            }\n        )\n    output.sort(key=lambda item: (item["binding_ref"].casefold(), item["filter_ref"].casefold()))\n    return output\n\n\ndef _filter_bindings(\n    value: Any,\n    *,\n    planned_filters: list[PlannedFilter],\n) -> list[FilterBinding]:\n    if not isinstance(value, list):\n        raise SqlGenerationInputError("resolved_filter_bindings deve ser lista.")\n    referenced = {item["binding_ref"].casefold(): item for item in planned_filters}\n    grouped: dict[str, list[FilterBinding]] = {key: [] for key in referenced}\n    for item in value:\n        if not isinstance(item, Mapping):\n            raise SqlGenerationInputError("resolved_filter_bindings contem item invalido.")\n        binding_ref = _optional_clean_text(item.get("binding_ref"))\n        if not binding_ref or binding_ref.casefold() not in referenced:\n            continue\n        target_table = _optional_clean_text(item.get("target_table"))\n        target_column = _optional_clean_text(item.get("target_column"))\n        operator = _optional_clean_text(item.get("operator"))\n        filter_concept = _optional_clean_text(item.get("filter_concept"))\n        scope = _optional_clean_text(item.get("scope"))\n        required = item.get("required")\n        raw_value = item.get("value")\n        join_path = item.get("join_path")\n        planned = referenced[binding_ref.casefold()]\n        if not (\n            target_table and target_column and operator and filter_concept and scope\n            and isinstance(required, bool)\n            and _is_filled_json_value(raw_value)\n            and _is_valid_join_path(join_path)\n        ):\n            raise SqlGenerationInputError("filter_binding esta incompleto ou invalido.")\n        if (\n            filter_concept.casefold() != planned["filter_concept"].casefold()\n            or scope.casefold() != planned["scope"].casefold()\n            or required is not planned["required"]\n        ):\n            raise SqlGenerationInputError("filter_binding diverge da obrigacao semantica.")\n        grouped[binding_ref.casefold()].append(\n            {\n                "binding_ref": binding_ref,\n                "filter_concept": filter_concept,\n                "target_table": target_table,\n                "target_column": target_column,\n                "operator": operator,\n                "value": deepcopy(raw_value),\n                "join_path": deepcopy(join_path),\n                "required": required,\n                "scope": scope,\n            }\n        )\n    output: list[FilterBinding] = []\n    for key in sorted(grouped):\n        candidates = grouped[key]\n        planned = referenced[key]\n        if len(candidates) > 1:\n            raise SqlGenerationInputError("filter_binding ambiguo para binding_ref.")\n        if planned["required"] is True and len(candidates) != 1:\n            raise SqlGenerationInputError("filter_binding obrigatorio ausente.")\n        if candidates:\n            output.append(candidates[0])\n    return output\n\n\ndef _is_filled_json_value(value: Any) -> bool:\n    if value is None:\n        return False\n    if isinstance(value, str):\n        return bool(value.strip())\n    if isinstance(value, bool) or isinstance(value, int):\n        return True\n    if isinstance(value, float):\n        return math.isfinite(value)\n    if isinstance(value, list):\n        return bool(value) and all(_is_filled_json_value(item) for item in value)\n    if isinstance(value, Mapping):\n        return bool(value) and all(\n            isinstance(key, str) and bool(key.strip()) and _is_filled_json_value(item)\n            for key, item in value.items()\n        )\n    return False\n\n\ndef _is_valid_join_path(value: Any) -> bool:\n    if not isinstance(value, list):\n        return False\n    return all(\n        isinstance(step, Mapping)\n        and bool(step)\n        and all(\n            isinstance(key, str) and bool(key.strip()) and _is_filled_json_value(item)\n            for key, item in step.items()\n        )\n        for step in value\n    )\n\n\ndef _binding_cardinality(value: Any) -> dict[str, Any]:\n''',
)

# Focused synthetic coverage in SQL-generation contract tests.
p = Path("testar_sql_generation.py")
text = p.read_text(encoding="utf-8")
append = r'''


def _plan_with_required_filter() -> dict:
    query_plan = _query_plan()
    query_plan["planning_context"]["planned_filters"] = [
        {
            "filter_ref": "filter-synthetic",
            "filter_concept": "synthetic_category",
            "binding_ref": "binding-synthetic",
            "required": True,
            "scope": "row",
            "detection_source": "intent_semantic_evidence",
            "mapping_source": "filter_binding",
            "matched_user_term": "synthetic",
            "provenance": {"context_version": "context-test-v1"},
        }
    ]
    query_plan["planning_context"]["resolved_filter_bindings"] = [
        {
            "binding_ref": "binding-synthetic",
            "filter_concept": "synthetic_category",
            "target_table": "schema_test.table_test",
            "target_column": "category_key",
            "operator": "=",
            "value": "synthetic_value",
            "join_path": [],
            "required": True,
            "scope": "row",
        }
    ]
    return query_plan


def test_required_filter_e_binding_fisico_sao_separados() -> None:
    request = build_sql_generation_request(_plan_with_required_filter())
    context = request["generation_context"]
    assert context["planned_filters"][0]["binding_ref"] == "binding-synthetic"
    assert "target_table" not in context["planned_filters"][0]
    assert context["filter_bindings"] == [
        {
            "binding_ref": "binding-synthetic",
            "filter_concept": "synthetic_category",
            "target_table": "schema_test.table_test",
            "target_column": "category_key",
            "operator": "=",
            "value": "synthetic_value",
            "join_path": [],
            "required": True,
            "scope": "row",
        }
    ]
    instruction = next(item for item in request["instructions"] if item["name"] == "required_filters")
    assert "required=true" in instruction["content"]
    assert "nao adicione filtros extras" in instruction["content"].lower()


def test_required_filter_sem_binding_falha_fechada() -> None:
    query_plan = _plan_with_required_filter()
    query_plan["planning_context"]["resolved_filter_bindings"] = []
    try:
        build_sql_generation_request(query_plan)
    except SqlGenerationInputError as exc:
        assert "obrigatorio ausente" in str(exc)
    else:
        raise AssertionError("binding obrigatorio ausente deveria falhar")


def test_binding_ambiguo_falha_fechada() -> None:
    query_plan = _plan_with_required_filter()
    query_plan["planning_context"]["resolved_filter_bindings"].append(
        deepcopy(query_plan["planning_context"]["resolved_filter_bindings"][0])
    )
    try:
        build_sql_generation_request(query_plan)
    except SqlGenerationInputError as exc:
        assert "ambiguo" in str(exc)
    else:
        raise AssertionError("binding ambiguo deveria falhar")


def test_filtros_sao_deterministicos_e_ignoram_nao_referenciados() -> None:
    query_plan = _plan_with_required_filter()
    second_filter = deepcopy(query_plan["planning_context"]["planned_filters"][0])
    second_filter.update({"filter_ref": "filter-a", "filter_concept": "alpha", "binding_ref": "binding-a"})
    second_binding = deepcopy(query_plan["planning_context"]["resolved_filter_bindings"][0])
    second_binding.update({"filter_concept": "alpha", "binding_ref": "binding-a", "value": "alpha-value"})
    extra_binding = deepcopy(second_binding)
    extra_binding["binding_ref"] = "binding-unreferenced"
    query_plan["planning_context"]["planned_filters"] = [query_plan["planning_context"]["planned_filters"][0], second_filter]
    query_plan["planning_context"]["resolved_filter_bindings"] = [extra_binding, query_plan["planning_context"]["resolved_filter_bindings"][0], second_binding]
    request = build_sql_generation_request(query_plan)
    assert [item["binding_ref"] for item in request["generation_context"]["planned_filters"]] == ["binding-a", "binding-synthetic"]
    assert [item["binding_ref"] for item in request["generation_context"]["filter_bindings"]] == ["binding-a", "binding-synthetic"]


def test_planned_filter_nao_aceita_campos_fisicos() -> None:
    query_plan = _plan_with_required_filter()
    query_plan["planning_context"]["planned_filters"][0]["target_column"] = "forbidden"
    try:
        build_sql_generation_request(query_plan)
    except SqlGenerationInputError as exc:
        assert "detalhes fisicos" in str(exc)
    else:
        raise AssertionError("planned_filter fisico deveria falhar")
'''
if "def _plan_with_required_filter()" not in text:
    p.write_text(text + append, encoding="utf-8")

# Remove temporary automation artifacts from the resulting branch.
Path(".github/scripts/apply_planned_filters_microstage2.py").unlink(missing_ok=True)
Path(".github/workflows/apply-planned-filters-microstage2.yml").unlink(missing_ok=True)
