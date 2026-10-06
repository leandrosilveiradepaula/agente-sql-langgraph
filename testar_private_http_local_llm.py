from __future__ import annotations

import unittest

from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfigurationError,
    load_openai_compatible_configuration,
)
from app.infrastructure.http.http_contracts import (
    HttpHeader,
    HttpTransportRequest,
)
from app.integrations.watson.flow_limits import WatsonFlowContractError


class PrivateHttpLocalLlmTests(unittest.TestCase):
    def test_http_private_ip_requires_explicit_opt_in(self):
        with self.assertRaises(OpenAiCompatibleConfigurationError):
            load_openai_compatible_configuration(
                {
                    "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
                    "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
                    "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
                    "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
                    "OPENAI_COMPATIBLE_SQL_BASE_URL": "http://192.168.1.214:3005",
                }
            )

    def test_http_private_ip_allowed_with_opt_in(self):
        configuration = load_openai_compatible_configuration(
            {
                "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
                "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
                "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
                "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
                "OPENAI_COMPATIBLE_SQL_BASE_URL": "http://192.168.1.214:3005",
                "OPENAI_COMPATIBLE_SQL_ALLOW_PRIVATE_HTTP": "true",
            }
        )

        self.assertIsNotNone(configuration)
        self.assertTrue(configuration.allow_private_http)

    def test_configuration_rejects_public_http_even_with_opt_in(self):
        with self.assertRaises(OpenAiCompatibleConfigurationError):
            load_openai_compatible_configuration(
                {
                    "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
                    "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
                    "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
                    "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
                    "OPENAI_COMPATIBLE_SQL_BASE_URL": "http://8.8.8.8:3005",
                    "OPENAI_COMPATIBLE_SQL_ALLOW_PRIVATE_HTTP": "true",
                }
            )

    def test_configuration_rejects_hostname_http_even_with_opt_in(self):
        with self.assertRaises(OpenAiCompatibleConfigurationError):
            load_openai_compatible_configuration(
                {
                    "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
                    "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "infodive_local",
                    "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "sql-infodive-demo-v1",
                    "OPENAI_COMPATIBLE_SQL_MODEL": "sql-infodive",
                    "OPENAI_COMPATIBLE_SQL_BASE_URL": "http://llm.internal:3005",
                    "OPENAI_COMPATIBLE_SQL_ALLOW_PRIVATE_HTTP": "true",
                }
            )

    def test_transport_rejects_public_http_even_with_opt_in(self):
        with self.assertRaises(WatsonFlowContractError):
            HttpTransportRequest(
                method="POST",
                url="http://8.8.8.8/api/chat/completions",
                headers=(HttpHeader("Content-Type", public_value="application/json"),),
                body=b"{}",
                connect_timeout_seconds=5,
                read_timeout_seconds=5,
                max_response_bytes=1000,
                operation_name="test",
                allow_private_http=True,
            )

    def test_transport_rejects_hostname_http_even_with_opt_in(self):
        with self.assertRaises(WatsonFlowContractError):
            HttpTransportRequest(
                method="POST",
                url="http://example.test/api/chat/completions",
                headers=(HttpHeader("Content-Type", public_value="application/json"),),
                body=b"{}",
                connect_timeout_seconds=5,
                read_timeout_seconds=5,
                max_response_bytes=1000,
                operation_name="test",
                allow_private_http=True,
            )

    def test_https_still_allowed_without_private_http_opt_in(self):
        request = HttpTransportRequest(
            method="POST",
            url="https://llm.example.test/api/chat/completions",
            headers=(HttpHeader("Content-Type", public_value="application/json"),),
            body=b"{}",
            connect_timeout_seconds=5,
            read_timeout_seconds=5,
            max_response_bytes=1000,
            operation_name="test",
        )

        self.assertFalse(request.allow_private_http)


if __name__ == "__main__":
    unittest.main()
