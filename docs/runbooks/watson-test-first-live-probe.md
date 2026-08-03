# Watson TEST first live probe

Runbook operacional para CMD no Windows. Nao use PowerShell nesta pagina.

## Pre-condicoes

- Branch esperada: `master` apos merge dos contratos Watson Flow.
- Probe manual disponivel em `scripts/manual_watson_flow_probe.py`.
- Live adapters desativados por padrao.
- A primeira consulta sintetica deve ser exatamente `SELECT 1 AS adapter_contract_probe`.
- Nao executar contra PROD, n8n, ASGI, servidor ou PostgreSQL.
- Nao repetir automaticamente em caso de falha.

## Hoje, sem API key

Criar o diretorio temporario:

```cmd
mkdir "%TEMP%\watson-flow-probe" 2>nul
```

Criar o arquivo SQL em UTF-8:

```cmd
.venv\Scripts\python.exe -c "from pathlib import Path; Path(r'%TEMP%\watson-flow-probe\watson-adapter-contract-probe.sql').write_text('SELECT 1 AS adapter_contract_probe', encoding='utf-8')"
```

Executar dry-run SQL-only, sem API key:

```cmd
.venv\Scripts\python.exe scripts\manual_watson_flow_probe.py ^
  --sql-file "%TEMP%\watson-flow-probe\watson-adapter-contract-probe.sql" ^
  --purpose execution
```

Configurar somente valores nao sensiveis do TEST:

```cmd
set "WATSON_API_BASE_URL=https://api.us-south.watson-orchestrate.cloud.ibm.com/instances/92d931c3-9a72-4844-97e4-a641ca7bd5b8"
set "WATSON_FLOW_ID=00e0284a-d785-448b-aed3-95672dd4d189"
```

Validar presenca sem imprimir valores:

```cmd
if not defined WATSON_API_BASE_URL (
  echo WATSON_API_BASE_URL ausente
  exit /b 1
)

if not defined WATSON_FLOW_ID (
  echo WATSON_FLOW_ID ausente
  exit /b 1
)
```

Executar dry-run com configuracao nao sensivel e plano sanitizado:

```cmd
.venv\Scripts\python.exe scripts\manual_watson_flow_probe.py ^
  --sql-file "%TEMP%\watson-flow-probe\watson-adapter-contract-probe.sql" ^
  --purpose execution ^
  --api-base-url "%WATSON_API_BASE_URL%" ^
  --flow-id "%WATSON_FLOW_ID%" ^
  --print-plan-json
```

Executar o runner offline:

```cmd
.venv\Scripts\python.exe scripts\offline_watson_test_composition_check.py
```

## Amanha, com nova API key

Digite a chave em terminal privado. CMD exibe a digitacao; nao copie a chave
para chat, arquivo, historico do projeto ou documentacao.

```cmd
set /p IBM_CLOUD_API_KEY=Informe a IBM Cloud API key do ambiente TEST:
```

Nao use `echo` com a variavel. Nao use `set` sem filtro. Nao use o comando
persistente do Windows para gravar essa variavel no perfil do usuario.

Executar uma unica tentativa live de execution:

```cmd
.venv\Scripts\python.exe scripts\manual_watson_flow_probe.py ^
  --execute-live ^
  --confirm-test-environment ^
  --sql-file "%TEMP%\watson-flow-probe\watson-adapter-contract-probe.sql" ^
  --purpose execution
```

Nao adicionar `--show-rows` no primeiro teste. Nao executar preflight neste
primeiro probe live. Nao usar curl, Postman, n8n ou ADK.

Limpar a API key da sessao:

```cmd
set "IBM_CLOUD_API_KEY="
```

Validar limpeza:

```cmd
if defined IBM_CLOUD_API_KEY (
  echo Falha ao limpar IBM_CLOUD_API_KEY
  exit /b 1
) else (
  echo IBM_CLOUD_API_KEY removida da sessao
)
```

Remover temporarios:

```cmd
del "%TEMP%\watson-flow-probe\watson-adapter-contract-probe.sql" 2>nul
rmdir "%TEMP%\watson-flow-probe" 2>nul
```

## Classificacao

- Sucesso completo: IAM success, Flow success, JSON valido, envelope aceito,
  `row_count=1`, coluna `adapter_contract_probe`, celula logica igual a `1`,
  sem retry e sem exposicao de segredo.
- IAM failure: nao chamar Flow novamente.
- Flow unavailable, timeout, rate limit ou HTTP error: nao repetir.
- Contract mismatch: capturar somente shape sanitizado, sem raw output.
- Result mismatch: nao repetir; revisar contrato observado.

## Dados seguros para compartilhar

Pode compartilhar status geral, exit code, purpose, SHA-256 e tamanho da SQL,
status IAM/Flow sanitizados, status normalizado, `row_count`, columns,
`truncated`, `execution_time_ms`, categoria de falha e ausencia de retry.

Nunca compartilhar API key, token, Authorization, body IAM, body Flow bruto,
headers completos, raw output, endpoint com detalhes sensiveis, stack trace ou
dump de objetos.

## Probe preflight posterior

Depois do primeiro execution controlado e da avaliacao do contrato real, um
probe separado pode usar:

```cmd
.venv\Scripts\python.exe scripts\manual_watson_flow_probe.py ^
  --execute-live ^
  --confirm-test-environment ^
  --sql-file "%TEMP%\watson-flow-probe\watson-adapter-contract-probe.sql" ^
  --purpose preflight
```

Executar somente apos decisao explicita. Sem retry automatico.
