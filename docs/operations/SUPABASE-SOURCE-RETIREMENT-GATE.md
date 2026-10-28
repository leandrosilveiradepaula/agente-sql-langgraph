# G5 — Consolidação Supabase: inventário comprovado e bloqueios para aposentar a origem

**Revisão 28/10/2026.** Este documento é um inventário READ-ONLY, não uma migração nem autorização para desativar bancos. Contrato de operação: `OFFICIAL=n8n`, `SHADOW=LangGraph`, `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`.

## Identidades exatas

- Origem (candidata futura à aposentadoria): Supabase **Agente Financeiro**, `nywxpvzhlpqjtcafpdfe`.
- Destino (manter): Supabase **Demo**, `cenhadslwxgykqtuobgc`.
- Não confundir Supabase Demo com CRM ou Service Desk. A execução de `P3` transferiu **apenas 200 registros** de `public.langgraph_shadow_runs`; checksum ordenado em ambas origens: `5a2dd8dbe09c6f21b4fd8260e34dbced`.

## Evidências de diferenças reais (catálogo PostgreSQL; consultas sem dados brutos)

| Recurso | Origem | DEMO | Política de consolidação |
|---|---:|---:|---|
| Tabelas `public` | 47 | 10 | não duplicar esquema legado automaticamente |
| `ai_agent_users` | 10 | 1 | inventariar identidade, senha e autenticação antes de decisão; **não copiar hashes/sessões** |
| `ai_agent_sessions` | 112 | 9 | preservar ou exportar histórico autorizado; sessões ativas não são portáveis |
| `ai_agent_runs` | 238 | 42 | arquivamento/retention versionado com trilha, sem sobrescrever IDs |
| `langgraph_shadow_runs` | 200 | 200 | **migrado e checksum idêntico**; RLS do DEMO ativo |
| `ai_ducklake_agent_rules` | 318 (11 versões) | 110 (10 versões) | contextos diferentes: **não fazer merge de conhecimento** |
| `ai_ducklake_entity_aliases` | 738 | 605 | preservar versões legadas em arquivo isolado |
| `ai_ducklake_dre_mapping` | 121 | 130 | não fundir DRE/negócio |
| `ai_ducklake_sql_patterns` | 106 | 60 | exemplos e SQL legada são dados de avaliação, não prompt |
| `ai_ducklake_table_catalog` | 98 | 80 | destinos/dialetos diferentes, nunca copiar por nome |
| Contexto versionado | `public`, 11 versões `v2.0-ducklake-...` | `semantic_context`, 10 versões `demo-finance-v1..v10` | manter isolamento `SEMANTIC_AGENT_VERSION` |
| Warehouse | `public.gold_*` e `public.syn_gold_*` | `demo_lakehouse.gold_*` e `rivatti_demo_masked.gold_*` | schemas diferentes: não presumir compatibilidade contábil |

Os números são contagens observadas nas consultas, não estimativas do `pg_class.reltuples`.

## Produto: duas implantações Vercel e dois DATABASE_URL (valores **não lidos**)

Vercel confirmou projetos distintos:
- `agente-financeiro` (ID `prj_CcjDsXQDhREm6DYyrVtGPx29wq7U`): último Production READY consultado no commit `5f6d5113cd69ebcc4475a6f6046046051b8250ac`, branch `main`; variáveis `DATABASE_URL`, `N8N_GENERATE_SQL_WEBHOOK_URL`, `N8N_EXECUTE_WATSON_WEBHOOK_URL`, shadow e S2S presentes. **Destino efetivo do DATABASE_URL não identificado** (variável sigilosa, não decifrada).
- `agente-financeiro-demo` (ID `prj_jGIbRJIvuEPCIN1dQw92ZUST6jsU`): último Production READY consultado no commit `aa088f4426d42c94e79cd887ea6c16bb1200c09e`, branch `demo/grupo-horizonte`; `DATABASE_URL`, n8n e Shadow presentes; **destino efetivo não identificado**.

Código do Produto `Agente-Financeiro`: `lib/db.ts` consome `process.env.DATABASE_URL`; sessões e runs utilizam esse pool. A leitura das *chaves* da Vercel não demonstra a identidade da base. Portanto nenhuma exclusão pode ser autorizada antes de um atestado local, sem exibir o DSN.

## LangGraph: conexões separadas

`app/test_runtime/config.py` e `app/test_runtime/composition.py` confirmam:
- `LANGGRAPH_SHADOW_DATABASE_DSN`: histórico/evidências Shadow;
- `CONTEXT_POSTGRES_DSN`: cinco catálogos versionados; `POSTGRES_CONTEXT_SCHEMA` + `SEMANTIC_AGENT_VERSION`;
- possível `POSTGRES_DSN` no runtime geral, sujeito a inventário separado.

Não há prova atual dos **valores efetivos em contêineres da VPS**, nem autenticação com o novo login tenant-bound. A migração 002 só criou grupo NOLOGIN, políticas RLS e tabela de vínculo; sem login e sem organization_id validada. NÃO trocar DSN nem ligar flags por causa do inventário.

## n8n: bloqueio decisivo

O n8n oficial usa credencial PostgreSQL independente do Produto. O inventário legado tem 68 nós; houve tentativa de rebinding do workflow oficial, mas um diagnóstico anterior registrou drift na versão publicada. **Não inferir sucesso do PUT**. A auditoria viva da VPS/n8n precisa confirmar *published vs stored*, credenciais por ID e destino da conexão sem exibir senha ou host secreto. O caminho Shadow candidato `LwUsMRWi34D2ARWu1YzgV` não substitui o oficial.

Não desativar o Supabase antigo enquanto qualquer destino de n8n/Produto/LangGraph estiver `UNKNOWN` ou `SOURCE`.

## Inventário técnico seguro a executar na VPS (read-only)

Criar evidência de **somente fingerprints estáveis de destino**: cada processo de origem (Vercel Production/Preview, VPS LangGraph, credencial PostgreSQL n8n) deve indicar `SOURCE`, `DEMO`, `OTHER` ou `UNKNOWN`; nunca emitir `dsn`, usuário, senha, API key, cookies, host interno ou valores brutos de variáveis.

Critérios **obrigatórios** para declarar `READY_TO_RETIRE_SOURCE`:
1. Cada consumidor ativo conhecido e cada fluxo publicado n8n identificado com destino real e intenção funcional; nenhum `SOURCE`/`UNKNOWN`.
2. Preservação de registros antigos relevantes: export/backup privado, retenção e validação de restauração, incluindo históricos, benchmarks **fora** do gerador, contextos/versões e autenticação (sem copiar sessões/hashes cegamente).
3. `DEMO` com organização/membership autorizada, credential Shadow tenant-bound testada, separação de Generate/Repair/Execute Approved e isolamento provado.
4. Convergência operacional Produto + n8n + LangGraph confirmada em staging/canário. Continuidade da resposta oficial pelo n8n, SQL financeira Shadow desativada até autorização independente, plano de rollback testado.
5. Janela de observação e consentimento humano **específico** para aposentadoria/remoção. Desativação reversível primeiro, exclusão definitiva somente depois.

**Resultado de hoje: `RETIREMENT_GATE=BLOCKED`.** Motivos: dependências efetivas ainda não auditadas, histórico/semântica legados não arquivados, DSN sem cutover homologado, n8n published não reconciliado.

### Referências reais
- [PR LangGraph #181](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/181): isolamento RLS.
- [PR LangGraph #182](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/pull/182): utilitário de login com gate.
- [PR Produto Demo #33](https://github.com/leandrosilveiradepaula/Agente-Financeiro/pull/33): tabelas de organização privadas.
- [Roadmap #155](https://github.com/leandrosilveiradepaula/agente-sql-langgraph/issues/155): rastro operacional e decisões.
