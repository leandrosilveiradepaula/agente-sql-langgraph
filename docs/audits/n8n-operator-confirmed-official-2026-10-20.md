# Baseline oficial n8n: workflow de 68 nós confirmado pelo operador

**Data da declaração:** 2026-10-20. **Fonte:** JSON fornecido pelo operador
com o nome `DEMO - Agente SQL Financeiro - Grupo Horizonte - Supabase -
granularidade semantica`. **Estado:** operador confirmou ser o workflow ativo
de produção; confirmação independente da versão published na VPS **não
realizada**. Tratar a declaração como referência operacional de trabalho, sem
inventar logs da VPS.

## Identificação verificável do anexo

| Campo | Valor |
|---|---|
| SHA-256 do JSON completo | `959bba4df209d1f506323ac9d2c4a9346cfb6a5776c1020e30841a5d9021b9e6` |
| SHA-256 da identidade do workflow | `f04761b9e98f923c3d4f6d0b2aaf2a0e7fe1abfc5f4f3c83328e9f787231dc2f` |
| SHA-256 da topologia | `05decd6515d33fb65fa96fde44e0bd0eba173238a4290604921ad82b2aa06374` |
| Nós | 68 |
| Conexões direcionadas | 78 |
| Nós alcançáveis do webhook | 60 |
| Nós não alcançáveis | 8 |
| Estado no export | `active=true` |
| Tipos | 41 Code, 11 Postgres, 10 IF, 3 Respond, 2 HTTP, 1 Webhook |

**Não versionar aqui o JSON bruto:** o arquivo fornecido contém valores
sensíveis embutidos em nós HTTP. Os hashes identificam o snapshot, mas não
equivalem a leitura de configuração published no servidor.

Este baseline **não é** a exportação histórica de 75 nós `v2.2.31`
mantida em `Agente-Financeiro/workflows/n8n/`. Os dois inventários têm
proveniência e contagens diferentes; não confundi-los.

## Semântica legada e risco operacional

A auditoria estática do JSON do operador encontrou **14 nós contendo regras
proibidas para o motor genérico**, **19 com dívida transicional** e **35
estruturais sujeitos a revisão**. Exemplos concretos confirmados:

1. Validação de pergunta e classificação de intenção: palavras-chave, nomes
   de entidades, classificações e prioridades embutidos no JavaScript.
2. Planejamento, schema, prompt SQL e gates: tabelas, colunas, relacionamentos,
   métricas financeiras, grupos contábeis, filtros, versão de orçamento e
   modelos de consulta específicos da instalação.
3. SQL cleaner: modifica semanticamente SQL gerada, inclusive inserindo
   filtros financeiros por substituição textual; não transportar a regra
   para Python nem n8n novo.
4. Relatório: inferência financeira duplicada; conversão de valores
   monetários em `Number` e possíveis zeros fictícios para nulos.
5. Configuração do datasource: consulta SQL que devolve valores fixos,
   embora o nome do nó sugira descoberta da fonte ativa.
6. Cache: sem chave de isolamento tenant claramente observável no JSON.
7. A geração de SQL percorre um caminho até o executor PostgreSQL sem gate
   de aprovação humana explícito **dentro deste workflow**. O Produto
   pode possuir outras verificações; não inferir que estão ausentes.
8. Os dois HTTP Requests ao Gemini referenciam chave de API diretamente.
   O operador decidiu rotacionar chaves em outra etapa; não replicá-las.
9. Oito nós inalcançáveis não podem ser contados como funcionalidade
   atualmente comprovada.

**Destino:** LangGraph resolve métricas, dimensões, tempo, operações,
intenção, contexto, planejamento, SQL, Security/Contract Gates e reparo;
catálogo/versionamento autorizado por tenant armazena regras específicas;
n8n continua responsável por webhook/orquestração operacional e execução
aprovada; Produto mantém authn/authz e a decisão de execução.

## Dupla execução planejada sem cutover

```text
Browser -> Produto/Next.js (auth e auditoria)
  |-> n8n OFICIAL, 68 nós -> Gemini -> resposta atual inalterada
  \-> n8n Shadow paralelo (separado, feature-flag OFF)
        -> LangGraph + Gemini (mesma pergunta e identidade autorizada)
        -> evidência, SQL proposta e métricas operacionais no Shadow
        -> avaliador compara fora do gerador
```

- O novo workflow de sete nós na PR #136 recebe somente contratos
  estruturais v1, valida o envelope e encaminha ao LangGraph. **Não possui**
  regras financeiras, queries prontas, credenciais exportadas ou executor SQL.
- O aceite HTTP 202 indica *recebimento* do evento, **não** geração correta,
  evidência persistida ou paridade.
- O disparo atual no Produto só ocorre nos caminhos em que o BFF agenda o
  `after()`; erros antecipados e rejeições precisam de plano de observabilidade
  separado, sem chamar o gerador em pedidos não autorizados.
- O percurso `execute_approved` é somente evidência em Shadow; não roda
  SQL real. Reparos criam proposta e obrigam nova aprovação.
- A versão Gemini do LangGraph, tenant autorizado, fingerprint de contexto e
  não execução real devem ser conferidos antes da ativação.
- Nunca usar SQL, golden answers, regras esperadas de benchmark ou respostas
  do fluxo oficial como entrada do gerador/planner. São referências **após**
  a geração para avaliação independente.

## Gates pendentes

- **G1:** implantação n8n Shadow isolada, prova de request + evidence
  `agent_run_id/run_id/shadow_record_id` sobre perguntas reais autorizadas
  e correspondência ao webhook oficial; nenhuma prova até aqui.
- **G2:** inventário completo e externalização das regras financeiras;
  os 14 achados são evidência do snapshot, não conclusão do inventário.
- **G3:** paridade semântica/SQL com Gemini nos dois caminhos, verificada com
  perguntas inéditas e sem fabricar respostas.
- **G4:** segregação por tenant, aprovação, rollback, segurança,
  auditoria, controle de provider e custo.
- **G5:** cutover controlado somente depois da homologação e autorização.
- **G6:** comparação Gemini x SQL-InfoDive após G5.

**Limite explícito:** esta revisão não alterou n8n, banco, credenciais,
provedor, `SEMANTIC_AGENT_VERSION`, produção ou execução de SQL real.
