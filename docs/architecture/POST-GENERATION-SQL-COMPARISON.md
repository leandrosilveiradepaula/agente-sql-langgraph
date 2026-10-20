# Comparação SQL pós-geração (somente leitura)

Este é um componente de paridade funcional, não outro fluxo n8n.
A resposta oficial n8n + Gemini não muda. Depois de ambos os geradores
terem produzido SQL, o Produto pode submeter a SQL oficial já persistida
a este serviço, que lê a SQL LangGraph de uma evidência Shadow existente.

## API interna

POST /v1/internal/sql-agent/compare-shadow-sql

O endpoint usa a mesma autenticação S2S Bearer da API interna. Corpo:
- contract_version: "1"
- agent_run_id: ID da execução oficial
- shadow_record_id: ID do registro de geração Shadow já persistido
- question: pergunta original já enviada à geração Shadow
- official_sql: SQL oficial previamente produzida
- principal: id e organization_id opcional

A API valida corpo estrito (sem golden_answer, expected_sql ou outros
campos de avaliação), IDs, origem, status da geração, pergunta e
fingerprints persistidos. A identidade e o organization_id devem coincidir.
Quando nenhum dos dois possui tenant, a comparação pode ocorrer mas
tenant_identity_attested fica falso; não declarar portabilidade aprovada.

A resposta inclui só categorias estruturais que divergem, fingerprint
global da SQL de cada lado, versão/fingerprint de contexto Shadow, exigência
de reaprovação e limitações explícitas. Não devolve SQL, nomes de tabelas,
aliases, valores de filtros, linhas financeiras ou respostas de provider.
Nenhum benchmark alimenta gerador/planner/reparo.

Os verdicts são:
- normalized_sql_match: os tokens normalizados coincidem, incluindo literais;
  ainda assim NÃO prova resultados financeiros iguais.
- structural_differences: há diferença identificada em pelo menos uma
  faceta entre tabelas, joins, predicates, projections, groupings,
  orderings, functions ou query_shape.
- inconclusive: sem diferença identificada nas facetas mas tokens diferentes
  ou predicados que o analisador não interpreta integralmente.

Comparar SQL textualmente diferente não equivale a afirmar erro financeiro;
um mapeamento de negócios versionado e posterior execução read-only autorizada
serão necessários para a paridade numérica. O comparador falha com segurança
para SQL inválida, não SELECT ou tentativa de SELECT INTO. Ele não executa
SQL mesmo quando a entrada é SELECT.

## Implantação e testes

Validar offline com:
python3 testar_internal_shadow_sql_comparison.py

O teste está integrado a scripts/check_all.py. Ele cobre correlação
e tenant, status, divergência de predicados/tabelas, entradas maliciosas,
dois esquemas sintéticos materialmente diferentes, autenticação S2S,
fingerprint da resposta e ausência de vazamento de SQL.

O endpoint requer uma integração de Produto BFF que autorize o usuário a
visualizar a SQL da execução oficial antes de enviar dados ao serviço interno.
Não expor o endpoint diretamente ao navegador. Não usar o banco de benchmark
como fonte semântica. Ativação, SQL read-only, rede, n8n e produção mantêm
os gates existentes; merge não equivale a deploy ou paridade.
