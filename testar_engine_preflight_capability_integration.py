from __future__ import annotations

from copy import deepcopy

from app.bootstrap import create_engine_preflight_from_runtime_config
from app.config.engine_preflight_runtime import (
    EnginePreflightRuntimeConfig,
    EnginePreflightRuntimeConfigError,
    evaluate_engine_preflight_capabilities,
    load_engine_preflight_runtime_config,
)
from app.domain.engine_preflight import normalize_engine_preflight_result
from testar_engine_preflight import _request


def _config(**overrides) -> EnginePreflightRuntimeConfig:
    values = {
        "provider_type": "generic_engine",
        "capability_mode": "unavailable",
        "dialect": "generic_sql",
        "timeout_seconds": 5,
        "auth_mode": "none",
        "endpoint": None,
        "operation": None,
        "ssl_verify": True,
    }
    values.update(overrides)
    return EnginePreflightRuntimeConfig(**values)


def test_configuracao_valida() -> None:
    config = _config()

    assert config.provider_type == "generic_engine"
    assert config.capability_mode == "unavailable"
    assert config.timeout_seconds == 5


def test_carrega_configuracao_do_mapping() -> None:
    config = load_engine_preflight_runtime_config(
        {
            "ENGINE_PREFLIGHT_PROVIDER_TYPE": "generic_engine",
            "ENGINE_PREFLIGHT_CAPABILITY_MODE": "unavailable",
            "ENGINE_PREFLIGHT_DIALECT": "generic_sql",
            "ENGINE_PREFLIGHT_TIMEOUT_SECONDS": "7",
            "ENGINE_PREFLIGHT_AUTH_MODE": "none",
            "ENGINE_PREFLIGHT_SSL_VERIFY": "true",
        }
    )

    assert config.timeout_seconds == 7
    assert config.ssl_verify is True


def test_configuracao_ausente_rejeitada() -> None:
    try:
        load_engine_preflight_runtime_config({})
    except EnginePreflightRuntimeConfigError as error:
        assert "ENGINE_PREFLIGHT_PROVIDER_TYPE" in str(error)
    else:
        raise AssertionError("Era esperado erro de configuracao.")


def test_endpoint_invalido_rejeitado() -> None:
    try:
        _config(endpoint="http://example.invalid/preflight")
    except EnginePreflightRuntimeConfigError as error:
        assert "HTTPS" in str(error)
    else:
        raise AssertionError("Era esperado erro de endpoint.")


def test_timeout_invalido_rejeitado() -> None:
    for value in (0, -1, 61):
        try:
            _config(timeout_seconds=value)
        except EnginePreflightRuntimeConfigError:
            pass
        else:
            raise AssertionError("Era esperado erro de timeout.")


def test_auth_mode_invalido_rejeitado() -> None:
    try:
        _config(auth_mode="password")
    except EnginePreflightRuntimeConfigError as error:
        assert "auth_mode" in str(error)
    else:
        raise AssertionError("Era esperado erro de auth_mode.")


def test_capability_mode_invalido_rejeitado() -> None:
    try:
        _config(capability_mode="execute")
    except EnginePreflightRuntimeConfigError as error:
        assert "capability_mode" in str(error)
    else:
        raise AssertionError("Era esperado erro de capability_mode.")


def test_dry_run_exige_endpoint() -> None:
    try:
        _config(capability_mode="dry_run", endpoint=None)
    except EnginePreflightRuntimeConfigError as error:
        assert "endpoint" in str(error)
    else:
        raise AssertionError("Era esperado endpoint obrigatorio.")


def test_dry_run_https_configurado_sem_chamar_rede() -> None:
    config = _config(
        capability_mode="dry_run",
        endpoint="https://example.invalid/preflight",
    )
    diagnostic = evaluate_engine_preflight_capabilities(config)

    assert diagnostic["endpoint_configured"] is True
    assert diagnostic["can_preflight"] is False


def test_capability_indisponivel() -> None:
    diagnostic = evaluate_engine_preflight_capabilities(_config())

    assert diagnostic["can_preflight"] is False
    assert diagnostic["adapter_available"] is False
    assert diagnostic["error_code"] == "ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE"


def test_execucao_normal_e_insegura() -> None:
    diagnostic = evaluate_engine_preflight_capabilities(
        _config(capability_mode="normal_execution")
    )

    assert diagnostic["reason"] == "normal_execution_is_not_safe_for_preflight"
    assert diagnostic["can_preflight"] is False


def test_parse_sem_adapter_ainda_bloqueia() -> None:
    diagnostic = evaluate_engine_preflight_capabilities(
        _config(capability_mode="parse")
    )

    assert diagnostic["capabilities"]["supports_parse"] is True
    assert diagnostic["adapter_available"] is False
    assert diagnostic["can_preflight"] is False


def test_explain_sem_analyze_declarado_sem_adapter() -> None:
    diagnostic = evaluate_engine_preflight_capabilities(
        _config(capability_mode="explain_without_analyze")
    )

    assert diagnostic["capabilities"]["supports_explain"] is True
    assert diagnostic["capabilities"]["supports_explain_analyze"] is False
    assert diagnostic["adapter_available"] is False


def test_capabilities_nao_executam_nem_retornam_linhas() -> None:
    capabilities = evaluate_engine_preflight_capabilities(_config())[
        "capabilities"
    ]

    assert capabilities["executes_query"] is False
    assert capabilities["returns_rows"] is False


def test_supported_dialects_deterministico() -> None:
    diagnostic = evaluate_engine_preflight_capabilities(
        _config(dialect="Generic_SQL")
    )

    assert diagnostic["capabilities"]["supported_dialects"] == ["generic_sql"]


def test_factory_explicita_cria_provider_diagnostico() -> None:
    provider = create_engine_preflight_from_runtime_config(_config())

    assert provider.__class__.__name__ == "CapabilityUnavailableEnginePreflight"


def test_provider_retorna_erro_canonico() -> None:
    provider = create_engine_preflight_from_runtime_config(_config())
    result = provider.preflight(_request())

    assert result["status"] == "error"
    assert result["failure_category"] == "capability_unavailable"
    assert result["error_code"] == "ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE"


def test_resultado_normalizado_e_infraestrutura() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(_config())
    result = normalize_engine_preflight_result(
        request=request,
        provider_result=provider.preflight(request),
    )

    assert result["status"] == "error"
    assert result["failure_category"] == "capability_unavailable"
    assert result["repairable"] is False
    assert result["errors"][0]["code"] == "ENGINE_PREFLIGHT_CAPABILITY_UNAVAILABLE"


def test_provider_prova_sem_execucao() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(_config())
    result = normalize_engine_preflight_result(
        request=request,
        provider_result=provider.preflight(request),
    )

    assert result["executed"] is False
    assert result["rows_returned"] == 0
    assert result["statement_planned"] is False


def test_provider_chamado_uma_vez() -> None:
    provider = create_engine_preflight_from_runtime_config(_config())
    provider.preflight(_request())

    assert provider.calls == 1


def test_request_nao_mutada() -> None:
    request = _request()
    original = deepcopy(request)
    provider = create_engine_preflight_from_runtime_config(_config())

    provider.preflight(request)

    assert request == original


def test_provider_recebe_somente_request() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(_config())

    provider.preflight(request)
    serialized = repr(provider.last_request).casefold()

    assert provider.last_request is not request
    assert "graphstate" not in serialized
    assert "'context'" not in serialized


def test_determinismo() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(_config())

    first = provider.preflight(request)
    second = provider.preflight(request)

    assert first == second


def test_sanitiza_provider_name_token() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(
        _config(provider_type="provider token=abc")
    )
    result = normalize_engine_preflight_result(
        request=request,
        provider_result=provider.preflight(request),
    )

    assert "token=abc" not in repr(result).casefold()


def test_sanitiza_provider_name_dsn() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(
        _config(provider_type="dsn=postgresql://example.invalid/db")
    )
    result = normalize_engine_preflight_result(
        request=request,
        provider_result=provider.preflight(request),
    )

    assert "postgresql://" not in repr(result).casefold()


def test_sanitiza_sql_integral() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(_config())
    result = normalize_engine_preflight_result(
        request=request,
        provider_result=provider.preflight(request),
    )

    assert request["sql"].casefold() not in repr(result).casefold()


def test_endpoint_nao_aparece_no_diagnostico() -> None:
    config = _config(
        capability_mode="dry_run",
        endpoint="https://example.invalid/preflight",
    )
    diagnostic = evaluate_engine_preflight_capabilities(config)

    assert "example.invalid" not in repr(diagnostic)


def test_ssl_verify_parse_false() -> None:
    config = load_engine_preflight_runtime_config(
        {
            "ENGINE_PREFLIGHT_PROVIDER_TYPE": "generic_engine",
            "ENGINE_PREFLIGHT_CAPABILITY_MODE": "unavailable",
            "ENGINE_PREFLIGHT_SSL_VERIFY": "false",
        }
    )

    assert config.ssl_verify is False


def test_ssl_verify_invalido_rejeitado() -> None:
    try:
        load_engine_preflight_runtime_config(
            {
                "ENGINE_PREFLIGHT_PROVIDER_TYPE": "generic_engine",
                "ENGINE_PREFLIGHT_CAPABILITY_MODE": "unavailable",
                "ENGINE_PREFLIGHT_SSL_VERIFY": "maybe",
            }
        )
    except EnginePreflightRuntimeConfigError as error:
        assert "booleana" in str(error)
    else:
        raise AssertionError("Era esperado erro booleano.")


def test_operacao_sanitizada() -> None:
    diagnostic = evaluate_engine_preflight_capabilities(
        _config(operation="operation token=abc")
    )

    assert "token=abc" not in repr(diagnostic).casefold()


def test_config_nao_guarda_credenciais() -> None:
    config = _config(auth_mode="bearer")
    serialized = repr(config).casefold()

    assert "authorization" not in serialized
    assert "password" not in serialized


def test_nao_ha_transporte_configurado_por_padrao() -> None:
    config = _config()

    assert config.endpoint is None


def test_provider_nao_expoe_headers_ou_body() -> None:
    request = _request()
    provider = create_engine_preflight_from_runtime_config(_config())
    result = provider.preflight(request)
    serialized = repr(result).casefold()

    assert "authorization" not in serialized
    assert "cookie" not in serialized
    assert "request_body" not in serialized
    assert "response_body" not in serialized


def main() -> None:
    tests = [
        ("configuracao valida", test_configuracao_valida),
        ("carrega configuracao", test_carrega_configuracao_do_mapping),
        ("configuracao ausente", test_configuracao_ausente_rejeitada),
        ("endpoint invalido", test_endpoint_invalido_rejeitado),
        ("timeout invalido", test_timeout_invalido_rejeitado),
        ("auth mode invalido", test_auth_mode_invalido_rejeitado),
        ("capability mode invalido", test_capability_mode_invalido_rejeitado),
        ("dry run exige endpoint", test_dry_run_exige_endpoint),
        ("dry run sem rede", test_dry_run_https_configurado_sem_chamar_rede),
        ("capability indisponivel", test_capability_indisponivel),
        ("execucao normal insegura", test_execucao_normal_e_insegura),
        ("parse sem adapter", test_parse_sem_adapter_ainda_bloqueia),
        (
            "explain sem analyze sem adapter",
            test_explain_sem_analyze_declarado_sem_adapter,
        ),
        ("capabilities seguras", test_capabilities_nao_executam_nem_retornam_linhas),
        ("dialetos ordenados", test_supported_dialects_deterministico),
        ("factory explicita", test_factory_explicita_cria_provider_diagnostico),
        ("erro canonico", test_provider_retorna_erro_canonico),
        ("normalizacao infra", test_resultado_normalizado_e_infraestrutura),
        ("prova sem execucao", test_provider_prova_sem_execucao),
        ("provider chamado uma vez", test_provider_chamado_uma_vez),
        ("request imutavel", test_request_nao_mutada),
        ("somente request", test_provider_recebe_somente_request),
        ("determinismo", test_determinismo),
        ("sanitiza token", test_sanitiza_provider_name_token),
        ("sanitiza dsn", test_sanitiza_provider_name_dsn),
        ("sanitiza sql", test_sanitiza_sql_integral),
        ("endpoint oculto", test_endpoint_nao_aparece_no_diagnostico),
        ("ssl false", test_ssl_verify_parse_false),
        ("ssl invalido", test_ssl_verify_invalido_rejeitado),
        ("operacao sanitizada", test_operacao_sanitizada),
        ("sem credenciais", test_config_nao_guarda_credenciais),
        ("sem transporte padrao", test_nao_ha_transporte_configurado_por_padrao),
        ("sem headers ou body", test_provider_nao_expoe_headers_ou_body),
    ]

    for index, (name, test_function) in enumerate(tests, start=1):
        test_function()
        print(f"TESTE {index} - {name}: OK")


if __name__ == "__main__":
    main()
