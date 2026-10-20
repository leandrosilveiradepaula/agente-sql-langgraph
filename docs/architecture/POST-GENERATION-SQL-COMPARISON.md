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
- normalized_sql_match: os tokens estruturais coincidem, mas os valores de
  strings e identificadores entre aspas preservam maiúsculas/minúsculas.
  Mesmo assim NÃO prova resultados financeiros iguais.
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

A validação de revisão de SQL diferencia, por exemplo, filtros textuais 'A'
versus 'a' e identificadores citados "Amount" versus "amount".
A normalização de palavras-chave não pode apagar essas diferenças.


## Identidade do provedor/modelo (etapa de paridade Gemini)

O comparador recupera os identificadores do **provedor e modelo realmente
registrados** na evidência de geração, e opcionalmente do reparo. Resposta
sanitizada: `shadow_generator_provider`, `shadow_generator_model`,
`shadow_repair_provider`, `shadow_repair_model`,
`generator_identity_attested` e `repair_identity_attested`.

É uma verificação de proveniência, não seleção de LLM. O motor não
recebe o provedor/modelo oficial como input para o gerador, não inventa
aliases e não utiliza benchmark. A interface do Produto compara a
identidade persistida no run oficial com os identificadores retornados
aqui, **somente depois da geração**. Se qualquer parte faltar, informa
`unattested`; se os identificadores não coincidirem literalmente,
informa `identifier_mismatch`, não presume Gemini pelo padrão configurado.

Quando há proposta de reparo, a identidade do reparador precisa estar
registrada para atestar ambos; SQL reparada exige nova aprovação de
qualquer modo. Os campos da resposta têm tamanho e alfabeto restritos;
nunca são incluídos tokens, chaves ou respostas brutas do provedor.

**Limite:** nomes exatos de modelos/provedores podem diferir como alias
operacional. Sem mapeamento de provedor versionado e autorizado, não
transformar divergência de identificador em equivalência afirmada.
