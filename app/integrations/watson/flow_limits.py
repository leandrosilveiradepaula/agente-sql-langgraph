from __future__ import annotations

from dataclasses import dataclass


class WatsonFlowContractError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class WatsonFlowLimits:
    max_approved_sql_bytes: int
    max_transport_sql_characters: int
    max_transport_sql_bytes: int
    max_payload_bytes: int
    max_raw_response_bytes: int
    max_response_depth: int
    max_response_members: int
    max_rows: int
    max_columns: int
    max_cells: int
    max_column_name_bytes: int
    max_string_cell_bytes: int
    max_error_messages: int
    max_error_message_bytes: int
    max_query_id_bytes: int
    max_duration_ms: int
    max_diagnostics: int
    max_diagnostic_code_bytes: int
    max_diagnostic_message_bytes: int
    max_retry_after_seconds: int
    max_access_token_bytes: int
    max_flow_id_bytes: int
    max_url_bytes: int

    def __post_init__(self) -> None:
        ceilings = {
            "max_approved_sql_bytes": 2_000_000,
            "max_transport_sql_characters": 100_000,
            "max_transport_sql_bytes": 1_000_000,
            "max_payload_bytes": 2_000_000,
            "max_raw_response_bytes": 20_000_000,
            "max_response_depth": 64,
            "max_response_members": 1_000_000,
            "max_rows": 1_000_000,
            "max_columns": 10_000,
            "max_cells": 10_000_000,
            "max_column_name_bytes": 1024,
            "max_string_cell_bytes": 10_000_000,
            "max_error_messages": 1000,
            "max_error_message_bytes": 8192,
            "max_query_id_bytes": 1024,
            "max_duration_ms": 86_400_000,
            "max_diagnostics": 1000,
            "max_diagnostic_code_bytes": 256,
            "max_diagnostic_message_bytes": 8192,
            "max_retry_after_seconds": 86_400,
            "max_access_token_bytes": 16_384,
            "max_flow_id_bytes": 128,
            "max_url_bytes": 2048,
        }
        for name, maximum in ceilings.items():
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int):
                raise WatsonFlowContractError(f"{name} deve ser inteiro.")
            if value <= 0 or value > maximum:
                raise WatsonFlowContractError(
                    f"{name} esta fora do intervalo permitido."
                )
        if self.max_transport_sql_characters != 10_000:
            raise WatsonFlowContractError(
                "max_transport_sql_characters deve refletir 10.000."
            )
        if self.max_transport_sql_bytes < self.max_transport_sql_characters:
            raise WatsonFlowContractError(
                "max_transport_sql_bytes deve comportar o limite em caracteres."
            )
        if self.max_payload_bytes <= self.max_transport_sql_bytes:
            raise WatsonFlowContractError(
                "max_payload_bytes deve comportar o payload minimo."
            )


def default_watson_flow_limits() -> WatsonFlowLimits:
    return WatsonFlowLimits(
        max_approved_sql_bytes=200_000,
        max_transport_sql_characters=10_000,
        max_transport_sql_bytes=40_000,
        max_payload_bytes=80_000,
        max_raw_response_bytes=1_000_000,
        max_response_depth=12,
        max_response_members=50_000,
        max_rows=10_000,
        max_columns=200,
        max_cells=200_000,
        max_column_name_bytes=128,
        max_string_cell_bytes=65_536,
        max_error_messages=20,
        max_error_message_bytes=512,
        max_query_id_bytes=128,
        max_duration_ms=300_000,
        max_diagnostics=20,
        max_diagnostic_code_bytes=128,
        max_diagnostic_message_bytes=512,
        max_retry_after_seconds=3600,
        max_access_token_bytes=8192,
        max_flow_id_bytes=64,
        max_url_bytes=1024,
    )
