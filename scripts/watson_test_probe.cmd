@echo off
setlocal EnableExtensions DisableDelayedExpansion

set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO_ROOT=%%~fI"
set "PYTHON_EXE="
set "LOCAL_PYTHON_EXE=%REPO_ROOT%\.venv\Scripts\python.exe"
set "PROBE_SCRIPT=%REPO_ROOT%\scripts\manual_watson_flow_probe.py"
set "WORK_DIR=%TEMP%\watson-flow-probe"
set "SQL_FILE=%WORK_DIR%\adapter_contract_probe.sql"
set "MODE=%~1"
set "PYTHONPATH=%REPO_ROOT%"

if "%MODE%"=="" set "MODE=help"

if /I "%MODE%"=="help" goto :help
if /I "%MODE%"=="dry-run" goto :dry_run
if /I "%MODE%"=="dry-run-config" goto :dry_run_config
if /I "%MODE%"=="live-execution" goto :lexec
if /I "%MODE%"=="live-preflight" goto :lpre
if /I "%MODE%"=="clean" goto :clean

echo Modo invalido.
exit /b 2

:check_repo
if not exist "%PROBE_SCRIPT%" (
  echo Repositorio esperado nao encontrado.
  exit /b 2
)
exit /b 0

:resolve_python
if exist "%LOCAL_PYTHON_EXE%" (
  call :validate_python "%LOCAL_PYTHON_EXE%"
  if errorlevel 1 (
    echo Python da venv invalido.
    exit /b 2
  )
  exit /b 0
)
for /f "delims=" %%P in ('"%SystemRoot%\System32\where.exe" python.exe 2^>nul') do (
  call :validate_python "%%~fP"
  if not errorlevel 1 exit /b 0
)
echo Python valido nao encontrado.
exit /b 2

:validate_python
"%~1" -c "import sys; print(sys.executable)" >nul 2>nul
if errorlevel 1 exit /b 1
set "PYTHON_EXE=%~1"
exit /b 0

:check_temp
if not defined TEMP (
  echo TEMP ausente.
  exit /b 2
)
if not exist "%TEMP%\" (
  echo TEMP invalido.
  exit /b 2
)
exit /b 0

:prepare_sql
if not exist "%WORK_DIR%" mkdir "%WORK_DIR%" >nul 2>nul
if errorlevel 1 (
  echo TEMP invalido.
  exit /b 2
)
"%PYTHON_EXE%" -c "from pathlib import Path; import sys; Path(sys.argv[1]).write_text('SELECT 1 AS adapter_contract_probe', encoding='utf-8')" "%SQL_FILE%"
if errorlevel 1 (
  echo Falha ao criar SQL temporaria.
  exit /b 1
)
exit /b 0

:remove_sql
if exist "%SQL_FILE%" del /q "%SQL_FILE%" >nul 2>nul
exit /b 0

:dry_run
call :check_repo
if errorlevel 1 exit /b %errorlevel%
call :check_temp
if errorlevel 1 exit /b %errorlevel%
call :resolve_python
if errorlevel 1 exit /b %errorlevel%
set "WATSON_API_BASE_URL="
set "WATSON_FLOW_ID="
set "IBM_CLOUD_API_KEY="
call :prepare_sql
if errorlevel 1 exit /b %errorlevel%
"%PYTHON_EXE%" "%PROBE_SCRIPT%" --sql-file "%SQL_FILE%" --purpose execution --print-plan-json
set "PROBE_CODE=%errorlevel%"
call :remove_sql
exit /b %PROBE_CODE%

:dry_run_config
call :check_repo
if errorlevel 1 exit /b %errorlevel%
if not defined WATSON_API_BASE_URL (
  echo WATSON_API_BASE_URL ausente.
  exit /b 2
)
if not defined WATSON_FLOW_ID (
  echo WATSON_FLOW_ID ausente.
  exit /b 2
)
set "IBM_CLOUD_API_KEY="
call :check_temp
if errorlevel 1 exit /b %errorlevel%
call :resolve_python
if errorlevel 1 exit /b %errorlevel%
call :prepare_sql
if errorlevel 1 exit /b %errorlevel%
"%PYTHON_EXE%" "%PROBE_SCRIPT%" --sql-file "%SQL_FILE%" --purpose execution --print-plan-json
set "PROBE_CODE=%errorlevel%"
call :remove_sql
exit /b %PROBE_CODE%

:lexec
call :run_live execution
exit /b %errorlevel%

:lpre
call :run_live preflight
exit /b %errorlevel%

:run_live
call :check_repo
if errorlevel 1 exit /b %errorlevel%
if not defined WATSON_API_BASE_URL (
  echo WATSON_API_BASE_URL ausente.
  exit /b 2
)
if not defined WATSON_FLOW_ID (
  echo WATSON_FLOW_ID ausente.
  exit /b 2
)
if not defined IBM_CLOUD_API_KEY (
  echo IBM_CLOUD_API_KEY ausente.
  exit /b 2
)
echo Esta acao faz uma unica tentativa live em TEST.
set /p "CONFIRM_TEXT=Digite EXECUTAR TEST para continuar: "
if not "%CONFIRM_TEXT%"=="EXECUTAR TEST" (
  echo Confirmacao invalida. Nenhuma chamada live foi iniciada.
  exit /b 5
)
call :check_temp
if errorlevel 1 exit /b %errorlevel%
call :resolve_python
if errorlevel 1 exit /b %errorlevel%
call :prepare_sql
if errorlevel 1 exit /b %errorlevel%
"%PYTHON_EXE%" "%PROBE_SCRIPT%" --execute-live --confirm-test-environment --sql-file "%SQL_FILE%" --purpose %~1
set "PROBE_CODE=%errorlevel%"
call :remove_sql
set "IBM_CLOUD_API_KEY="
echo IBM_CLOUD_API_KEY removida do escopo deste script.
echo Se ela existir no CMD pai, execute: set "IBM_CLOUD_API_KEY="
exit /b %PROBE_CODE%

:clean
call :check_temp
if errorlevel 1 exit /b %errorlevel%
if exist "%WORK_DIR%" rmdir /s /q "%WORK_DIR%" >nul 2>nul
set "IBM_CLOUD_API_KEY="
echo Limpeza local concluida. Para limpar o CMD pai, execute: set "IBM_CLOUD_API_KEY="
exit /b 0

:help
echo Uso:
echo   watson_test_probe.cmd help
echo   watson_test_probe.cmd dry-run
echo   watson_test_probe.cmd dry-run-config
echo   watson_test_probe.cmd live-execution
echo   watson_test_probe.cmd live-preflight
echo   watson_test_probe.cmd clean
echo.
echo O launcher usa setlocal. Variaveis da sessao CMD pai nao sao removidas por este script.
echo O launcher prefere .venv\Scripts\python.exe e, se ausente, usa python.exe valido no PATH.
echo O launcher nunca cria venv, nunca chama pip e nunca instala dependencias.
echo A API key nunca deve ser passada como argumento e nunca deve ser gravada em arquivo.
echo Live exige WATSON_API_BASE_URL, WATSON_FLOW_ID, IBM_CLOUD_API_KEY e confirmacao EXECUTAR TEST.
exit /b 0
