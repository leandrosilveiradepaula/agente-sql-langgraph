from __future__ import annotations

import math
from copy import deepcopy
from datetime import date, datetime, time, timezone
from decimal import Decimal
from uuid import UUID

from app.domain.result_normalization import normalize_execution_result
from testar_sql_execution import _provider_result, _request


LIMITS = {
    "max_rows": 20,
    "max_columns": 20,
    "max_total_cells": 200,
    "max_nesting_depth": 6,
    "max_collection_items": 20,
    "max_serialized_bytes": 20000,
    "max_diagnostic_entries": 20,
}


def _result(columns=None, rows=None, **overrides):
    request = _request()
    selected_rows = rows if rows is not None else [{"value": 1}]
    if columns is not None:
        selected_columns = columns
    elif selected_rows:
        selected_columns = [{"name": key} for key in selected_rows[0].keys()]
    else:
        selected_columns = [{"name": "value"}]
    safe_columns = [
        {"name": f"safe_{index}", "type": column.get("type")}
        for index, column in enumerate(selected_columns)
    ]
    safe_rows = [
        {column["name"]: 1 for column in safe_columns}
        for _ in selected_rows
    ]
    provider_result = _provider_result(
        columns=safe_columns,
        rows=safe_rows,
        row_count=len(selected_rows),
    )
    from app.domain.sql_execution import normalize_sql_execution_result

    result = normalize_sql_execution_result(
        request=request,
        provider_result=provider_result,
    )
    result["columns"] = deepcopy(selected_columns)
    result["rows"] = deepcopy(selected_rows)
    result["row_count"] = len(selected_rows)
    result.update(overrides)
    return result


def _normalize(value):
    return normalize_execution_result(
        _result(rows=[{"value": value}]),
        limits=LIMITS,
    )


def test_resultado_vazio_valido() -> None:
    result = normalize_execution_result(
        _result(columns=[], rows=[]),
        limits=LIMITS,
    )
    assert result["status"] == "success"
    assert result["metrics"]["row_count"] == 0


def test_uma_coluna_uma_linha() -> None:
    result = _normalize(1)
    assert result["columns"][0]["original_name"] == "value"
    assert result["rows"][0]["cells"][0]["type"] == "integer"


def test_multiplas_colunas_linhas_ordem_preservada() -> None:
    result = normalize_execution_result(
        _result(
            columns=[{"name": "a"}, {"name": "b"}],
            rows=[{"a": 1, "b": "x"}, {"a": 2, "b": "y"}],
        ),
        limits=LIMITS,
    )
    assert [column["original_name"] for column in result["columns"]] == ["a", "b"]
    assert [row["ordinal"] for row in result["rows"]] == [0, 1]


def test_null_bool_int_decimal_float_string_datas_binario_json_uuid() -> None:
    values = [
        (None, "null", None),
        (True, "boolean", True),
        (7, "integer", 7),
        (Decimal("123.4500"), "decimal", "123.4500"),
        (1.25, "float", 1.25),
        ("acao utf-8", "string", "acao utf-8"),
        ("", "string", ""),
        (date(2024, 1, 2), "date", "2024-01-02"),
        (
            datetime(2024, 1, 2, 3, 4, tzinfo=timezone.utc),
            "datetime",
            "2024-01-02T03:04:00+00:00",
        ),
        (datetime(2024, 1, 2, 3, 4), "datetime", "2024-01-02T03:04:00"),
        (time(3, 4, 5), "time", "03:04:05"),
        (b"abc", "binary", "YWJj"),
        (bytearray(b"abc"), "binary", "YWJj"),
        ({"b": 2, "a": 1}, "json", {"a": {"type": "integer", "value": 1}, "b": {"type": "integer", "value": 2}}),
        ([1, "x"], "json", [{"type": "integer", "value": 1}, {"type": "string", "value": "x"}]),
        ((1, 2), "json", [{"type": "integer", "value": 1}, {"type": "integer", "value": 2}]),
        (UUID("12345678-1234-5678-1234-567812345678"), "uuid", "12345678-1234-5678-1234-567812345678"),
    ]
    for value, expected_type, expected_value in values:
        result = _normalize(value)
        cell = result["rows"][0]["cells"][0]
        assert cell["type"] == expected_type
        assert cell["value"] == expected_value


def test_floats_especiais() -> None:
    cases = [
        (-0.0, "-0.0"),
        (math.nan, "NaN"),
        (math.inf, "Infinity"),
        (-math.inf, "-Infinity"),
    ]
    for value, special in cases:
        result = _normalize(value)
        assert result["rows"][0]["cells"][0]["special"] == special


def test_tipo_desconhecido_rejeita_sem_valor() -> None:
    result = _normalize(object())
    assert result["status"] == "rejected"
    assert "object at" not in repr(result)


def test_estrutura_ciclica_profundidade_e_colecao_excessivas() -> None:
    cyc = []
    cyc.append(cyc)
    for value, limits in [
        (cyc, LIMITS),
        ({"a": {"b": {"c": {"d": 1}}}}, {**LIMITS, "max_nesting_depth": 2}),
        (list(range(4)), {**LIMITS, "max_collection_items": 3}),
    ]:
        result = normalize_execution_result(
            _result(rows=[{"value": value}]),
            limits=limits,
        )
        assert result["status"] == "rejected"
        assert "value" not in repr(result["diagnostics"])


def test_coluna_duplicada_ordinal_e_shape_invalidos() -> None:
    duplicate = _result(columns=[{"name": "a"}, {"name": "b"}], rows=[{"a": 1, "b": 2}])
    duplicate["columns"][1]["name"] = "a"
    assert normalize_execution_result(duplicate, limits=LIMITS)["status"] == "rejected"

    bad_shape = _result(columns=[{"name": "a"}, {"name": "b"}], rows=[{"a": 1, "b": 2}])
    bad_shape["rows"][0] = {"a": 1}
    assert normalize_execution_result(bad_shape, limits=LIMITS)["status"] == "rejected"


def test_resultado_nao_executado_rejected_fingerprint_divergente() -> None:
    for overrides in [
        {"executed": False},
        {"status": "rejected"},
        {"response_fingerprint": None},
    ]:
        result = normalize_execution_result(
            _result(**overrides),
            limits=LIMITS,
        )
        assert result["status"] == "rejected"


def test_sem_mutacao_copia_fingerprint_deterministico_e_sensivel() -> None:
    execution_result = _result(
        columns=[{"name": "a"}, {"name": "b"}],
        rows=[{"a": 1, "b": "x"}, {"a": 2, "b": "y"}],
    )
    original = deepcopy(execution_result)
    first = normalize_execution_result(execution_result, limits=LIMITS)
    second = normalize_execution_result(execution_result, limits=LIMITS)
    assert execution_result == original
    assert first == second
    assert first["result_fingerprint"] == second["result_fingerprint"]

    changed_type = normalize_execution_result(
        _result(rows=[{"value": "1"}]),
        limits=LIMITS,
    )
    changed_order = normalize_execution_result(
        _result(
            columns=[{"name": "b"}, {"name": "a"}],
            rows=[{"b": "x", "a": 1}],
        ),
        limits=LIMITS,
    )
    assert changed_type["result_fingerprint"] != _normalize(1)["result_fingerprint"]
    assert changed_order["result_fingerprint"] != first["result_fingerprint"]


def test_limites_defensivos() -> None:
    result = normalize_execution_result(
        _result(rows=[{"value": 1}, {"value": 2}]),
        limits={**LIMITS, "max_rows": 1},
    )
    assert result["status"] == "rejected"


def main() -> None:
    tests = [
        test_resultado_vazio_valido,
        test_uma_coluna_uma_linha,
        test_multiplas_colunas_linhas_ordem_preservada,
        test_null_bool_int_decimal_float_string_datas_binario_json_uuid,
        test_floats_especiais,
        test_tipo_desconhecido_rejeita_sem_valor,
        test_estrutura_ciclica_profundidade_e_colecao_excessivas,
        test_coluna_duplicada_ordinal_e_shape_invalidos,
        test_resultado_nao_executado_rejected_fingerprint_divergente,
        test_sem_mutacao_copia_fingerprint_deterministico_e_sensivel,
        test_limites_defensivos,
    ]
    for index, test_function in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {test_function.__name__}: OK")


if __name__ == "__main__":
    main()
