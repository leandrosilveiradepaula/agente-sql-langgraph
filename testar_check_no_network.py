from __future__ import annotations

import sys

import scripts.check_no_network as check


def _guarded(code: str):
    return check.run_guarded([sys.executable, "-c", code], capture=True)


def main() -> None:
    assert _guarded("import socket; s=socket.socket(); s.connect(('example.invalid', 443))").returncode != 0
    assert _guarded("import socket; socket.create_connection(('example.invalid', 443))").returncode != 0
    result = _guarded("import socket; socket.getaddrinfo('example.invalid', 443)")
    assert result.returncode != 0
    assert "example.invalid" not in result.stderr
    assert _guarded("import http.client; c=http.client.HTTPConnection('example.invalid'); c.connect()").returncode != 0
    assert _guarded("import http.client; c=http.client.HTTPSConnection('example.invalid'); c.connect()").returncode != 0
    assert _guarded("import urllib.request; urllib.request.urlopen('https://example.invalid')").returncode != 0
    assert _guarded("import app.bootstrap; print('imports-ok')").returncode == 0
    assert _guarded("from pathlib import Path; Path('tmp_network_guard_test.txt').write_text('x'); Path('tmp_network_guard_test.txt').unlink()").returncode == 0
    assert _guarded("from app.adapters.testing.fake_http_transport import FakeHttpTransport; print(FakeHttpTransport(result={'status':'timeout'}))").returncode == 0
    assert _guarded("import http.client; http.client.HTTPSConnection = object; print('mock-ok')").returncode == 0
    assert "NETWORK_BLOCKED_OFFLINE_TEST" in result.stderr
    assert check.run_guarded([sys.executable, "-c", "print('ok')"], capture=True).returncode == 0
    print("testar_check_no_network.py: 12/12 OK")


if __name__ == "__main__":
    main()
