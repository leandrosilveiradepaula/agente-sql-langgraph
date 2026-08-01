from __future__ import annotations

from app.integrations.watson.flow_limits import default_watson_flow_limits
from app.integrations.watson.sql_transport import (
    build_watson_flow_payload,
    compact_sql_for_watson_transport,
)


LIMITS = default_watson_flow_limits()


def _ok(sql: str) -> str:
    result = compact_sql_for_watson_transport(sql, LIMITS)
    assert result.status == "success", result
    assert result.sql_transport is not None
    return result.sql_transport


def _bad(sql: str, code: str | None = None) -> None:
    result = compact_sql_for_watson_transport(sql, LIMITS)
    assert result.status == "rejected"
    if code:
        assert result.error_code == code


def main() -> None:
    assert _ok("SELECT a FROM t") == "SELECT a FROM t"
    assert _ok("SELECT   a    FROM   t") == "SELECT a FROM t"
    assert _ok("SELECT\n a\r\nFROM t") == "SELECT a FROM t"
    assert _ok("SELECT\t a FROM t") == "SELECT a FROM t"
    assert _ok("SELECT a -- comment\nFROM t") == "SELECT a FROM t"
    assert _ok("SELECT a /* comment */ FROM t") == "SELECT a FROM t"
    assert _ok("SELECT '-- keep' FROM t") == "SELECT '-- keep' FROM t"
    assert _ok("SELECT '/* keep */' FROM t") == "SELECT '/* keep */' FROM t"
    assert _ok("SELECT 'a b' FROM t") == "SELECT 'a b' FROM t"
    assert _ok("SELECT 'it''s' FROM t") == "SELECT 'it''s' FROM t"
    assert _ok('SELECT "Col A" FROM t') == 'SELECT "Col A" FROM t'
    assert _ok('SELECT "a""b" FROM t') == 'SELECT "a""b" FROM t'
    assert _ok("SELECT a.b FROM t") == "SELECT a.b FROM t"
    assert _ok("SELECT a,b FROM t") == "SELECT a,b FROM t"
    assert _ok("SELECT (a) FROM t") == "SELECT(a) FROM t"
    assert _ok("SELECT a>=1 AND b<>2 FROM t") == "SELECT a>=1 AND b<>2 FROM t"
    assert _ok("SELECT 10.5 FROM t") == "SELECT 10.5 FROM t"
    assert _ok("SELECT aFROM FROM t") == "SELECT aFROM FROM t"
    assert _ok("SELECT ab cd FROM t") == "SELECT ab cd FROM t"
    assert _ok("SELECT a/*x*/b FROM t") == "SELECT a b FROM t"
    _bad("SELECT 'abc", "WATSON_SQL_TRANSPORT_UNCLOSED_STRING")
    _bad('SELECT "abc', "WATSON_SQL_TRANSPORT_UNCLOSED_IDENTIFIER")
    _bad("SELECT /* abc", "WATSON_SQL_TRANSPORT_UNCLOSED_COMMENT")
    _bad("   ")
    _bad("-- only comment")
    _bad("SELECT \x00")
    _bad("SELECT \x01")
    exact = "x" * 10_000
    assert len(_ok(exact)) == 10_000
    _bad("x" * 10_001, "WATSON_SQL_TRANSPORT_TOO_LARGE")
    _bad("é" * 20_001, "WATSON_SQL_TRANSPORT_TOO_LARGE")
    assert compact_sql_for_watson_transport("x" * 10_001, LIMITS).sql_transport is None
    original = "SELECT  a FROM t"
    assert original == "SELECT  a FROM t"
    assert _ok(original) == _ok(original)
    assert _ok(_ok("SELECT   a FROM t")) == "SELECT a FROM t"
    payload = build_watson_flow_payload("SELECT 1")
    assert payload == {"sql_query": "SELECT 1"}
    assert "limit" not in payload
    payload["sql_query"] = "changed"
    assert build_watson_flow_payload("SELECT 1")["sql_query"] == "SELECT 1"
    print("testar_watson_sql_transport.py: 37/37 OK")


if __name__ == "__main__":
    main()
