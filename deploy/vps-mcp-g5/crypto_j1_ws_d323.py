"""Strict fixed-operation WS D323 owner-sidecar projection, separate from REST auditor."""
from __future__ import annotations

import json
import re
import socket
import time

from crypto_j1_readonly import OWNER_SOCKET, HOUR_MS, _SHA, _fail, Rejected

# CIA/J1 WS D323: separate from the historical two-contract REST auditor.
# This projection never opens the private WS SQLite or accepts caller paths.
_WS_D323_FIELDS = frozenset((
    "schema_version", "status", "latest_eligible_closed_end_ms",
    "verified_closed_hours", "expected_closed_hours",
    "verified_contracts_per_hour", "expected_contracts_per_hour",
    "persisted_ws_rows", "ranked_scope_sha256", "ws_metadata_sha256",
    "ws_journal_sha256", "last_hour_sha256",
    "ws_timer_active_enabled", "rotation_timer_active_enabled",
    "n2_quiesced", "old_rest_n50_quiesced", "ws_service_not_failed",
    "ws_journal_integrity_verified", "ws_closed_24h_local_verified",
    "rotation_36h_live_verified", "continuous_collector_verified",
    "marketwide_top50_verified", "crypto_identity_independently_verified",
    "source_authenticated", "approved_for_signals",
    "live_trading_authorized", "orders_sent", "network_requests",
    "database_mutation_statements", "systemd_modified",
))
_WS_D323_STATUSES = frozenset((
    "ws_24h_local_evidence_verified", "invalid_or_untrusted_witness_input",
    "owner_optin_required", "owner_environment_abstain",
    "awaiting_safe_closed_hour_audit_window", "n2_failback_observed",
    "ws_systemd_isolation_or_service_not_ready",
    "awaiting_owner_ws_journal_audit", "owner_active_ws_epoch_unavailable",
    "owner_ws_scope_integrity_abstain", "owner_ws_journal_integrity_abstain",
    "accumulating_or_incomplete_ws_24h", "owner_ws_readonly_audit_abstain",
))
_WS_D323_FALSE = frozenset((
    "rotation_36h_live_verified", "continuous_collector_verified",
    "marketwide_top50_verified", "crypto_identity_independently_verified",
    "source_authenticated", "approved_for_signals",
    "live_trading_authorized", "orders_sent", "systemd_modified",
))
_WS_D323_BOOLEAN = frozenset((
    "ws_timer_active_enabled", "rotation_timer_active_enabled",
    "n2_quiesced", "old_rest_n50_quiesced", "ws_service_not_failed",
    "ws_journal_integrity_verified", "ws_closed_24h_local_verified",
)) | _WS_D323_FALSE
_WS_D323_HASHES = frozenset((
    "ranked_scope_sha256", "ws_metadata_sha256", "ws_journal_sha256",
    "last_hour_sha256",
))


def validate_ws_d323_report(report: object) -> bool:
    """Exact, fail-closed count/digest-only contract; no promotion to trading."""
    if type(report) is not dict or set(report) != _WS_D323_FIELDS:
        return False
    if (report["schema_version"] != "j1-n50-ws-closed24h-owner-witness-v1"
            or report["status"] not in _WS_D323_STATUSES
            or any(type(report[k]) is not bool for k in _WS_D323_BOOLEAN)
            or any(report[k] is not False for k in _WS_D323_FALSE)
            or any(type(report[k]) is not int or report[k] != 0
                   for k in ("network_requests", "database_mutation_statements"))
            or type(report["expected_closed_hours"]) is not int
            or report["expected_closed_hours"] != 24
            or type(report["expected_contracts_per_hour"]) is not int
            or report["expected_contracts_per_hour"] != 50):
        return False
    for key in ("verified_closed_hours", "verified_contracts_per_hour",
                "persisted_ws_rows"):
        if type(report[key]) is not int or not 0 <= report[key] <= 1_000_000:
            return False
    timestamp = report["latest_eligible_closed_end_ms"]
    if (timestamp is not None and
            (type(timestamp) is not int or timestamp % HOUR_MS != 0
             or not 1_600_000_000_000 <= timestamp <=
             time.time_ns() // 1_000_000 + 60_000)):
        return False
    for key in _WS_D323_HASHES:
        value = report[key]
        if value is not None and (
            type(value) is not str or _SHA.fullmatch(value) is None
        ):
            return False
    if report["status"] == "ws_24h_local_evidence_verified":
        return (
            report["ws_journal_integrity_verified"] is True
            and report["ws_closed_24h_local_verified"] is True
            and report["verified_closed_hours"] == 24
            and report["verified_contracts_per_hour"] == 50
            and report["persisted_ws_rows"] >= 1200
            and timestamp is not None
            and all(report[k] is not None for k in _WS_D323_HASHES)
        )
    return (
        report["ws_closed_24h_local_verified"] is False
        and report["verified_closed_hours"] == 0
        and report["verified_contracts_per_hour"] == 0
    )


def ws_d323_audit_via_owner() -> dict:
    """One parameterless socket operation, independently checking owner output."""
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(95)
            client.connect(OWNER_SOCKET)
            client.sendall(b'{"op":"cia_ws_d323"}\n')
            chunks = bytearray()
            while b"\n" not in chunks and len(chunks) <= 4096:
                part = client.recv(min(1024, 4097 - len(chunks)))
                if not part:
                    break
                chunks.extend(part)
        if (not 1 <= len(chunks) <= 4096
                or chunks.count(b"\n") != 1 or not chunks.endswith(b"\n")):
            raise Rejected
        report = json.loads(bytes(chunks[:-1]))
        if validate_ws_d323_report(report):
            return report
        if type(report) is dict and report == _fail("ws_d323_owner_audit_unavailable"):
            return report
        if type(report) is dict and report.get("status") == "blocked":
            return _fail("ws_d323_owner_audit_blocked")
        raise Rejected
    except (OSError, TimeoutError, Rejected, ValueError, TypeError,
            OverflowError, UnicodeError):
        return _fail("ws_d323_owner_service_unavailable")
