from __future__ import annotations

import http.client
import socket
import ssl
import time
from urllib.parse import urlsplit

from app.infrastructure.http.http_contracts import (
    HttpTransportRequest,
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
    materialize_headers,
    sanitize_response_headers,
)


class StdlibHttpTransport:
    """
    Transporte HTTPS sincronico com stdlib, sem proxy, pool, redirect ou retry.
    """

    def __init__(self, *, connection_factory=None, ssl_context=None) -> None:
        self._connection_factory = connection_factory or http.client.HTTPSConnection
        if ssl_context is None:
            ssl_context = ssl.create_default_context()
        if getattr(ssl_context, "check_hostname", True) is not True:
            raise ValueError("TLS deve verificar hostname.")
        if getattr(ssl_context, "verify_mode", ssl.CERT_REQUIRED) == ssl.CERT_NONE:
            raise ValueError("TLS nao pode usar CERT_NONE.")
        self._ssl_context = ssl_context

    def __repr__(self) -> str:
        return "StdlibHttpTransport(<safe>)"

    def send(self, request: HttpTransportRequest):
        connection = None
        start = time.monotonic()
        try:
            parsed = urlsplit(request.url)
            path = parsed.path or "/"
            if parsed.query:
                path = f"{path}?{parsed.query}"
            connection = self._connection_factory(
                parsed.hostname,
                parsed.port,
                timeout=request.connect_timeout_seconds,
                context=self._ssl_context,
            )
            headers = materialize_headers(request.headers)
            headers["Content-Length"] = str(len(request.body))
            headers["Connection"] = "close"
            headers["Accept-Encoding"] = "identity"
            connection.request(request.method, path, body=request.body, headers=headers)
            if getattr(connection, "sock", None) is not None:
                connection.sock.settimeout(request.read_timeout_seconds)
            response = connection.getresponse()
            response_headers = sanitize_response_headers(dict(response.getheaders()))
            content_encoding = response_headers.get("content-encoding", "identity")
            if content_encoding.casefold() not in {"", "identity"}:
                return http_transport_failure("invalid_response")
            declared_length = response_headers.get("content-length")
            if declared_length is None:
                raw_declared = response.getheader("Content-Length")
                declared_length = raw_declared if isinstance(raw_declared, str) else None
            if declared_length is not None:
                try:
                    expected_length = int(declared_length)
                except ValueError:
                    return http_transport_failure("invalid_response")
                if expected_length < 0:
                    return http_transport_failure("invalid_response")
                if expected_length > request.max_response_bytes:
                    return http_transport_failure("response_too_large")
            else:
                expected_length = None
            chunks: list[bytes] = []
            total = 0
            while True:
                chunk = response.read(8192)
                if chunk == b"":
                    break
                if not isinstance(chunk, bytes):
                    return http_transport_failure("invalid_response")
                total += len(chunk)
                if total > request.max_response_bytes:
                    return http_transport_failure("response_too_large")
                chunks.append(chunk)
            body = b"".join(chunks)
            if expected_length is not None and len(body) != expected_length:
                return http_transport_failure("invalid_response")
            duration_ms = int((time.monotonic() - start) * 1000)
            return http_transport_success(
                HttpTransportResponse(
                    status_code=response.status,
                    headers=response_headers,
                    body=body,
                    duration_ms=duration_ms,
                )
            )
        except socket.timeout:
            return http_transport_failure("timeout")
        except TimeoutError:
            return http_transport_failure("timeout")
        except socket.gaierror:
            return http_transport_failure("dns_failure")
        except ssl.SSLError:
            return http_transport_failure("tls_failure")
        except (ConnectionError, OSError):
            return http_transport_failure("connection_failure")
        except Exception:
            return http_transport_failure("unexpected_error")
        finally:
            if connection is not None:
                try:
                    connection.close()
                except Exception:
                    pass
