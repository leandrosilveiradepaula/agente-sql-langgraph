from __future__ import annotations

import json
from copy import deepcopy
from datetime import datetime, timezone
from decimal import Decimal

from app.domain.result_serialization import serialize_normalized_result
from testar_result_normalization import LIMITS, _result
from app.domain.result_normalization import normalize_execution_result


def _serialized(value, *, max_bytes: int = 40000):
    normalized = normalize_execution_result(
        _result(rows=[{"value": value}]),
        limits=LIMITS,
    )
    return serialize_normalized_result(
        normalized,
        max_serialized_bytes=max_bytes,
    )


def test_json_safe_e_allow_nan_false() -> None:
    result = _serialized({"b": 2, "a": [1, None, True]})
    assert result["status"] == "success"
    json.dumps(result, allow_nan=False)


def test_decimal_preserva_precisao_sem_float() -> None:
    result = _serialized(Decimal("123.4500"))
    cell = result["rows"][0]["cells"][0]
    assert cell["type"] == "decimal"
    assert cell["value"] == "123.4500"
    assert not isinstance(cell["value"], float)


def test_datas_timezone_naive_e_binario() -> None:
    aware = _serialized(datetime(2024, 1, 2, tzinfo=timezone.utc))
    naive = _serialized(datetime(2024, 1, 2))
    binary = _serialized(b"abc")
    assert aware["rows"][0]["cells"][0]["timezone"] is True
    assert naive["rows"][0]["cells"][0]["timezone"] is False
    assert binary["rows"][0]["cells"][0]["encoding"] == "base64"


def test_dict_canonicalizado_lista_ordem_muda() -> None:
    first = _serialized({"b": 2, "a": 1})
    second = _serialized({"a": 1, "b": 2})
    assert first["result_fingerprint"] == second["result_fingerprint"]
    assert _serialized([1, 2])["result_fingerprint"] != _serialized([2, 1])[
        "result_fingerprint"
    ]


def test_null_bool_int_separados_float_especial() -> None:
    assert _serialized(None)["rows"][0]["cells"][0]["type"] == "null"
    assert _serialized(True)["rows"][0]["cells"][0]["type"] == "boolean"
    assert _serialized(1)["rows"][0]["cells"][0]["type"] == "integer"
    assert _serialized(float("nan"))["rows"][0]["cells"][0]["special"] == "NaN"


def test_contract_version_lineage_fingerprint_deterministico() -> None:
    first = _serialized("x")
    second = _serialized("x")
    assert first["contract_version"]
    assert first["lineage"]["execution_request_fingerprint"]
    assert first["lineage"]["serialized_result_fingerprint"]
    assert first["result_fingerprint"] == second["result_fingerprint"]


def test_max_serialized_bytes_sem_mutacao_e_sem_sql_credenciais() -> None:
    normalized = normalize_execution_result(
        _result(rows=[{"value": "x"}]),
        limits=LIMITS,
    )
    original = deepcopy(normalized)
    rejected = serialize_normalized_result(
        normalized,
        max_serialized_bytes=1,
    )
    assert rejected["status"] == "rejected"
    assert normalized == original
    serialized = repr(_serialized("password=hidden SELECT id"))
    assert "SELECT id FROM schema_test.table_test" not in serialized
    assert "postgresql://" not in serialized


def test_provider_metadata_sanitizada() -> None:
    result = _serialized("x")
    assert result["columns"][0]["metadata"] == {}


def main() -> None:
    tests = [
        test_json_safe_e_allow_nan_false,
        test_decimal_preserva_precisao_sem_float,
        test_datas_timezone_naive_e_binario,
        test_dict_canonicalizado_lista_ordem_muda,
        test_null_bool_int_separados_float_especial,
        test_contract_version_lineage_fingerprint_deterministico,
        test_max_serialized_bytes_sem_mutacao_e_sem_sql_credenciais,
        test_provider_metadata_sanitizada,
    ]
    for index, test_function in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {test_function.__name__}: OK")


if __name__ == "__main__":
    main()
