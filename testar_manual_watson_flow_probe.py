from __future__ import annotations

import contextlib
import io
import json
import tempfile
from pathlib import Path
from types import SimpleNamespace

import scripts.manual_watson_flow_probe as probe


FLOW_ID = "00e0284a-d785-448b-aed3-95672dd4d189"


def _run(args, env=None):
    out = io.StringIO()
    with contextlib.redirect_stdout(out):
        code = probe.main(args, environ={} if env is None else env)
    return code, out.getvalue()


def _sql(tmp: str, text: str = "SELECT 1 AS adapter_contract_probe") -> str:
    path = Path(tmp) / "query.sql"
    path.write_text(text, encoding="utf-8")
    return str(path)


def _plan(output: str) -> dict[str, object]:
    return json.loads(output)


class BombSecretProvider:
    def __init__(self, *args, **kwargs) -> None:
        raise AssertionError("secret provider nao deve ser construido")


class BombStdlibHttpTransport:
    def __init__(self, *args, **kwargs) -> None:
        pass


class SecretTrapEnv(dict):
    def get(self, key, default=None):
        if key == "IBM_CLOUD_API_KEY":
            raise AssertionError("secret nao pode ser lido diretamente do env")
        return super().get(key, default)


class FakePreflightAdapter:
    def __init__(self, result=None) -> None:
        self.calls = 0
        self.requests = []
        self.result = result or {
            "status": "approved",
            "statement_planned": True,
            "executed": False,
            "rows_returned": 0,
        }

    def preflight(self, request):
        self.calls += 1
        self.requests.append(request)
        return dict(self.result)


class FakeExecutorAdapter:
    def __init__(self, result=None) -> None:
        self.calls = 0
        self.requests = []
        self.result = result or {
            "status": "success",
            "executed": True,
            "row_count": 1,
        }

    def execute(self, request):
        self.calls += 1
        self.requests.append(request)
        return dict(self.result)


class SecretReadingPreflightAdapter:
    def __init__(self, secret_provider) -> None:
        self.secret_provider = secret_provider
        self.calls = 0

    def preflight(self, request):
        self.calls += 1
        self.secret_provider.get_secret(probe.SecretName("IBM_CLOUD_API_KEY"))
        return {
            "status": "error",
            "failure_category": "authentication_failed",
            "statement_planned": False,
            "executed": False,
            "rows_returned": 0,
        }


class CompositionFactory:
    def __init__(self, preflight=None, executor=None, read_secret=False) -> None:
        self.preflight = preflight
        self.executor = executor or FakeExecutorAdapter()
        self.read_secret = read_secret
        self.calls = 0
        self.kwargs = None

    def __call__(self, **kwargs):
        self.calls += 1
        self.kwargs = kwargs
        assert kwargs["environment"] is probe.DeploymentEnvironment.TEST
        assert "live_configuration" in kwargs
        assert "limits" in kwargs
        assert "secret_provider" in kwargs
        assert "http_transport" in kwargs
        preflight = self.preflight
        if preflight is None:
            preflight = (
                SecretReadingPreflightAdapter(kwargs["secret_provider"])
                if self.read_secret
                else FakePreflightAdapter()
            )
            self.preflight = preflight
        return SimpleNamespace(
            status="success",
            dependencies=SimpleNamespace(
                engine_preflight=preflight,
                sql_executor=self.executor,
            ),
        )


def main() -> None:
    original_secret = probe.EnvironmentSecretProvider
    original_build = probe.build_watson_test_dependencies
    original_transport = probe.StdlibHttpTransport
    try:
        with tempfile.TemporaryDirectory() as tmp:
            sql = _sql(tmp)
            code, output = _run(["--sql-file", sql, "--purpose", "execution"], env={})
            assert code == probe.EXIT_OK
            assert "mode=dry_run" in output
            assert "operation_ready_for_live=false" in output
            assert "IBM_CLOUD_API_KEY" not in output
            assert "SELECT 1" not in output
            assert "adapter_contract_probe" not in output

            code, output = _run(
                [
                    "--sql-file",
                    sql,
                    "--purpose",
                    "execution",
                    "--api-base-url",
                    "https://example.invalid",
                    "--flow-id",
                    FLOW_ID,
                    "--print-plan-json",
                ],
                env={},
            )
            plan = _plan(output)
            assert code == probe.EXIT_OK
            assert plan["configuration"]["source"] == "arguments"
            assert plan["configuration"]["api_base_url_valid"] is True
            assert plan["configuration"]["flow_id_valid"] is True
            assert plan["security"]["secret_required"] is False
            assert plan["security"]["secret_accessed"] is False
            assert plan["security"]["network_enabled"] is False
            assert plan["operation_ready_for_live"] is False
            serialized = json.dumps(plan, sort_keys=True)
            assert "SELECT 1" not in serialized
            assert "https://example.invalid" not in serialized
            assert FLOW_ID not in serialized
            assert "IBM_CLOUD_API_KEY" not in serialized

            code, output = _run(["--sql-file", sql, "--print-plan-json"], env={
                "WATSON_API_BASE_URL": "https://env.example.invalid",
                "WATSON_FLOW_ID": FLOW_ID,
                "IBM_CLOUD_API_KEY": "test-secret",
            })
            plan = _plan(output)
            assert code == probe.EXIT_OK
            assert plan["configuration"]["source"] == "environment"
            assert "test-secret" not in output

            code, output = _run(
                [
                    "--sql-file",
                    sql,
                    "--api-base-url",
                    "https://arg.example.invalid",
                    "--print-plan-json",
                ],
                env={"WATSON_FLOW_ID": FLOW_ID},
            )
            assert code == probe.EXIT_OK
            assert _plan(output)["configuration"]["source"] == "mixed"

            assert _run(["--sql-file", sql, "--api-base-url", "http://bad.invalid"])[0] == probe.EXIT_CONFIG_INVALID
            assert _run(["--sql-file", sql], env={"WATSON_API_BASE_URL": "http://bad.invalid"})[0] == probe.EXIT_CONFIG_INVALID
            assert _run(["--sql-file", sql, "--flow-id", "not-a-uuid"])[0] == probe.EXIT_CONFIG_INVALID
            assert _run(["--execute-live", "--sql-file", sql])[0] == probe.EXIT_LIVE_CONFIRMATION_MISSING
            assert _run(["--execute-live", "--confirm-test-environment", "--sql-file", sql], env={})[0] == probe.EXIT_CONFIG_INVALID

            probe.EnvironmentSecretProvider = BombSecretProvider  # type: ignore[assignment]
            code, output = _run(["--sql-file", sql], env={})
            assert code == probe.EXIT_OK
            assert "secret_accessed=false" in output
            probe.build_watson_test_dependencies = (  # type: ignore[assignment]
                lambda **_kwargs: (_ for _ in ()).throw(AssertionError("live deps"))
            )
            assert _run(["--sql-file", sql], env={})[0] == probe.EXIT_OK
            probe.EnvironmentSecretProvider = original_secret  # type: ignore[assignment]
            probe.build_watson_test_dependencies = original_build  # type: ignore[assignment]

            probe.StdlibHttpTransport = BombStdlibHttpTransport  # type: ignore[assignment]
            preflight = FakePreflightAdapter()
            executor = FakeExecutorAdapter()
            factory = CompositionFactory(preflight=preflight, executor=executor)
            probe.build_watson_test_dependencies = factory  # type: ignore[assignment]
            code, output = _run(
                [
                    "--execute-live",
                    "--confirm-test-environment",
                    "--sql-file",
                    sql,
                    "--purpose",
                    "preflight",
                    "--api-base-url",
                    "https://example.invalid",
                    "--flow-id",
                    FLOW_ID,
                ],
                env=SecretTrapEnv(),
            )
            assert code == probe.EXIT_OK
            assert factory.calls == 1
            assert preflight.calls == 1
            assert executor.calls == 0
            assert preflight.requests[0]["sql"] == "SELECT 1 AS adapter_contract_probe"
            assert preflight.requests[0]["request_fingerprint"]
            assert "preflight_status=approved" in output
            assert "executed=false" in output

            preflight = FakePreflightAdapter()
            executor = FakeExecutorAdapter()
            factory = CompositionFactory(preflight=preflight, executor=executor)
            probe.build_watson_test_dependencies = factory  # type: ignore[assignment]
            code, output = _run(
                [
                    "--execute-live",
                    "--confirm-test-environment",
                    "--sql-file",
                    sql,
                    "--purpose",
                    "execution",
                    "--api-base-url",
                    "https://example.invalid",
                    "--flow-id",
                    FLOW_ID,
                    "--show-rows",
                    "--confirm-show-rows",
                ],
                env=SecretTrapEnv(),
            )
            assert code == probe.EXIT_OK
            assert preflight.calls == 0
            assert executor.calls == 1
            assert executor.requests[0]["current_sql"] == "SELECT 1 AS adapter_contract_probe"
            assert executor.requests[0]["request_fingerprint"]
            assert "execution_status=success" in output
            assert "preview_rows_limit=5" in output

            factory = CompositionFactory(read_secret=True)
            probe.build_watson_test_dependencies = factory  # type: ignore[assignment]
            code, output = _run(
                [
                    "--execute-live",
                    "--confirm-test-environment",
                    "--sql-file",
                    sql,
                    "--purpose",
                    "preflight",
                    "--api-base-url",
                    "https://example.invalid",
                    "--flow-id",
                    FLOW_ID,
                ],
                env=SecretTrapEnv(),
            )
            assert code == probe.EXIT_SECRET_INVALID
            assert "IBM_CLOUD_API_KEY" not in output

            empty = Path(tmp) / "empty.sql"
            empty.write_bytes(b"")
            assert _run(["--sql-file", str(empty)])[0] == probe.EXIT_SQL_INVALID
            huge = Path(tmp) / "huge.sql"
            huge.write_bytes(b"x" * 200_001)
            assert _run(["--sql-file", str(huge)])[0] == probe.EXIT_SQL_INVALID
            assert _run(["--sql-file", "missing.sql"])[0] == probe.EXIT_SQL_INVALID
            assert _run([])[0] == probe.EXIT_USAGE
            assert _run(["--show-rows", "--sql-file", sql])[0] == probe.EXIT_USAGE
            assert _run(["--max-preview-rows", "0", "--sql-file", sql])[0] == probe.EXIT_USAGE
            assert _run(["--max-preview-rows", "51", "--sql-file", sql])[0] == probe.EXIT_USAGE
    finally:
        probe.EnvironmentSecretProvider = original_secret  # type: ignore[assignment]
        probe.build_watson_test_dependencies = original_build  # type: ignore[assignment]
        probe.StdlibHttpTransport = original_transport  # type: ignore[assignment]

    assert probe.EXIT_OK == 0
    assert probe.EXIT_USAGE == 2
    assert probe.EXIT_SQL_INVALID == 3
    assert probe.EXIT_CONFIG_INVALID == 4
    assert probe.EXIT_LIVE_CONFIRMATION_MISSING == 5
    assert probe.EXIT_SECRET_INVALID == 6
    assert probe.EXIT_IAM_FAILURE == 7
    assert probe.EXIT_WATSON_FLOW_FAILURE == 8
    assert probe.EXIT_CONTRACT_MISMATCH == 9
    assert probe.EXIT_RESULT_MISMATCH == 10
    assert probe.EXIT_INTERNAL_ERROR == 11
    assert "__main__" in Path("scripts/manual_watson_flow_probe.py").read_text(encoding="utf-8")
    check_all = Path("scripts/check_all.py").read_text(encoding="utf-8")
    assert "testar_manual_watson_flow_probe.py" in check_all
    assert "scripts/manual_watson_flow_probe.py" not in check_all
    source = Path("scripts/manual_watson_flow_probe.py").read_text(encoding="utf-8")
    assert "allow_nan=False" in source
    assert "env.get(_SECRET_ENV_NAME)" not in source
    assert "flow_client.run_flow" not in source
    print("testar_manual_watson_flow_probe.py: 44/44 OK")


if __name__ == "__main__":
    main()
