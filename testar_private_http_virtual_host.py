from __future__ import annotations

import unittest

from app.integrations.openai_compatible.configuration import (
    OpenAiCompatibleConfiguration,
    OpenAiCompatibleConfigurationError,
    load_openai_compatible_configuration,
)
from app.integrations.openai_compatible.client import OpenAiCompatibleClient
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret


class _Secrets:
    def get_secret(self, name):
        return {"status": "success", "secret": SensitiveSecret("dummy-for-test")}


class _Transport:
    def __init__(self):
        self.request = None

    def send(self, request):
        self.request = request
        return type("Result", (), {"status": "timeout", "response": None})()


class PrivateVirtualHostTests(unittest.TestCase):
    def test_explicit_host_for_private_ip(self):
        cfg = load_openai_compatible_configuration({
            "OPENAI_COMPATIBLE_SQL_ENABLED": "true",
            "OPENAI_COMPATIBLE_SQL_PROVIDER_KEY": "private",
            "OPENAI_COMPATIBLE_SQL_CONFIG_VERSION": "v1",
            "OPENAI_COMPATIBLE_SQL_MODEL": "sql-model",
            "OPENAI_COMPATIBLE_SQL_BASE_URL": "http://10.66.66.1",
            "OPENAI_COMPATIBLE_SQL_ALLOW_PRIVATE_HTTP": "true",
            "OPENAI_COMPATIBLE_SQL_HTTP_HOST": "chat.internal",
        })
        self.assertEqual(cfg.http_host, "chat.internal")
        transport = _Transport()
        client = OpenAiCompatibleClient(
            configuration=cfg, secret_provider=_Secrets(), http_transport=transport
        )
        client.generate_content({"instruction": "synthetic"})
        self.assertEqual(
            [(header.name, header.public_value) for header in transport.request.headers
             if header.name == "Host"],
            [("Host", "chat.internal")],
        )
        self.assertEqual(transport.request.url, "http://10.66.66.1/api/chat/completions")

    def test_default_does_not_override_host(self):
        cfg = OpenAiCompatibleConfiguration(
            provider_key="provider", config_version="v1",
            api_base_url="https://example.test", model_id="model"
        )
        transport = _Transport()
        OpenAiCompatibleClient(
            configuration=cfg, secret_provider=_Secrets(), http_transport=transport
        ).generate_content({"synthetic": True})
        self.assertFalse(any(header.name == "Host" for header in transport.request.headers))

    def test_host_rejected_on_https_or_without_private_opt_in(self):
        for options in [
            {"api_base_url": "https://example.test", "allow_private_http": False},
            {"api_base_url": "http://10.66.66.1", "allow_private_http": False},
        ]:
            with self.subTest(options=options):
                with self.assertRaises(OpenAiCompatibleConfigurationError):
                    OpenAiCompatibleConfiguration(
                        provider_key="provider", config_version="v1", model_id="model",
                        http_host="chat.internal", **options
                    )

    def test_malicious_hosts_rejected(self):
        for host in ["chat.internal\\r\\nX-Injection: yes", "chat.internal:80",
                     "user@chat.internal", "/chat.internal", "bad..internal",
                     "-bad.internal", "bad_.internal"]:
            with self.subTest(host=host):
                with self.assertRaises(OpenAiCompatibleConfigurationError):
                    OpenAiCompatibleConfiguration(
                        provider_key="provider", config_version="v1",
                        api_base_url="http://10.66.66.1", model_id="model",
                        allow_private_http=True, http_host=host
                    )


if __name__ == "__main__":
    unittest.main()
