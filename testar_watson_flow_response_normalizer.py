from __future__ import annotations

import math

from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.flow_response_normalizer import (
    normalize_watson_flow_response,
)


LIMITS = default_watson_flow_limits()
SUCCESS = {
    "success": True,
    "data": [{"category": "A", "amount": 10}],
    "columns": ["category", "amount"],
    "row_count": 1,
    "query_id": "fixture-query",
    "truncated": False,
    "execution_time_ms": 12,
}


def _norm(raw):
    return normalize_watson_flow_response(raw, "execution", LIMITS)


def _bad(raw, code: str | None = None) -> None:
    result = _norm(raw)
    assert result.status == "invalid_response", result
    if code:
        assert result.error_code == code


def main() -> None:
    assert _norm(SUCCESS).status == "success"
    assert _norm({"result": SUCCESS}).status == "success"
    assert _norm({"output": SUCCESS}).status == "success"
    assert _norm({"result": {"output": SUCCESS}}).status == "success"
    assert _norm({"output": {"result": SUCCESS}}).status == "success"
    _bad({"data": []})
    _bad({"success": "true"})
    _bad({"success": 1})
    _bad({"success": True, "result": {"success": False, "error_code": "syntax_error"}}, "WATSON_FLOW_AMBIGUOUS_RESPONSE")
    assert _norm({"result": SUCCESS, "output": SUCCESS}).status == "success"
    other_success = {
        **SUCCESS,
        "data": [{"category": "B", "amount": 20}],
    }
    _bad({"result": SUCCESS, "output": other_success}, "WATSON_FLOW_AMBIGUOUS_RESPONSE")
    _bad({"success": True, "data": "bad"})
    _bad({"success": True, "data": [1]})
    assert _norm({"success": True, "data": [], "columns": []}).columns == []
    assert _norm({"success": True, "data": [{"a": 1}]}).columns == [{"name": "a"}]
    _bad({"success": True, "data": [{"a": 1, "b": 2}], "columns": ["a"]})
    assert _norm(SUCCESS).row_count == 1
    _bad({**SUCCESS, "row_count": 2})
    _bad({**SUCCESS, "row_count": True})
    assert _norm(SUCCESS).query_id == "fixture-query"
    _bad({**SUCCESS, "query_id": "x" * 200}, "WATSON_FLOW_RESPONSE_TOO_LARGE")
    assert _norm(SUCCESS).duration_ms == 12
    _bad({**SUCCESS, "execution_time_ms": -1})
    _bad({**SUCCESS, "execution_time_ms": math.nan})
    assert _norm({**SUCCESS, "truncated": True}).truncated is True
    _bad({**SUCCESS, "truncated": "true"})
    error = _norm({"success": False, "error": "syntax", "error_code": "syntax_error"})
    assert error.status == "functional_error"
    error_list = normalize_watson_flow_response(
        {"success": False, "error": ["x"], "failure_category": "column_not_found"},
        "preflight",
        LIMITS,
    )
    assert error_list.repairable is True
    assert _norm({"success": False}).status == "functional_error"
    _bad({"success": False, "data": [{"a": 1}]})
    small_limits = default_watson_flow_limits()
    _bad({"success": True, "data": [{"a": i} for i in range(small_limits.max_rows + 1)]}, "WATSON_FLOW_RESPONSE_TOO_LARGE")
    _bad({"success": True, "data": [{f"c{i}": i for i in range(LIMITS.max_columns + 1)}]})
    _bad({"success": True, "data": [{f"c{i}": i for i in range(500)} for _ in range(500)]})
    _bad({"success": True, "data": [{"a": "x" * (LIMITS.max_raw_response_bytes + 1)}]})
    nested = {"success": True, "data": [{"a": 1}]}
    current = nested
    for _ in range(LIMITS.max_response_depth + 2):
        current["result"] = {}
        current = current["result"]
    _bad(nested, "WATSON_FLOW_RESPONSE_TOO_LARGE")
    cycle = {"success": True}
    cycle["self"] = cycle
    _bad(cycle)
    raw = {"result": {**SUCCESS}}
    before = repr(raw)
    assert _norm(raw).rows == [{"category": "A", "amount": 10}]
    assert repr(raw) == before
    result = _norm(raw)
    result.rows[0]["amount"] = 99
    assert _norm(raw).rows[0]["amount"] == 10
    assert "raw_output" not in repr(result)
    assert _norm(raw).rows == _norm(raw).rows
    assert normalize_watson_flow_response(raw, "preflight", LIMITS).purpose == "preflight"
    print("testar_watson_flow_response_normalizer.py: 42/42 OK")


if __name__ == "__main__":
    main()
