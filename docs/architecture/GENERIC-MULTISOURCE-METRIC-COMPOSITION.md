# Capacidade genérica implementada — composição de métricas com múltiplas fontes

**Estado da implementação:** testada com dois contextos inteiramente sintéticos e estruturalmente diferentes, por meio do LangGraph real, em modo generate-only. **Estado da migração financeira do legado:** `IMPLEMENTED_UNPROVEN` até correlacionar e homologar contabilidade G5 por versão. O recurso é opt-in; não foi ativado no fluxo oficial, n8n ou Shadow real.

## Relação com o sistema antigo

O nó publicado n8n 22, função `planDreMensalAnalitica` (linhas 1973–2027), instrui combinar lançamentos diretos e rateados usando `UNION ALL` antes de agregar. Essa é uma **operação estrutural transferível**, mas seus nomes financeiros, regras de sinal, critérios, fatos e mapeamentos permanecem no G5 cifrado e não foram copiados. O novo código só implementa a operação estrutural. Não tem clientes, categorias, DRE obrigatória, valores ou tabelas reais fixos.

## Contrato e autorização

Opcionalmente, o snapshot de tenant pode declarar `metric_source_compositions` (ausência preserva exatamente a baseline e fingerprint antigos). Cada definição contém `composition_ref`, `intent_name`, `metric_ref`, `strategy=union_all_then_aggregate`, `source_use=APPROVED_SEMANTIC_MAPPING`, `accounting_definition_attested=true` e pelo menos duas fontes. Cada fonte define `source_ref`, `target_table` qualificada, `value_column`, `grain_ref`, `sign_multiplier` (+1/-1), `dimension_columns` e `source_filters` com operadores estruturais declarados.

O contrato rejeita itens extras contendo SQL histórica, sinais sem origem, tabelas/colunas fora do catálogo, medidas sem marcação de coluna métrica, fontes duplicadas, operadores/valores de filtro inválidos, dimensões sem mapeamento em **todas** as fontes, composição com metric/filter/comparison/temporal plan incompatível e alteração de plano antes do provedor.

**Importante:** declarar `accounting_definition_attested=true` não constitui aprovação contábil independente. O `CanonicalContextRepository` exige snapshot aprovado, tenant, versão e fingerprint configurados fora da pergunta; a auditoria financeira real e a governança da publicação continuam sendo gates humanos/operacionais. Não usar regras G5 cifradas como se estivessem atestadas.

## Funcionamento

1. `app/domain/context_normalizer.py`: inclui as composições apenas se o catálogo fornecido pelo cliente as contém; assim alterações de sinais/colunas/filters passam a alterar o fingerprint da versão e exigem nova aprovação.
2. `app/domain/planner.py`: escolhe a definição por intenção **já resolvida pelo catálogo**, valida grão/colunas por fonte, exige tabelas já selecionadas e dimension bindings explícitos, falha sem tentativas de inferir operação financeira do texto.
3. `app/domain/sql_generation.py`: transmite a composição verificada ao gerador de SQL com instruções genéricas de `UNION ALL` e agregação **somente após** a união. A configuração semântica permanece fora do Python.
4. `app/adapters/postgres/metric_source_composition_sql.py`: renderer estrutural PostgreSQL isolado constrói SQL read-only **dinamicamente** a partir das mesmas fontes do plano, preservando sinais, filtros e agrupamentos, sem joins entre fatos, sem SQL pronta por pergunta e sem acesso a banco.
5. `app/domain/sql_contract.py`: **fail closed** quando o candidato da LLM não permite comprovar fontes/sinais/filtros/UNION ALL/agrupamento. Até existir prova semântica AST equivalente, compara os tokens do candidato ao renderer derivado do plano autorizado; não são golden answers do benchmark. A validação de agrupamentos verifica todas as dimensões por fonte e suas projeções pós-UNION.

## Evidência reproduzível e escopo

- `testar_metric_source_composition_e2e.py`: **15 testes PASS** de normalização, dois contextos distintos, versões/fingerprints, geração de SQL dinâmica, Security+Contract Gates, agrupamentos e rejeições adversariais de fonte, coluna, filtro, sinal, SQL histórica e manipulação do plano.
- `testar_canonical_composition_shadow_e2e.py`: **3 testes PASS** em contêiner isolado sem rede, com fluxo HTTP real `/v1/internal/sql-agent/generate` → contexto canônico por tenant → LangGraph → geração dinâmica via adapter estrutural *injetado* → gates → evidências, e bloqueios de principal/tenant e fingerprint. Sem chamadas externas/LLM.
- Regressões selecionadas: planner **105**, SQL Contract **102**, além de SQL generation, normalizer, validator, filtros planejados, dois contextos Shadow pré-existentes e integração grafo (**5 PASS** em contêiner isolado).
- Relatório privado da VPS (JSON sem SQL, dados financeiros ou credenciais), SHA-256 `7d072603f211ad1fde940d809c366246bfa3c2cfdfda77a7b328ea89e6dc2db6`: **dois fingerprints de contexto**, **dois fingerprints de request e SQL distintos**, **Security+Contract Gates aprovados** sem executar SQL financeira.

**Não comprovado:** regras e sinais da versão G5 original (77 registros cifrados), uso do Gemini real com esse contrato, paridade de números, dois clientes reais, execução SELECT autorizada e cutover. A primeira capacidade financeira do legado continua `NOT_PROVEN`; somente sua **operação estrutural genérica** funciona demonstravelmente com dados sintéticos. A comparação das 63 perguntas continua exclusivamente no avaliador posterior.

**Limites atuais intencionais:** composição multitemporal, joins de dimensão externa, fórmulas derivadas, comparação interfonte e filtros dinâmicos da pergunta não estão cobertos por esse contrato e devem resultar em recusa segura em vez de SQL especulativa. Para outros dialetos, implementar adaptador estrutural autorizado: nenhum `if cliente`.
