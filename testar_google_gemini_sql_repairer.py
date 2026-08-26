from __future__ import annotations

import json
from copy import deepcopy

from app.adapters.testing.fake_http_transport import FakeHttpTransport
from app.adapters.testing.fake_secret_value_provider import (
    FakeSecretValueProvider,
)
from app.bootstrap import create_google_gemini_sql_repairer
from app.domain.sql_repair import (
    SqlRepairProviderError,
    sql_fingerprint,
    validate_sql_repair_response,
)
from app.graph.nodes.repair_sql import create_repair_sql_node
from app.infrastructure.http.http_contracts import (
    HttpTransportResponse,
    http_transport_failure,
    http_transport_success,
)
from app.infrastructure.secrets.sensitive_secret import SensitiveSecret
from app.integrations.google_gemini.client import GoogleGeminiClient
from app.integrations.google_gemini.configuration import (
    GEMINI_API_KEY_SECRET_NAME,
    GoogleGeminiConfiguration,
    load_google_gemini_configuration,
    load_google_gemini_repairer_configuration,
)
from app.integrations.google_gemini.contracts import (
    GeminiContractError,
    build_gemini_repair_payload,
    build_gemini_repair_prompt,
)
from app.integrations.google_gemini.sql_repairer_adapter import (
    GoogleGeminiSqlRepairerAdapter,
)
from app.ports.secret_value_provider import secret_lookup_failure
from testar_repair_sql import CURRENT_SQL, REPAIRED_SQL, _state
from testar_sql_repair import _repair_request


SECRET_VALUE = "test-placeholder-gemini-key"


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


def _success_payload(output_text: str = REPAIRED_SQL) -> dict:
    return {
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


def _success_payload_with_usage(output_text: str = REPAIRED_SQL) -> dict:
    payload = _success_payload(output_text)
    payload["usageMetadata"] = {
        "promptTokenCount": 13,
        "candidatesTokenCount": 5,
        "totalTokenCount": 18,
    }
    return payload


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


def _adapter_success(output_text: str = REPAIRED_SQL):
    client, transport, secret_provider = _client(
        transport_result=_http_success(_success_payload(output_text))
    )
    return GoogleGeminiSqlRepairerAdapter(client=client), transport, secret_provider


def _payload(request: dict | None = None) -> dict:
    raw = build_gemini_repair_payload(
        request=request or _repair_request(),
        configuration=GoogleGeminiConfiguration(),
    )
    return json.loads(raw.decode("utf-8"))


def _prompt(request: dict | None = None) -> str:
    return _payload(request)["contents"][0]["parts"][0]["text"]


def _assert_provider_error(adapter, request) -> None:
    try:
        adapter.repair(request)
    except SqlRepairProviderError as error:
        assert SECRET_VALUE not in repr(error)
    else:
        raise AssertionError("Era esperado erro de provider.")


def _assert_domain_rejects(output_text: str, expected_code: str, *, history=None) -> None:
    adapter, _transport, _secret = _adapter_success(output_text)
    result = adapter.repair(_repair_request())
    try:
        validate_sql_repair_response(
            provider_result=result,
            current_sql=CURRENT_SQL,
            repair_history=history or [],
        )
    except Exception as error:
        assert getattr(error, "code", None) == expected_code
    else:
        raise AssertionError(f"Era esperado {expected_code}.")


def test_configuracao_default_do_repairer() -> None:
    config = load_google_gemini_repairer_configuration({})

    assert config.model_id == "gemini-2.5-flash"
    assert config.temperature == 0
    assert config.top_p == 0.1
    assert config.top_k == 1
    assert config.max_output_tokens == 8192
    assert config.response_mime_type == "text/plain"
    assert config.thinking_budget == 0


def test_modelo_repairer_customizado() -> None:
    config = load_google_gemini_repairer_configuration(
        {"GEMINI_SQL_REPAIRER_MODEL": "gemini-repair-test"}
    )

    assert config.model_id == "gemini-repair-test"


def test_generator_e_repairer_podem_usar_modelos_diferentes() -> None:
    env = {
        "GEMINI_SQL_GENERATOR_MODEL": "gemini-generator-test",
        "GEMINI_SQL_REPAIRER_MODEL": "gemini-repair-test",
    }

    generator = load_google_gemini_configuration(env)
    repairer = load_google_gemini_repairer_configuration(env)

    assert generator.model_id == "gemini-generator-test"
    assert repairer.model_id == "gemini-repair-test"


def test_payload_deterministico() -> None:
    request = _repair_request()

    first = build_gemini_repair_payload(
        request=request,
        configuration=GoogleGeminiConfiguration(),
    )
    second = build_gemini_repair_payload(
        request=deepcopy(request),
        configuration=GoogleGeminiConfiguration(),
    )

    assert first == second
    assert build_gemini_repair_prompt(request) == _prompt(request)


def test_payload_contem_current_sql() -> None:
    assert CURRENT_SQL in _prompt()


def test_payload_contem_attempt_e_max_attempts() -> None:
    prompt = _prompt()

    assert '"attempt":1' in prompt
    assert '"max_attempts":2' in prompt


def test_payload_contem_repair_context() -> None:
    prompt = _prompt()

    assert '"repair_context"' in prompt
    assert "schema_test.table_test" in prompt


def test_payload_contem_failure_estruturado() -> None:
    prompt = _prompt()

    assert '"failure"' in prompt
    assert '"category":"column_not_found"' in prompt


def test_payload_contem_previous_attempts() -> None:
    request = _repair_request(
        repair_history=[
            {
                "attempt": 1,
                "failed_stage": "engine_preflight",
                "failure_category": "column_not_found",
                "sql_before_fingerprint": sql_fingerprint(CURRENT_SQL),
                "sql_after_fingerprint": sql_fingerprint(REPAIRED_SQL),
                "request_fingerprint": "a" * 64,
                "response_fingerprint": "b" * 64,
                "repair_applied": True,
                "reason": "sql_repair_applied",
                "provider_name": "fake_sql_repairer",
                "errors": [],
                "warnings": [],
            }
        ],
        repair_attempts=1,
        max_repair_attempts=2,
    )

    prompt = _prompt(request)

    assert '"previous_attempts"' in prompt
    assert '"attempt":1' in prompt
    assert sql_fingerprint(REPAIRED_SQL) in prompt


def test_payload_contem_instructions_e_output_constraints() -> None:
    prompt = _prompt()

    assert '"instructions"' in prompt
    assert '"output_constraints"' in prompt
    assert "Retorne exatamente uma SQL" in prompt


def test_payload_nao_contem_graphstate() -> None:
    assert "GraphState" not in _prompt()


def test_payload_nao_contem_segredo_ou_header() -> None:
    prompt = _prompt()

    assert SECRET_VALUE not in prompt
    assert "x-goog-api-key" not in prompt.casefold()
    assert "authorization" not in prompt.casefold()
    assert "headers" not in prompt.casefold()


def test_objeto_nao_serializavel_falha_antes_de_http() -> None:
    class NonSerializable:
        pass

    request = _repair_request()
    request["repair_context"]["selected_pattern"] = {"bad": NonSerializable()}
    transport = FakeHttpTransport(
        result=_http_success(_success_payload("SELECT 1"))
    )
    secret_provider = FakeSecretValueProvider(
        secret=SensitiveSecret(SECRET_VALUE)
    )
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(),
        secret_provider=secret_provider,
        http_transport=transport,
    )

    result = client.generate_content(
        request,
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == "unexpected_error"
    assert transport.calls == 0
    assert "NonSerializable" not in repr(result)
    assert SECRET_VALUE not in repr(result)


def test_secret_missing_nao_chama_http() -> None:
    _assert_secret_failure("missing", "secret_missing")


def test_secret_unavailable_nao_chama_http() -> None:
    _assert_secret_failure("unavailable", "secret_unavailable")


def test_secret_invalid_nao_chama_http() -> None:
    _assert_secret_failure("invalid", "secret_invalid")


def _assert_secret_failure(secret_status: str, expected_status: str) -> None:
    transport = FakeHttpTransport(
        result=_http_success(_success_payload("SELECT 1"))
    )
    secret_provider = FakeSecretValueProvider(
        result=secret_lookup_failure(secret_status)
    )
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(),
        secret_provider=secret_provider,
        http_transport=transport,
    )

    result = client.generate_content(
        _repair_request(),
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == expected_status
    assert transport.calls == 0
    assert SECRET_VALUE not in repr(result)


def test_sucesso_usa_somente_primeiro_candidate() -> None:
    client, _transport, _secret = _client(
        transport_result=_http_success(
            {
                "candidates": [
                    {"content": {"parts": [{"text": "SELECT 1"}]}},
                    {"content": {"parts": [{"text": "SELECT 2"}]}},
                ]
            }
        )
    )

    result = client.generate_content(
        _repair_request(),
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == "success"
    assert result["output_text"] == "SELECT 1"
    assert "SELECT 2" not in result["output_text"]


def test_segundo_candidate_nao_e_fallback() -> None:
    client, _transport, _secret = _client(
        transport_result=_http_success(
            {
                "candidates": [
                    {"content": {"parts": [{"inlineData": {}}]}},
                    {"content": {"parts": [{"text": "SELECT 2"}]}},
                ]
            }
        )
    )

    result = client.generate_content(
        _repair_request(),
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == "invalid_response"
    assert "SELECT 2" not in repr(result)


def test_json_invalido() -> None:
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

    result = client.generate_content(
        _repair_request(),
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == "invalid_response"
    assert SECRET_VALUE not in repr(result)


def test_utf8_invalido() -> None:
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

    result = client.generate_content(
        _repair_request(),
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == "invalid_response"
    assert transport.calls == 1


def test_http_401_403() -> None:
    for status_code in (401, 403):
        _assert_http_status(status_code, "authentication_failed")


def test_http_429() -> None:
    _assert_http_status(429, "rate_limited")


def test_http_5xx() -> None:
    _assert_http_status(500, "provider_unavailable")


def _assert_http_status(status_code: int, expected: str) -> None:
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

    result = client.generate_content(
        _repair_request(),
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == expected
    assert transport.calls == 1
    assert SECRET_VALUE not in repr(result)


def test_timeout() -> None:
    _assert_transport_failure("timeout", "transport_timeout")


def test_dns_tls_failure() -> None:
    for status in ("dns_failure", "tls_failure"):
        _assert_transport_failure(status, "transport_unavailable")


def test_response_too_large() -> None:
    _assert_transport_failure("response_too_large", "invalid_response")


def _assert_transport_failure(status: str, expected: str) -> None:
    client, transport, _secret = _client(
        transport_result=http_transport_failure(status)
    )

    result = client.generate_content(
        _repair_request(),
        payload_builder=build_gemini_repair_payload,
    )

    assert result["status"] == expected
    assert transport.calls == 1


def test_adapter_retorna_provider_output_e_duration() -> None:
    adapter, transport, secret_provider = _adapter_success()

    result = adapter.repair(_repair_request())

    assert result == {
        "provider_name": "google_gemini",
        "provider_model": "gemini-2.5-flash",
        "output_text": REPAIRED_SQL,
        "duration_ms": 7,
        "token_usage": {
            "provider": "google_gemini",
            "model": "gemini-2.5-flash",
            "prompt_tokens": None,
            "response_tokens": None,
            "total_tokens": None,
        },
    }
    assert transport.calls == 1
    assert secret_provider.secret_names == [GEMINI_API_KEY_SECRET_NAME]


def test_adapter_mapeia_usage_metadata() -> None:
    client, _transport, _secret = _client(
        transport_result=_http_success(_success_payload_with_usage())
    )
    adapter = GoogleGeminiSqlRepairerAdapter(client=client)

    result = adapter.repair(_repair_request())

    assert result["provider_model"] == "gemini-2.5-flash"
    assert result["token_usage"] == {
        "provider": "google_gemini",
        "model": "gemini-2.5-flash",
        "prompt_tokens": 13,
        "response_tokens": 5,
        "total_tokens": 18,
    }


def test_raw_response_ausente() -> None:
    adapter, _transport, _secret = _adapter_success()

    result = adapter.repair(_repair_request())

    assert "raw_response" not in result


def test_adapter_nao_limpa_markdown() -> None:
    adapter, _transport, _secret = _adapter_success(
        "```sql\nSELECT id FROM schema_test.table_test\n```"
    )

    result = adapter.repair(_repair_request())

    assert result["output_text"].startswith("```sql")


def test_dominio_rejeita_ddl() -> None:
    _assert_domain_rejects(
        "CREATE TABLE schema_test.table_test (id int)",
        "SQL_REPAIR_NON_READ_ONLY",
    )


def test_dominio_rejeita_dml() -> None:
    _assert_domain_rejects(
        "UPDATE schema_test.table_test SET id = 1",
        "SQL_REPAIR_NON_READ_ONLY",
    )


def test_dominio_rejeita_multiplas_instrucoes() -> None:
    _assert_domain_rejects(
        "SELECT id FROM schema_test.table_test; SELECT value FROM schema_test.table_test",
        "SQL_REPAIR_MULTIPLE_STATEMENTS",
    )


def test_dominio_rejeita_sql_identica() -> None:
    _assert_domain_rejects(
        CURRENT_SQL,
        "SQL_REPAIR_UNCHANGED_SQL",
    )


def test_dominio_rejeita_sql_repetida() -> None:
    _assert_domain_rejects(
        REPAIRED_SQL,
        "SQL_REPAIR_REPEATED_SQL",
        history=[
            {
                "attempt": 1,
                "sql_after_fingerprint": sql_fingerprint(REPAIRED_SQL),
            }
        ],
    )


def test_factory_nao_acessa_secret() -> None:
    transport = FakeHttpTransport(
        result=_http_success(_success_payload("SELECT 1"))
    )
    secret_provider = FakeSecretValueProvider(
        secret=SensitiveSecret(SECRET_VALUE)
    )

    adapter = create_google_gemini_sql_repairer(
        {"GEMINI_API_BASE_URL": "https://example.invalid"},
        secret_provider=secret_provider,
        http_transport=transport,
    )

    assert adapter.__class__.__name__ == "GoogleGeminiSqlRepairerAdapter"
    assert secret_provider.calls == 0


def test_factory_nao_acessa_rede() -> None:
    transport = FakeHttpTransport(
        result=_http_success(_success_payload("SELECT 1"))
    )

    create_google_gemini_sql_repairer(
        {"GEMINI_API_BASE_URL": "https://example.invalid"},
        secret_provider=FakeSecretValueProvider(
            secret=SensitiveSecret(SECRET_VALUE)
        ),
        http_transport=transport,
    )

    assert transport.calls == 0


def test_repr_seguro() -> None:
    client = GoogleGeminiClient(
        configuration=GoogleGeminiConfiguration(
            api_base_url="https://example.invalid",
            model_id="generic-model",
        ),
        secret_provider=FakeSecretValueProvider(
            secret=SensitiveSecret(SECRET_VALUE)
        ),
        http_transport=FakeHttpTransport(
            result=_http_success(_success_payload("SELECT 1"))
        ),
    )
    adapter = GoogleGeminiSqlRepairerAdapter(client=client)

    assert repr(client) == "GoogleGeminiClient(<safe>)"
    assert repr(adapter) == "GoogleGeminiSqlRepairerAdapter(<safe>)"
    assert "example.invalid" not in repr(client)
    assert "generic-model" not in repr(client)
    assert SECRET_VALUE not in repr(adapter)


def test_integracao_adapter_com_repair_node_sem_banco() -> None:
    adapter, transport, _secret = _adapter_success()
    node = create_repair_sql_node(adapter)

    result = node(_state())

    assert result["final_status"] == "processing"
    assert result["current_sql"] == REPAIRED_SQL
    assert result["repair_attempts"] == 1
    assert result["security_result"]["status"] == "not_run"
    assert result["contract_result"]["status"] == "not_run"
    assert result["engine_preflight_result"]["status"] == "not_run"
    assert transport.calls == 1


def test_build_repair_payload_rejeita_objeto_nao_serializavel() -> None:
    class NonSerializable:
        pass

    request = _repair_request()
    request["repair_context"]["selected_pattern"] = {"bad": NonSerializable()}

    try:
        build_gemini_repair_payload(
            request=request,
            configuration=GoogleGeminiConfiguration(),
        )
    except GeminiContractError as error:
        assert "NonSerializable" not in repr(error)
    else:
        raise AssertionError("Era esperado erro Gemini.")


def test_adapter_rejeita_contrato_invalido_sem_http() -> None:
    adapter, transport, _secret = _adapter_success()
    request = _repair_request()
    request["contract_version"] = "invalid"

    _assert_provider_error(adapter, request)

    assert transport.calls == 0


def main() -> None:
    tests = [
        ("config default", test_configuracao_default_do_repairer),
        ("modelo customizado", test_modelo_repairer_customizado),
        ("modelos diferentes", test_generator_e_repairer_podem_usar_modelos_diferentes),
        ("payload deterministico", test_payload_deterministico),
        ("payload current_sql", test_payload_contem_current_sql),
        ("payload attempt", test_payload_contem_attempt_e_max_attempts),
        ("payload repair_context", test_payload_contem_repair_context),
        ("payload failure", test_payload_contem_failure_estruturado),
        ("payload previous_attempts", test_payload_contem_previous_attempts),
        ("payload instructions", test_payload_contem_instructions_e_output_constraints),
        ("payload sem GraphState", test_payload_nao_contem_graphstate),
        ("payload sem segredo", test_payload_nao_contem_segredo_ou_header),
        ("objeto nao serializavel client", test_objeto_nao_serializavel_falha_antes_de_http),
        ("secret missing", test_secret_missing_nao_chama_http),
        ("secret unavailable", test_secret_unavailable_nao_chama_http),
        ("secret invalid", test_secret_invalid_nao_chama_http),
        ("primeiro candidate", test_sucesso_usa_somente_primeiro_candidate),
        ("sem fallback candidate", test_segundo_candidate_nao_e_fallback),
        ("json invalido", test_json_invalido),
        ("utf8 invalido", test_utf8_invalido),
        ("http 401 403", test_http_401_403),
        ("http 429", test_http_429),
        ("http 5xx", test_http_5xx),
        ("timeout", test_timeout),
        ("dns tls", test_dns_tls_failure),
        ("response too large", test_response_too_large),
        ("adapter sucesso", test_adapter_retorna_provider_output_e_duration),
        ("adapter usage metadata", test_adapter_mapeia_usage_metadata),
        ("sem raw_response", test_raw_response_ausente),
        ("adapter nao limpa", test_adapter_nao_limpa_markdown),
        ("dominio rejeita ddl", test_dominio_rejeita_ddl),
        ("dominio rejeita dml", test_dominio_rejeita_dml),
        ("dominio rejeita multiplas", test_dominio_rejeita_multiplas_instrucoes),
        ("dominio rejeita identica", test_dominio_rejeita_sql_identica),
        ("dominio rejeita repetida", test_dominio_rejeita_sql_repetida),
        ("factory sem secret", test_factory_nao_acessa_secret),
        ("factory sem rede", test_factory_nao_acessa_rede),
        ("repr seguro", test_repr_seguro),
        ("integracao repair node", test_integracao_adapter_com_repair_node_sem_banco),
    ]
    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")

    test_build_repair_payload_rejeita_objeto_nao_serializavel()
    test_adapter_rejeita_contrato_invalido_sem_http()
    print("testes auxiliares: OK")


if __name__ == "__main__":
    main()
