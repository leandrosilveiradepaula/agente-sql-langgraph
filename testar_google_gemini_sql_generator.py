from __future__ import annotations

import json
from copy import deepcopy

from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.adapters.testing.fake_secret_value_provider import (
    FakeSecretValueProvider,
)
from app.bootstrap import create_google_gemini_sql_generator
from app.domain.sql_generation import (
    SQL_GENERATION_CONTRACT_VERSION,
    SqlGenerationProviderError,
    validate_sql_generation_response,
)
from app.infrastructure.http.http_contracts import (
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
    materialize_headers,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.google_gemini.client import GoogleGeminiClient
from app.integrations.google_gemini.configuration import (
    GEMINI_API_KEY_SECRET_NAME,
    GoogleGeminiConfiguration,
    GoogleGeminiConfigurationError,
    build_gemini_generate_content_url,
    load_google_gemini_configuration,
)
from app.integrations.google_gemini.contracts import (
    GeminiContractError,
    build_gemini_payload,
    build_gemini_prompt,
)
from app.integrations.google_gemini.sql_generator_adapter import (
    GoogleGeminiSqlGeneratorAdapter,
)
from app.ports.secret_value_provider import secret_lookup_failure
from testar_sql_generation import _query_plan


SECRET_VALUE = "test-placeholder-gemini-key"


def _request() -> dict:
    from app.domain.sql_generation import build_sql_generation_request

    return build_sql_generation_request(_query_plan())


def _http_success(payload: dict, *, duration_ms: int = 7):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return http_transport_success(
        HttpTransportResponse(
            status_code=200,
            headers={"content-type": "application/json"},
            body=body,
            duration_ms=duration_ms,
        )
    )


def _client(*, transport_result):
    transport = FakeHttpTransport(result=transport_result)
    secret_provider = FakeSecretValueProvider(
        secret=SensitiveSecret(SECRET_VALUE)
    )
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(),
        secret_provider=secret_provider,
        http_transport=transport,
    )
    return client, transport, secret_provider


def _adapter_success(output_text: str = "SELECT id FROM schema_test.table_test"):
    client, transport, secret_provider = _client(
        transport_result=_http_success(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": output_text,
                                }
                            ]
                        },
                    }
                ]
            }
        )
    )
    return GoogleGeminiSqlGeneratorAdapter(client=client), transport, secret_provider


def _adapter_success_with_usage(
    output_text: str = "SELECT id FROM schema_test.table_test",
):
    client, transport, secret_provider = _client(
        transport_result=_http_success(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {
                                    "text": output_text,
                                }
                            ]
                        },
                    }
                ],
                "usageMetadata": {
                    "promptTokenCount": 11,
                    "candidatesTokenCount": 7,
                    "totalTokenCount": 18,
                },
            }
        )
    )
    return GoogleGeminiSqlGeneratorAdapter(client=client), transport, secret_provider


def _assert_domain_rejects(output_text: str, expected_code: str) -> None:
    adapter, _transport, _secret = _adapter_success(output_text)
    result = adapter.generate(_request())
    try:
        validate_sql_generation_response(result)
    except Exception as error:
        assert getattr(error, "code", None) == expected_code
    else:
        raise AssertionError(f"Era esperado {expected_code}.")


def _assert_config_error(**kwargs) -> None:
    try:
        GoogleGeminiConfiguration(**kwargs)
    except GoogleGeminiConfigurationError:
        pass
    else:
        raise AssertionError("Era esperado erro de configuracao.")


def test_configuracao_default_valida() -> None:
    config = GoogleGeminiConfiguration()

    assert config.api_base_url == "https://generativelanguage.googleapis.com"
    assert config.model_id == "gemini-2.5-flash"
    assert config.temperature == 0
    assert config.top_p == 0.1
    assert config.top_k == 1
    assert config.max_output_tokens == 8192
    assert config.response_mime_type == "text/plain"
    assert config.thinking_budget == 0
    assert build_gemini_generate_content_url(config).endswith(
        "/v1beta/models/gemini-2.5-flash:generateContent"
    )


def test_configuracao_rejeita_invalidos() -> None:
    _assert_config_error(api_base_url="")
    _assert_config_error(api_base_url="http://example.invalid")
    _assert_config_error(model_id="")
    _assert_config_error(connect_timeout_seconds=0)
    _assert_config_error(read_timeout_seconds=0)
    _assert_config_error(temperature=-0.1)
    _assert_config_error(temperature=2.1)
    _assert_config_error(top_p=-0.1)
    _assert_config_error(top_p=1.1)
    _assert_config_error(top_k=0)
    _assert_config_error(max_output_tokens=0)
    _assert_config_error(response_mime_type="")
    _assert_config_error(thinking_budget=-1)


def test_loader_usa_defaults_e_env_nao_sensiveis() -> None:
    config = load_google_gemini_configuration(
        {
            "GEMINI_API_BASE_URL": "https://example.invalid",
            "GEMINI_SQL_GENERATOR_MODEL": "generic-model",
            "GEMINI_CONNECT_TIMEOUT_SECONDS": "6",
            "GEMINI_READ_TIMEOUT_SECONDS": "11",
            "GEMINI_MAX_OUTPUT_TOKENS": "123",
            "GEMINI_API_KEY": SECRET_VALUE,
        }
    )

    assert config.api_base_url == "https://example.invalid"
    assert config.model_id == "generic-model"
    assert config.connect_timeout_seconds == 6
    assert config.read_timeout_seconds == 11
    assert config.max_output_tokens == 123
    assert SECRET_VALUE not in repr(config)


def test_payload_deterministico_e_derivado_da_request() -> None:
    request = _request()
    first = build_gemini_payload(
        request=request,
        configuration=GoogleGeminiConfiguration(),
    )
    second = build_gemini_payload(
        request=deepcopy(request),
        configuration=GoogleGeminiConfiguration(),
    )
    payload = json.loads(first.decode("utf-8"))
    prompt = payload["contents"][0]["parts"][0]["text"]

    assert first == second
    assert build_gemini_prompt(request) == prompt
    assert request["contract_version"] in prompt
    assert "grouping_dimensions" in prompt
    assert "target_table e target_column" in prompt
    assert "GraphState" not in prompt
    assert "authorization" not in prompt.casefold()
    assert "headers" not in prompt.casefold()
    assert SECRET_VALUE not in prompt
    assert payload["generationConfig"]["temperature"] == 0
    assert payload["generationConfig"]["topP"] == 0.1
    assert payload["generationConfig"]["topK"] == 1
    assert payload["generationConfig"]["maxOutputTokens"] == 8192
    assert payload["generationConfig"]["responseMimeType"] == "text/plain"
    assert (
        payload["generationConfig"]["thinkingConfig"]["thinkingBudget"]
        == 0
    )


def test_payload_rejeita_objeto_nao_serializavel() -> None:
    class NonSerializable:
        pass

    request = _request()
    request["generation_context"]["selected_pattern"] = {
        "bad": NonSerializable()
    }

    try:
        build_gemini_payload(
            request=request,
            configuration=GoogleGeminiConfiguration(),
        )
    except GeminiContractError as error:
        serialized = repr(error)
        assert "NonSerializable" not in serialized
        assert "object at 0x" not in serialized
        assert "selected_pattern" not in serialized
    else:
        raise AssertionError("Era esperado erro de contrato Gemini.")


def test_client_serializacao_invalida_nao_chama_http() -> None:
    class NonSerializable:
        pass

    request = _request()
    request["generation_context"]["selected_pattern"] = {
        "bad": NonSerializable()
    }
    transport = FakeHttpTransport(
        result=_http_success(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "SELECT 1"}]}}
                ]
            }
        )
    )
    secret_provider = FakeSecretValueProvider(
        secret=SensitiveSecret(SECRET_VALUE)
    )
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(),
        secret_provider=secret_provider,
        http_transport=transport,
    )

    result = client.generate_content(request)

    assert result["status"] == "unexpected_error"
    assert transport.calls == 0
    assert "NonSerializable" not in repr(result)
    assert "object at 0x" not in repr(result)
    assert SECRET_VALUE not in repr(result)


def test_client_sucesso_monta_http_sem_vazar_chave() -> None:
    client, transport, secret_provider = _client(
        transport_result=_http_success(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": " SELECT id "},
                                {"inlineData": {"mimeType": "text/plain"}},
                                {"text": "FROM schema_test.table_test "},
                            ]
                        },
                    }
                ]
            },
            duration_ms=9,
        )
    )

    result = client.generate_content(_request())

    assert result["status"] == "success"
    assert result["output_text"] == "SELECT id FROM schema_test.table_test"
    assert result["duration_ms"] == 9
    assert result["token_usage"] == {
        "provider": "google_gemini",
        "model": "gemini-2.5-flash",
        "prompt_tokens": None,
        "response_tokens": None,
        "total_tokens": None,
    }
    assert transport.calls == 1
    assert secret_provider.calls == 1
    assert secret_provider.secret_names == [GEMINI_API_KEY_SECRET_NAME]
    sent = transport.last_request
    assert sent is not None
    assert sent.url == (
        "https://generativelanguage.googleapis.com"
        "/v1beta/models/gemini-2.5-flash:generateContent"
    )
    assert SECRET_VALUE not in repr(sent)
    assert SECRET_VALUE in materialize_headers(sent.headers)["x-goog-api-key"]


def test_client_usa_somente_primeiro_candidate() -> None:
    client, _transport, _secret = _client(
        transport_result=_http_success(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "SELECT 1"},
                            ]
                        },
                    },
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "SELECT 2"},
                            ]
                        },
                    },
                ]
            }
        )
    )

    result = client.generate_content(_request())

    assert result["status"] == "success"
    assert result["output_text"] == "SELECT 1"
    assert "SELECT 2" not in result["output_text"]


def test_client_nao_usa_segundo_candidate_como_fallback() -> None:
    client, _transport, _secret = _client(
        transport_result=_http_success(
            {
                "candidates": [
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"inlineData": {"mimeType": "text/plain"}},
                            ]
                        },
                    },
                    {
                        "finishReason": "STOP",
                        "content": {
                            "parts": [
                                {"text": "SELECT 2"},
                            ]
                        },
                    },
                ]
            }
        )
    )

    result = client.generate_content(_request())

    assert result["status"] == "invalid_response"
    assert "SELECT 2" not in repr(result)


def test_client_rejeita_envelopes_invalidos() -> None:
    cases = [
        {},
        {"candidates": []},
        {"candidates": [{"content": {}}]},
        {"candidates": [{"content": {"parts": []}}]},
        {"candidates": [{"content": {"parts": [{}]}}]},
        {"candidates": [{"content": {"parts": [{"text": "   "}]} } ]},
    ]
    for payload in cases:
        client, _transport, _secret = _client(
            transport_result=_http_success(payload)
        )
        result = client.generate_content(_request())
        assert result["status"] == "invalid_response"
        assert SECRET_VALUE not in repr(result)


def test_client_rejeita_json_invalido() -> None:
    transport = FakeHttpTransport(
        result=http_transport_success(
            HttpTransportResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b"{",
                duration_ms=1,
            )
        )
    )
    secret_provider = FakeSecretValueProvider(
        secret=SensitiveSecret(SECRET_VALUE)
    )
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(),
        secret_provider=secret_provider,
        http_transport=transport,
    )

    result = client.generate_content(_request())

    assert result["status"] == "invalid_response"
    assert SECRET_VALUE not in repr(result)


def test_client_rejeita_utf8_invalido() -> None:
    transport = FakeHttpTransport(
        result=http_transport_success(
            HttpTransportResponse(
                status_code=200,
                headers={"content-type": "application/json"},
                body=b"\xff",
                duration_ms=1,
            )
        )
    )
    secret_provider = FakeSecretValueProvider(
        secret=SensitiveSecret(SECRET_VALUE)
    )
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(),
        secret_provider=secret_provider,
        http_transport=transport,
    )

    result = client.generate_content(_request())

    assert result["status"] == "invalid_response"
    assert transport.calls == 1
    assert SECRET_VALUE not in repr(result)


def test_client_mapeia_http_e_transporte_sem_retry() -> None:
    http_cases = [
        (400, "http_error"),
        (401, "authentication_failed"),
        (403, "authentication_failed"),
        (429, "rate_limited"),
        (500, "provider_unavailable"),
    ]
    for status_code, expected in http_cases:
        client, transport, _secret = _client(
            transport_result=http_transport_success(
                HttpTransportResponse(
                    status_code=status_code,
                    headers={"content-type": "application/json"},
                    body=b"{}",
                    duration_ms=2,
                )
            )
        )
        result = client.generate_content(_request())
        assert result["status"] == expected
        assert transport.calls == 1
        assert SECRET_VALUE not in repr(result)

    client, transport, _secret = _client(
        transport_result=http_transport_failure("timeout")
    )
    result = client.generate_content(_request())
    assert result["status"] == "transport_timeout"
    assert transport.calls == 1

    client, transport, _secret = _client(
        transport_result=http_transport_failure("connection_failure")
    )
    result = client.generate_content(_request())
    assert result["status"] == "transport_unavailable"
    assert transport.calls == 1

    for transport_status, expected in [
        ("response_too_large", "invalid_response"),
        ("dns_failure", "transport_unavailable"),
        ("tls_failure", "transport_unavailable"),
    ]:
        client, transport, _secret = _client(
            transport_result=http_transport_failure(transport_status)
        )
        result = client.generate_content(_request())
        assert result["status"] == expected
        assert transport.calls == 1


def test_client_secret_ausente_nao_chama_http() -> None:
    transport = FakeHttpTransport(
        result=_http_success(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "SELECT 1"}]}}
                ]
            }
        )
    )
    secret_provider = FakeSecretValueProvider(
        result=secret_lookup_failure("missing")
    )
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(),
        secret_provider=secret_provider,
        http_transport=transport,
    )

    result = client.generate_content(_request())

    assert result["status"] == "secret_missing"
    assert transport.calls == 0
    assert SECRET_VALUE not in repr(result)


def test_client_secret_unavailable_e_invalid_nao_chamam_http() -> None:
    for secret_status, expected in [
        ("unavailable", "secret_unavailable"),
        ("invalid", "secret_invalid"),
    ]:
        transport = FakeHttpTransport(
            result=_http_success(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "SELECT 1"}]}}
                    ]
                }
            )
        )
        secret_provider = FakeSecretValueProvider(
            result=secret_lookup_failure(secret_status)
        )
        client = GoogleGeminiClient(
            configuration=GoogleGeminiConfiguration(),
            secret_provider=secret_provider,
            http_transport=transport,
        )

        result = client.generate_content(_request())

        assert result["status"] == expected
        assert transport.calls == 0
        assert SECRET_VALUE not in repr(result)


def test_adapter_implementa_sql_generator_e_nao_raw_response() -> None:
    adapter, transport, _secret = _adapter_success()

    result = adapter.generate(_request())

    assert result == {
        "provider_name": "google_gemini",
        "provider_model": "gemini-2.5-flash",
        "output_text": "SELECT id FROM schema_test.table_test",
        "duration_ms": 7,
        "token_usage": {
            "provider": "google_gemini",
            "model": "gemini-2.5-flash",
            "prompt_tokens": None,
            "response_tokens": None,
            "total_tokens": None,
        },
    }
    assert "raw_response" not in result
    assert transport.calls == 1
    assert validate_sql_generation_response(result) == (
        "SELECT id FROM schema_test.table_test"
    )


def test_adapter_mapeia_usage_metadata() -> None:
    adapter, _transport, _secret = _adapter_success_with_usage()

    result = adapter.generate(_request())

    assert result["provider_model"] == "gemini-2.5-flash"
    assert result["token_usage"] == {
        "provider": "google_gemini",
        "model": "gemini-2.5-flash",
        "prompt_tokens": 11,
        "response_tokens": 7,
        "total_tokens": 18,
    }


def test_adapter_rejeita_contract_version_invalido() -> None:
    adapter, transport, _secret = _adapter_success()
    request = _request()
    request["contract_version"] = "invalid"

    try:
        adapter.generate(request)
    except SqlGenerationProviderError as error:
        assert SECRET_VALUE not in repr(error)
    else:
        raise AssertionError("Era esperado erro de provider.")

    assert transport.calls == 0


def test_adapter_nao_limpa_respostas_invalidas_do_modelo() -> None:
    adapter, _transport, _secret = _adapter_success(
        "```sql\nSELECT id FROM schema_test.table_test\n```"
    )

    result = adapter.generate(_request())

    assert result["output_text"].startswith("```sql")
    try:
        validate_sql_generation_response(result)
    except Exception:
        pass
    else:
        raise AssertionError("Markdown deveria ser rejeitado pelo dominio.")


def test_adapter_deixa_dominio_rejeitar_sql_invalida() -> None:
    cases = [
        (
            "CREATE TABLE schema_test.table_test (id int)",
            "SQL_GENERATION_NON_READ_ONLY",
        ),
        (
            "UPDATE schema_test.table_test SET id = 1",
            "SQL_GENERATION_NON_READ_ONLY",
        ),
        (
            "SELECT id FROM schema_test.table_test; SELECT id FROM schema_test.table_test",
            "SQL_GENERATION_MULTIPLE_STATEMENTS",
        ),
        (
            "Aqui esta a SQL: SELECT id FROM schema_test.table_test",
            "SQL_GENERATION_RESPONSE_INVALID",
        ),
    ]
    for output_text, expected_code in cases:
        _assert_domain_rejects(output_text, expected_code)


def test_adapter_duration_ms_invalida_vira_zero() -> None:
    class DurationClient:
        def __init__(self, duration_ms):
            self.duration_ms = duration_ms

        def generate_content(self, request):
            assert request["contract_version"] == SQL_GENERATION_CONTRACT_VERSION
            return {
                "status": "success",
                "output_text": "SELECT 1",
                "duration_ms": self.duration_ms,
            }

    for value in (True, -1):
        adapter = GoogleGeminiSqlGeneratorAdapter(
            client=DurationClient(value)
        )
        result = adapter.generate(_request())
        assert result["duration_ms"] == 0


def test_adapter_propaga_falha_sanitizada_do_client() -> None:
    class FailingClient:
        def generate_content(self, request):
            assert request["contract_version"] == SQL_GENERATION_CONTRACT_VERSION
            return {
                "status": "authentication_failed",
                "public_error_message": f"never {SECRET_VALUE}",
            }

    adapter = GoogleGeminiSqlGeneratorAdapter(client=FailingClient())

    try:
        adapter.generate(_request())
    except SqlGenerationProviderError as error:
        serialized = repr(error)
        assert SECRET_VALUE not in serialized
        assert "never" not in serialized
    else:
        raise AssertionError("Era esperado erro de provider.")


def test_factory_explicita_nao_acessa_secret_ou_rede() -> None:
    transport = FakeHttpTransport(
        result=_http_success(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "SELECT 1"}]}}
                ]
            }
        )
    )
    secret_provider = FakeSecretValueProvider(
        secret=SensitiveSecret(SECRET_VALUE)
    )

    adapter = create_google_gemini_sql_generator(
        {"GEMINI_API_BASE_URL": "https://example.invalid"},
        secret_provider=secret_provider,
        http_transport=transport,
    )

    assert adapter.__class__.__name__ == "GoogleGeminiSqlGeneratorAdapter"
    assert secret_provider.calls == 0
    assert transport.calls == 0


def test_reprs_nao_expoem_config_client_ou_secret() -> None:
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(
            api_base_url="https://example.invalid",
            model_id="generic-model",
        ),
        secret_provider=FakeSecretValueProvider(
            secret=SensitiveSecret(SECRET_VALUE)
        ),
        http_transport=FakeHttpTransport(
            result=_http_success(
                {
                    "candidates": [
                        {"content": {"parts": [{"text": "SELECT 1"}]}}
                    ]
                }
            )
        ),
    )
    adapter = GoogleGeminiSqlGeneratorAdapter(client=client)

    assert repr(client) == "GoogleGeminiClient(<safe>)"
    assert repr(adapter) == "GoogleGeminiSqlGeneratorAdapter(<safe>)"
    assert "example.invalid" not in repr(client)
    assert "generic-model" not in repr(client)
    assert SECRET_VALUE not in repr(client)
    assert "GoogleGeminiClient" not in repr(adapter).replace(
        "GoogleGeminiSqlGeneratorAdapter",
        "",
    )
    assert SECRET_VALUE not in repr(adapter)


def main() -> None:
    tests = [
        ("config default", test_configuracao_default_valida),
        ("config invalidos", test_configuracao_rejeita_invalidos),
        ("loader env nao sensivel", test_loader_usa_defaults_e_env_nao_sensiveis),
        ("payload deterministico", test_payload_deterministico_e_derivado_da_request),
        ("payload rejeita objeto", test_payload_rejeita_objeto_nao_serializavel),
        ("client serializacao invalida", test_client_serializacao_invalida_nao_chama_http),
        ("client sucesso", test_client_sucesso_monta_http_sem_vazar_chave),
        ("primeiro candidate", test_client_usa_somente_primeiro_candidate),
        ("sem fallback candidate", test_client_nao_usa_segundo_candidate_como_fallback),
        ("envelopes invalidos", test_client_rejeita_envelopes_invalidos),
        ("json invalido", test_client_rejeita_json_invalido),
        ("utf8 invalido", test_client_rejeita_utf8_invalido),
        ("http e transporte", test_client_mapeia_http_e_transporte_sem_retry),
        ("secret ausente", test_client_secret_ausente_nao_chama_http),
        ("secret unavailable invalid", test_client_secret_unavailable_e_invalid_nao_chamam_http),
        ("adapter sucesso", test_adapter_implementa_sql_generator_e_nao_raw_response),
        ("adapter usage metadata", test_adapter_mapeia_usage_metadata),
        ("contract invalido", test_adapter_rejeita_contract_version_invalido),
        ("adapter nao limpa", test_adapter_nao_limpa_respostas_invalidas_do_modelo),
        ("dominio rejeita invalidas", test_adapter_deixa_dominio_rejeitar_sql_invalida),
        ("duration invalida", test_adapter_duration_ms_invalida_vira_zero),
        ("falha sanitizada", test_adapter_propaga_falha_sanitizada_do_client),
        ("factory explicita", test_factory_explicita_nao_acessa_secret_ou_rede),
        ("repr seguro", test_reprs_nao_expoem_config_client_ou_secret),
    ]
    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()
