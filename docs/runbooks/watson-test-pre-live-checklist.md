# Watson TEST Pre-Live Checklist

## A. Antes Da API Key

- Confirmar `git status -sb` limpo.
- Executar `scripts/check_all.py`.
- Executar `scripts/check_clean_room.py`.
- Confirmar que nenhum probe live foi executado.
- Confirmar que n8n, Watson PROD e PostgreSQL nao foram alterados.

## B. Apos Receber A Nova API Key

- Abrir um CMD novo.
- Definir a API key somente na sessao CMD.
- Nao usar `setx`.
- Nao gravar a chave em arquivo.
- Nao colar a chave em argumentos.

## C. Antes Do Dry-Run

- Usar `scripts\watson_test_probe.cmd dry-run`.
- O launcher prefere `.venv\Scripts\python.exe`.
- Se a venv nao existir, o launcher pode usar `python.exe` valido no PATH.
- No CI, o Python vem de `actions/setup-python`.
- O launcher nunca cria venv, nunca instala dependencias e nunca chama pip.
- Ausencia de `.venv` e de Python valido no PATH falha antes de criar SQL
  temporaria.
- Em maquina operacional, recomenda-se usar a `.venv`; PATH nao garante
  isolamento de dependencias.
- O dry-run nao exige API key.
- O dry-run nao acessa rede.
- O plano nao deve conter SQL integral, URL completa, flow ID completo, token ou
  API key.

## D. Antes Do Probe Execution

- Confirmar `WATSON_API_BASE_URL`, `WATSON_FLOW_ID` e `IBM_CLOUD_API_KEY` na
  sessao CMD, sem imprimir valores.
- Executar uma unica tentativa:
  `scripts\watson_test_probe.cmd live-execution`.
- Digitar exatamente `EXECUTAR TEST` quando solicitado.
- Nao usar show rows no primeiro teste.
- Nao executar preflight antes de uma execution bem-sucedida.
- Nao fazer retry manual.

## E. Apos Sucesso

- Registrar somente exit code, status sanitizado, hash do commit e horario.
- Nao persistir raw output.
- Nao ativar ASGI.
- Nao criar cache de token.
- Nao alterar n8n.
- Nao tocar PROD.

## F. Apos Falha

- Parar.
- Nao repetir a tentativa.
- Preservar apenas evidencia sanitizada.
- Classificar a falha usando o rehearsal offline correspondente.
- Nao alterar contrato durante a janela live.

## G. Limpeza

- Executar `scripts\watson_test_probe.cmd clean`.
- Como o launcher usa `setlocal`, limpar tambem a sessao CMD pai:
  `set "IBM_CLOUD_API_KEY="`
- Nao limpar automaticamente URL ou flow ID.

## H. Evidencias Seguras

- Permitido: commit, branch, exit code, status publico, fingerprints
  sanitizados.
- Proibido: API key, token, Authorization, URL completa, flow ID completo,
  body real, raw output, headers completos, SQL de negocio.

## I. Criterios Para Avancar Ao Preflight

- Execution TEST unica bem-sucedida.
- Sem retry manual.
- Sem raw output em evidencia.
- `check_all.py` e `check_clean_room.py` continuam passando depois.

## J. Criterios Para Ativacao Futura No Processo TEST

- Contrato do provider estabilizado.
- Operacao documentada e reproduzivel.
- Sem cache, retry ou backoff implicitos.
- Sem ASGI live permanente nesta fase.
- Sem mudanca n8n ou PROD.
