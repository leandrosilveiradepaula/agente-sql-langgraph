from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from app.domain.result_normalization import canonical_json, stable_fingerprint
from app.domain.result_normalization_types import (
    RESULT_SERIALIZATION_CONTRACT_VERSION,
    NormalizedQueryResult,
    SerializedQueryResult,
    SerializationDiagnostic,
)


class ResultSerializationError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        diagnostic: SerializationDiagnostic | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.diagnostic = diagnostic
        super().__init__(message)


def serialize_normalized_result(
    normalized_result: NormalizedQueryResult,
    *,
    max_serialized_bytes: int,
) -> SerializedQueryResult:
    original = deepcopy(normalized_result)
    try:
        if original.get("status") != "success":
            raise ResultSerializationError(
                "RESULT_SERIALIZATION_INPUT_INVALID",
                "Serializacao exige resultado normalizado success.",
            )
        if not isinstance(max_serialized_bytes, int) or max_serialized_bytes <= 0:
            raise ResultSerializationError(
                "RESULT_SERIALIZATION_LIMIT_EXCEEDED",
                "Limite de serializacao deve ser inteiro positivo.",
            )
        lineage = deepcopy(original["lineage"])
        lineage["serialization_contract_version"] = (
            RESULT_SERIALIZATION_CONTRACT_VERSION
        )
        payload = {
            "status": "success",
            "contract_version": RESULT_SERIALIZATION_CONTRACT_VERSION,
            "columns": deepcopy(original["columns"]),
            "rows": deepcopy(original["rows"]),
            "lineage": lineage,
            "diagnostics": [],
            "warnings": list(original.get("warnings", [])),
            "error_code": None,
        }
        serialized_fingerprint = stable_fingerprint(payload)
        lineage["serialized_result_fingerprint"] = serialized_fingerprint
        payload["lineage"] = lineage
        payload["result_fingerprint"] = serialized_fingerprint
        canonical = canonical_json(payload)
        json.loads(canonical)
        json.dumps(json.loads(canonical), allow_nan=False)
        size = len(canonical.encode("utf-8"))
        if size > max_serialized_bytes:
            raise ResultSerializationError(
                "RESULT_SERIALIZATION_LIMIT_EXCEEDED",
                "Payload serializado excede limite de bytes.",
                diagnostic={
                    "code": "RESULT_SERIALIZATION_LIMIT_EXCEEDED",
                    "message": "Payload serializado excede limite de bytes.",
                    "row_ordinal": None,
                    "column_ordinal": None,
                    "normalized_type": None,
                    "size": size,
                    "fingerprint": serialized_fingerprint,
                },
            )
        return {
            **payload,
            "canonical_json": canonical,
        }
    except ResultSerializationError as error:
        diagnostic = error.diagnostic or {
            "code": error.code,
            "message": error.message,
            "row_ordinal": None,
            "column_ordinal": None,
            "normalized_type": None,
            "size": None,
            "fingerprint": None,
        }
        return _rejected(original, error.code, diagnostic)
    except (TypeError, ValueError) as error:
        return _rejected(
            original,
            "RESULT_SERIALIZATION_VALUE_INVALID",
            {
                "code": "RESULT_SERIALIZATION_VALUE_INVALID",
                "message": "Resultado normalizado contem valor nao serializavel.",
                "row_ordinal": None,
                "column_ordinal": None,
                "normalized_type": None,
                "size": None,
                "fingerprint": None,
            },
        )


def to_canonical_json(serialized_result: SerializedQueryResult) -> str:
    if serialized_result.get("canonical_json"):
        return str(serialized_result["canonical_json"])
    return canonical_json(serialized_result)


def _rejected(
    normalized_result: dict[str, Any],
    code: str,
    diagnostic: SerializationDiagnostic,
) -> SerializedQueryResult:
    return {
        "status": "rejected",
        "contract_version": RESULT_SERIALIZATION_CONTRACT_VERSION,
        "columns": [],
        "rows": [],
        "lineage": deepcopy(normalized_result.get("lineage", {})),
        "diagnostics": [diagnostic],
        "warnings": [],
        "error_code": code,
        "result_fingerprint": None,
        "canonical_json": None,
    }
