"""Bounded, tenant-neutral feasibility of declared conditional metric bindings.

This is NOT a metric inference engine. It checks whether the already
authorized binding route *could* meet an operation's structural cardinality.
Direct metric aliases and other routes are deliberately not evaluated.
No historical questions, SQL, private identifiers or LLM responses are used.
"""
from __future__ import annotations

from collections.abc import Mapping
from itertools import combinations
from typing import Any

MAX_COMBINATIONS = 20_000
MAX_CANDIDATES = 128


def binding_route_feasibility(
    *,
    bindings: list[Mapping[str, Any]],
    cardinality: Mapping[str, Any],
) -> str:
    """Return possible, impossible, indeterminate, or not_applicable.

    A possible result proves only that the declared binding conditions are
    mutually satisfiable. It does not prove that a question expresses them,
    that a SQL can be generated, or that the business mapping is correct.
    """
    if not isinstance(cardinality, Mapping):
        return "indeterminate"
    minimum = cardinality.get("minimum")
    maximum = cardinality.get("maximum")
    mode = cardinality.get("mode")
    if type(minimum) is not int or type(maximum) is not int:
        return "indeterminate"
    if minimum < 1 or maximum < minimum:
        return "indeterminate"
    if mode == "single" and minimum == maximum == 1:
        return "not_applicable"
    if mode != "multiple":
        return "indeterminate"
    if not bindings:
        return "not_configured"
    if len(bindings) > MAX_CANDIDATES:
        return "indeterminate"

    same_concept = cardinality.get("same_metric_concept")
    if type(same_concept) is not bool:
        return "indeterminate"

    groups: dict[str, list[Mapping[str, Any]]] = {}
    for item in bindings:
        if not isinstance(item, Mapping):
            return "indeterminate"
        concept, table, column = (
            item.get("metric_concept"),
            item.get("target_table"),
            item.get("target_column"),
        )
        present = item.get("when_present")
        absent = item.get("when_absent")
        if (
            not all(isinstance(x, str) and x.strip()
                    for x in (concept, table, column))
            or not isinstance(present, list)
            or not isinstance(absent, list)
            or not all(isinstance(x, str) and x.strip()
                       for x in present + absent)
        ):
            return "indeterminate"
        key = concept.casefold() if same_concept else "_all_concepts_"
        groups.setdefault(key, []).append(item)

    examined = 0
    for group in groups.values():
        if len(group) < minimum:
            continue
        for subset in combinations(group, minimum):
            examined += 1
            if examined > MAX_COMBINATIONS:
                return "indeterminate"
            # Comparison operand refs are derived from metric concept +
            # physical target. Two conditional aliases with an identical
            # metric ref cannot count as two distinct operands.
            identities = {
                (
                    item["metric_concept"],
                    item["target_table"],
                    item["target_column"],
                )
                for item in subset
            }
            if len(identities) != len(subset):
                continue
            required: set[str] = set()
            forbidden: set[str] = set()
            for item in subset:
                required.update(x.casefold() for x in item["when_present"])
                forbidden.update(x.casefold() for x in item["when_absent"])
            if not required.intersection(forbidden):
                return "possible"
    return "impossible"
