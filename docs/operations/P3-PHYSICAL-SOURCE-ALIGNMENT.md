# P3 — Alinhamento físico entre n8n oficial e LangGraph Shadow

**Decisão em 29/10/2026:** preservar n8n como orquestrador e a resposta oficial enquanto se audita a fonte real. O canário financeiro teve autorização explícita para **uma** pergunta/execução SELECT controlada no DEMO, mas foi interrompido **antes de qualquer chamada Gemini ou SQL financeira** por conflito de fonte/contexto. A autorização não permite migrar, ativar versões, alterar credenciais/roles/produção/n8n ou fazer cutover.

## Diagnóstico confirmado — consultas de metadados, sem ler linhas financeiras

No projeto Supabase DEMO `cenhadslwxgykqtuobgc`:

| Controle | Evidência |
| --- | --- |
| Contexto semântico `demo-finance-v9` | 8 relações em `demo_lakehouse` |
| Versões `demo-finance-v1..v10` | Catálogos físicos também associados a `demo_lakehouse` |
| Role `finance_g1_readonly` | SELECT efetivo só em 8 relações de `rivatti_demo_masked`, sem privilégios de escrita ou temporários |
| Comparação das estruturas | 8 tabelas em cada schema; apenas 6 nomes de tabelas comuns; 70 e 67 colunas, apenas 6 pares de mesmo nome/tabela e 2 pares de mesmo tipo |
| SQL oficial histórica armazenada em `ai_agent_runs` | 39 SQLs: 38 referenciam `rivatti_demo_masked`, zero `demo_lakehouse`, 1 sem schema atestável por inspeção textual |
| Prova do datasource n8n **published atual** | NÃO confirmada pela VPS nesta etapa |
| Identidade do tenant e par oficial/Shadow no DEMO | Nenhum par P3 completo/persistido identificado |

A versão ativa do workflow n8n não pode ser inferida apenas do histórico de SQL. O operador já confirmou anteriormente duas referências de credencial G1; o workflow publicado **precisa** ser novamente atestado, sem expor segredos.

**Nova evidência de cobertura (29/10/2026, SELECT apenas em metadados):** no catálogo `demo-finance-v10`, há 37 entradas ativas de `ai_ducklake_entity_aliases` com `target_table` preenchido; 12 usam explicitamente `demo_lakehouse.`, 25 não qualificam o schema, nenhuma cita `rivatti_demo_masked.`. Somente 32 referências têm nome de tabela existente na fonte mascarada, e **apenas 2 referências têm simultaneamente nome de tabela e coluna existentes** (inspeção de nomes físicos; não atesta semântica contábil). Logo, **nem trocar prefixo de schema nem reutilizar aliases, fórmulas e regras da v10 constitui migração válida**. Revisar a correspondência e significado de cada conceito sob versão distinta, com os itens desconhecidos nulos/bloqueados.

**Conclusão:** conceder SELECT à role atual no outro schema **não** resolve a divergência. As duas estruturas são materialmente distintas. Também é proibido copiar a semântica do modelo `demo_lakehouse` para `rivatti_demo_masked` por mera semelhança de nomes, sem revisão de joins, grain, métricas, sinais, período e mapeamento contábil.

## Solução estrutural

1. Usar como baseline apenas o datasource **published e confirmado** pelo n8n. O histórico sugere `rivatti_demo_masked`, não prova o published atual.
2. Manter o catálogo existente `demo-finance-v9` para seu próprio contexto físico. Criar **nova versão de contexto distinta** para a fonte oficial, após levantamento de metadados físicos e aprovação humana dos significados contábeis. Não alterar `SEMANTIC_AGENT_VERSION` de runtime por inferência.
3. População de catálogo é responsabilidade dos dados/versionamento **por tenant**: `ai_ducklake_table_catalog`, `ai_ducklake_entity_aliases`, `ai_ducklake_agent_rules`, `ai_ducklake_sql_patterns` e `ai_ducklake_dre_mapping` apenas quando aplicável. Não copiar SQLs históricas, casos de benchmark ou hardcodes do n8n para as regras do gerador.
4. Contexto/credencial devem ter isolamento por tenant, fingerprint pinado e dialeto autorizado. O mesmo LangGraph opera com duas estruturas materialmente diferentes, sem `if` por cliente.
5. Depois de publicados e homologados os mapeamentos, executar **um** canário NL→SQL com os dois caminhos usando a mesma pergunta/organização, modelo Gemini e contexto correto, mantendo `LANGGRAPH_ALLOW_REAL_SQL_EXECUTION=false`; posteriormente fazer a prova financeira read-only sobre SQLs já geradas com hashes aprovados.

O rascunho de metadados físicos contém nomes/tipos e campos para revisão, todos vazios: grain, joins, métricas, datas, sinais, DRE etc. **Não é um contexto ativável** e não produz SQL.

## Auditoria unificada: um comando na VPS, sem nova API key nem DSN

**Somente após CI verde e merge humano desta PR.** No terminal da VPS autorizada:

```bash
cd /docker/agente-sql-langgraph-repo || exit 1
git fetch -q origin && git checkout -q main && git pull --ff-only -q origin main || exit 1

bash scripts/operations/p3_source_alignment_one_shot.sh \
  --context-version demo-finance-v9 \
  --source-ref nywxpvzhlpqjtcafpdfe \
  --demo-ref cenhadslwxgykqtuobgc \
  --n8n-container n8n-n8n-1 \
  --shadow-container agente-sql-langgraph-shadow-test-langgraph-shadow-test-1
```

O script utiliza exclusivamente ferramentas já existentes e revisadas: `g1_post_put_audit_readonly.py` (snapshot privado + identidade published 2.4.8) e `audit_supabase_runtime_dependencies_readonly.py` (classifica o alvo do Shadow e das credenciais n8n localmente). O segundo solicita a confirmação literal **`AUDIT-N8N-LOCAL`** na própria VPS, não solicita API key e nunca mostra a credencial. A auditoria confere o **LOGIN PostgreSQL efetivamente referenciado pelos dois nós de execução** (IDs obtidos do contrato G1), banco, TLS e Supabase DEMO, além da classificação do projeto. A simples existência de uma role segura no catálogo PostgreSQL não comprova que o n8n a utiliza. **A classificação agregada `N8N_OFFICIAL_CREDENTIAL_TARGET=SOURCE` não invalida a credencial G1 DEMO:** o auditor passa a emitir `N8N_EXECUTION_CREDENTIAL_TARGET=DEMO` em separado, mais as quantidades de nós PostgreSQL alcançáveis por SOURCE, DEMO e destinos indeterminados. Nós SOURCE alcançáveis continuam bloqueando o canário mesmo com G1 em DEMO. A análise de alcançabilidade é conservadora: todos os ramos de condições contam como possíveis, sem interpretar regras financeiras. Uma credencial PostgreSQL distinta, administrativa ou sem TLS produz `N8N_DATASOURCE_NOT_ATTESTED`, mesmo com o projeto correto. A coleta de metadados `p3_source_alignment_readonly.py --probe-shadow` usa o `CONTEXT_POSTGRES_DSN` já presente no contêiner Shadow TEST, verifica sua flag de execução SQL e a versão semântica corrente e só consulta `pg_catalog` e o catálogo semântico. A política física da fonte vem do arquivo G1 versionado, como configuração e não como regra de negócio.

Todos os relatórios físicos e provas permanecem em diretório local privado `0700`, arquivos `0600`. **Não compartilhar o diretório privado, JSON bruto de metadados, exportações n8n, headers, SQLs, DSNs, tokens, usuários ou dados financeiros em GitHub/chat.** Encaminhar apenas a linha JSON de `status`, `blockers`, contagens e fingerprints. O código não altera workflow/credencial, banco, servidor, Vercel ou LLM. Nenhuma SELECT financeira é realizada; `READ ONLY` é usado para as consultas **somente de metadados**.

### Interpretação de resultados

- `N8N_PUBLISHED_NOT_ATTESTED`: ausência de published/credencial ou deriva — não usar SQL histórica como substituto.
- `N8N_DATASOURCE_NOT_ATTESTED`: algum dos alvos SOURCE/DEMO/Shadow não foi comprovado como o DEMO autorizado.
- `CONTEXT_SOURCE_MISMATCH`: catálogo semântico seleciona relações diferentes da fonte física oficial.
- `ROLE_SCOPE_MISMATCH` / `ROLE_WRITE_PRIVILEGE`: privilégio efetivo não é exatamente SELECT-only nas relações declaradas.
- `PHYSICAL_COLUMNS_MISSING` / `ROLE_NOT_LEAST_PRIVILEGED`: fonte ou papel não atende ao contrato físico.
- `ready_for_semantic_review`: os metadados estão alinhados, **ainda sem aprovação contábil, tenant, SQL ou paridade**. Mesmo esse status não habilita execução real.

## Itens que a revisão contábil precisa confirmar

Os schemas atuais compartilham poucos nomes e **não possuem FKs declaradas** na fonte mascarada, embora possuam PKs. Não é possível deduzir joins financeiramente válidos só por nomes semelhantes. É obrigatório validar, para cada conceito necessário à pergunta inédita:

- métrica, fórmula e granularidade (em especial rateio versus lançamento);
- significado de cada chave de relacionamento, incluindo múltiplas bases;
- período e referência de competência versus lançamento;
- significado de realizado, orçamento, versões e filtros permitidos;
- convenção de sinal, categorias e DRE se existir;
- integridade e versão autorizada da política semântica, com fingerprint, tenant e provider/modelo atestados.

Nenhuma relação, coluna ou alias específico deve ser hardcoded no motor; tudo permanece em metadados versionados.

## Segurança e critérios de conclusão

A prova unitária offline, sem banco/LLM, inclui dois contextos sintéticos diferentes, acesso extra/missing, tentativas de mudança de schema, atributos administrativos, evidência published ausente, snapshot adulterado e rascunho privado com campos financeiros nulos. CI Windows e Linux, teste de sintaxe do shell. Um PASS de CI **não** significa paridade financeira; executar SELECT financeiro real só quando os gates de aprovação humana e par de SQLs imutáveis estiverem comprovados. n8n continua como orquestrador; nenhuma desativação implícita.
