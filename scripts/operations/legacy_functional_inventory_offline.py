"""Static audit of ALL published n8n nodes. Never runs SQL, n8n or an LLM.

Legacy ordinal-specific review labels are audit-only, not financial runtime
logic. The workflow must remain private; public output is hashes and topology.
"""
from __future__ import annotations

import argparse
from collections import Counter, deque
from hashlib import sha256
import json
from pathlib import Path
import re

ROLE_PATTERN = re.compile(r"^\|\s*([0-9]{1,3})\s*\|\s*([^|\r\n]+?)\s*\|\s*([^|\r\n]+?)\s*\|\s*$", re.M)
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,128}$")
REFS = re.compile(r"\$json(?:\??\.[A-Za-z_][A-Za-z0-9_]*){1,4}")
VERBS = re.compile(r"\b(SELECT|UPDATE|INSERT|DELETE|CREATE|ALTER|DROP|TRUNCATE|WITH)\b", re.I)
TYPES = {"webhook", "code", "postgres", "if", "httpRequest", "respondToWebhook"}
BUSINESS = {
    5: "CATALOG_VERSION_FIXED",
    6: "INTENT_ALIAS_LITERALS",
    7: "HISTORICAL_PATTERN_TO_PROMPT",
    8: "INLINE_FINANCIAL_FORMULAS_AND_MODELS",
    15: "AGENT_VERSION_FIXED",
    19: "LEGACY_PROVIDER_VERSION",
    22: "PHYSICAL_TABLE_MAP_AND_METRIC_RULES",
    23: "METRIC_COMPARISON_DESCRIPTORS",
    32: "FINANCIAL_REPORT_DESCRIPTORS",
    54: "METRIC_DIMENSION_LEXICONS",
}
TRANSITIONAL = {
    9, 10, 11, 12, 13, 17, 18, 20, 21, 24, 28, 30, 33, 34,
    36, 38, 42, 44, 46, 49, 51, 53, 55, 57, 58, 59, 60, 61,
    63, 64, 66, 67, 68,
}
PG_EFFECTS = {
    5: "SEMANTIC_CATALOG_READ", 18: "AUDIT_LOG_WRITE_DYNAMIC",
    21: "QUESTION_QUEUE_WRITE_DYNAMIC", 36: "SQL_CACHE_READ",
    42: "SQL_CACHE_HIT_WRITE", 46: "SQL_CACHE_UPSERT",
    49: "SQL_CACHE_INVALIDATION", 51: "MANUAL_DDL_UNREACHABLE",
    63: "RUNTIME_CONFIG_READ", 66: "PREFLIGHT_DYNAMIC",
    67: "SQL_EXECUTION_DYNAMIC",
}
IF_EFFECTS = {
    25: "TECHNICAL_VALIDATION_SUCCESS", 27: "EXECUTE_MODE",
    29: "TECHNICAL_VALIDATION_APPROVED_FLAG", 35: "CACHE_ENABLED",
    37: "CACHE_ROW_EXISTS", 41: "PREFLIGHT_CACHE_HIT",
    45: "CACHE_WRITE_ELIGIBLE", 48: "CACHE_HIT_INVALIDATION",
    56: "REPAIR_REQUIRED", 62: "PREFLIGHT_TECHNICAL_SUCCESS",
}
NO_HUMAN_APPROVAL = (25, 29, 62)


class InventoryRejected(ValueError):
    pass


def reject(reason):
    raise InventoryRejected(reason)


def digest(value):
    return sha256(value.encode("utf-8")).hexdigest()


def digest_obj(value):
    return digest(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True))


def parse_roles(markdown, count=68):
    rows = ROLE_PATTERN.findall(markdown)
    roles = {}
    for ordinal, label, owner in rows:
        idx = int(ordinal)
        if idx in roles or not 1 <= idx <= count:
            reject("ROLE_DUPLICATE_OR_RANGE")
        if len(label) > 200 or len(owner) > 200:
            reject("ROLE_TEXT_TOO_LONG")
        roles[idx] = (label.strip(), owner.strip())
    if set(roles) != set(range(1, count + 1)):
        reject("ROLE_COVERAGE_MISSING")
    return roles


def build_inventory(raw, roles, baseline, expected_nodes=68, expected_edges=78):
    if isinstance(raw, list):
        if len(raw) != 1:
            reject("MULTIPLE_WORKFLOWS")
        raw = raw[0]
    if not isinstance(raw, dict) or raw.get("active") is not True:
        reject("NOT_PUBLISHED_ACTIVE")
    if not raw.get("versionId") or raw.get("activeVersionId") != raw["versionId"]:
        reject("PUBLISHED_VERSION_DRIFT")
    nodes = raw.get("nodes")
    connection_map = raw.get("connections")
    if not isinstance(nodes, list) or len(nodes) != expected_nodes:
        reject("NODE_COUNT")
    if not isinstance(connection_map, dict) or set(roles) != set(range(1, expected_nodes + 1)):
        reject("ROLES_OR_CONNECTIONS")
    if not isinstance(baseline, dict) or len(baseline.get("nodes", [])) != expected_nodes:
        reject("BASELINE_NOT_AVAILABLE")
    name_idx, ids = {}, set()
    for i, node in enumerate(nodes, 1):
        if not isinstance(node, dict) or not isinstance(node.get("name"), str):
            reject("NODE_INVALID")
        if node["name"] in name_idx or node.get("type", "").split(".")[-1] not in TYPES:
            reject("NODE_TYPE_OR_DUPLICATE")
        if not isinstance(node.get("id"), str) or not IDENTIFIER.fullmatch(node["id"]) or node["id"] in ids:
            reject("NODE_ID_INVALID")
        ids.add(node["id"])
        name_idx[node["name"]] = i
        orig = baseline["nodes"][i - 1]
        params = node.get("parameters", {})
        if not isinstance(params, dict) or orig.get("ordinal") != i:
            reject("PARAMETERS_OR_BASELINE")
        if orig.get("node_type") != node["type"].split(".")[-1]:
            reject("PUBLISHED_NODE_TYPE_DRIFT")
        code = params.get("jsCode", "") if node["type"].endswith(".code") else ""
        query = params.get("query", "") if node["type"].endswith(".postgres") else ""
        if not isinstance(code, str) or not isinstance(query, str):
            reject("CODE_OR_QUERY_INVALID")
        for key, value in {
            "node_identity_sha256": digest(node["id"]),
            "configuration_sha256": digest_obj(params),
            "code_sha256": digest(code) if code else None,
            "query_sha256": digest(query) if query else None,
        }.items():
            if orig.get(key) != value:
                reject("WORKFLOW_BODY_DRIFT")
    edges, forward, backward = [], {i: set() for i in range(1, expected_nodes + 1)}, {i: set() for i in range(1, expected_nodes + 1)}
    for name, ports in connection_map.items():
        if name not in name_idx or not isinstance(ports, dict):
            reject("CONNECTION_INVALID")
        for kind, lanes in ports.items():
            if kind != "main" or not isinstance(lanes, list):
                reject("CONNECTION_CHANNEL_INVALID")
            for port_index, branch in enumerate(lanes):
                if not isinstance(branch, list):
                    reject("CONNECTION_BRANCH_INVALID")
                for target in branch:
                    if not isinstance(target, dict) or target.get("node") not in name_idx:
                        reject("CONNECTION_DANGLING")
                    if type(target.get("index")) is not int or not 0 <= target["index"] < 100:
                        reject("TARGET_PORT_INVALID")
                    a, b = name_idx[name], name_idx[target["node"]]
                    edges.append((a, b, kind, port_index, target["index"]))
                    forward[a].add(b); backward[b].add(a)
    if len(edges) != expected_edges or len(set(edges)) != expected_edges:
        reject("EDGE_COVERAGE_INVALID")
    old = baseline.get("edges", [])
    if set(edges) != {(e["from"], e["to"], e["connection_type"], e["source_port"], e["target_port"]) for e in old}:
        reject("EDGE_BASELINE_DRIFT")
    triggers = [i for i, n in enumerate(nodes, 1) if n["type"].endswith(".webhook")]
    if len(triggers) != 1:
        reject("WEBHOOK_COUNT")
    todo = deque(triggers); reached = set(triggers)
    while todo:
        for next_node in forward[todo.popleft()]:
            if next_node not in reached:
                todo.append(next_node); reached.add(next_node)
    reviewed = []
    for i, node in enumerate(nodes, 1):
        kind = node["type"].split(".")[-1]
        params = node["parameters"]
        cond = params.get("conditions", {}).get("conditions", []) if kind == "if" else []
        if kind == "if" and (not isinstance(cond, list) or len(cond) != 1):
            reject("CONDITIONAL_NOT_REVIEWABLE")
        if kind == "postgres" and (i not in PG_EFFECTS or params.get("operation") != "executeQuery"):
            reject("POSTGRES_OPERATION_DRIFT")
        if kind == "httpRequest":
            if params.get("method") != "POST":
                reject("HTTP_METHOD_DRIFT")
            if "generativelanguage.googleapis.com" not in str(params.get("url", "")).lower():
                reject("LLM_PROVIDER_ENDPOINT_DRIFT")
        code = params.get("jsCode", "") if kind == "code" else ""
        query = params.get("query", "") if kind == "postgres" else ""
        if kind == "code" and not code.strip():
            reject("EMPTY_CODE")
        cls = "FORBIDDEN" if i in BUSINESS else "TRANSITIONAL" if i in TRANSITIONAL else "STRUCTURAL"
        effect = PG_EFFECTS.get(i) if kind == "postgres" else IF_EFFECTS.get(i) if kind == "if" else (
            "GEMINI_REQUEST" if kind == "httpRequest" else
            "WEBHOOK_RESPONSE" if kind == "respondToWebhook" else
            "WEBHOOK_ENTRY" if kind == "webhook" else "CODE_TRANSFORM"
        )
        if not effect:
            reject("EFFECT_UNCLASSIFIED")
        role, owner = roles[i]
        reviewed.append({
            "ordinal": i, "node_type": kind,
            "disabled_in_published_export": node.get("disabled") is True,
            "functional_role": role, "proposed_owner": owner,
            "observed_effect": effect, "business_debt_class": cls,
            "hardcode_or_migration_risk": BUSINESS.get(i) or ("FUNCTIONAL_PARITY_NOT_PROVEN" if cls == "TRANSITIONAL" else "STRUCTURAL_PROCESS"),
            "source_reachability": "REACHABLE_FROM_WEBHOOK" if i in reached else "NOT_REACHABLE_FROM_WEBHOOK",
            "incoming": sorted([{"from": a, "source_port": p} for a,b,k,p,t in edges if b == i], key=lambda x:(x["from"],x["source_port"])),
            "outgoing": sorted([{"to": b, "source_port": p} for a,b,k,p,t in edges if a == i], key=lambda x:(x["source_port"],x["to"])),
            "node_id_sha256": digest(node["id"]),
            "parameter_sha256": digest_obj(params),
            "code_sha256": digest(code) if code else None,
            "query_sha256": digest(query) if query else None,
            "if_guard_paths": sorted(set(REFS.findall(str(cond[0].get("leftValue", ""))))) if cond else [],
            "if_guard_sha256": digest_obj(cond) if cond else None,
            "postgres_sql_shape": "DYNAMIC_EXPRESSION" if "{{" in query else "LITERAL" if query.strip() else "NOT_APPLICABLE",
            "postgres_lexical_verbs": sorted(set(x.upper() for x in VERBS.findall(query))),
            "financial_semantics_attested": False,
            "review_scope": "SOURCE_BOUND_STATIC_FUNCTIONAL_INVENTORY",
        })
    types = Counter(x["node_type"] for x in reviewed)
    classes = Counter(x["business_debt_class"] for x in reviewed)
    return {
        "contract": "legacy-financial-n8n-functional-review-v1",
        "status": "STATIC_FUNCTIONAL_INVENTORY_COMPLETE_FINANCIAL_PARITY_NOT_ATTESTED",
        "node_count": len(reviewed), "edge_count": len(edges),
        "reachable_count": len(reached), "unreachable_count": len(reviewed)-len(reached),
        "types": dict(sorted(types.items())), "classes": dict(sorted(classes.items())),
        "source_published": True, "identities_configs_bodies_and_edges_matched_baseline": True,
        "source_identity_hash": digest(str(raw.get("id", ""))),
        "source_sql_executed": False, "workflow_executed": False,
        "financial_meaning_approved": False, "never_feed_generator": True,
        "if_port_zero": "true", "if_port_one": "false",
        "technical_gates_not_human_approval": list(NO_HUMAN_APPROVAL),
        "nodes": reviewed,
        "edges": [{"from":a,"to":b,"connection_type":k,"source_port":p,"target_port":t} for a,b,k,p,t in sorted(edges)],
    }



def render_markdown(report):
    """Complete human-readable matrix with no raw n8n code or SQL."""
    counts = report["types"]
    lines = [
        "# Inventario funcional integral do n8n publicado - Bloco 1",
        "",
        "> Revisao estatica de todos os nos e todas as rotas por porta.",
        "> Nao representa homologacao contabil, paridade financeira ou autorizacao de cutover.",
        "",
        "## Proveniencia e verificacao",
        "",
        "- Workflow publicado e ativo: versao atual e publicada coincidem.",
        "- Identidades, parametros, corpos de Code, queries e 78 conexoes: MATCH contra o crosswalk privado anterior.",
        "- Hash do export bruto: " + report["raw_export_sha256"],
        "- Hash do export anterior: " + report["previous_export_sha256"],
        "- O hash bruto mudou; os 68 corpos/parametros e as 78 arestas conferem. Nao tratar metadados do export como equivalencia de respostas.",
        "- Nos: 68/68; conexoes dirigidas: 78/78; tipos: " + str(dict(counts)),
        "- Alcancaveis pelo webhook: " + str(report["reachable_count"]) + "; fora da rota do webhook: " + str(report["unreachable_count"]) + ".",
        "- Metodo: export publicado privado e auditoria read-only; apenas hashes, sinais tecnicos e topologia sao publicos.",
        "- A coluna Responsabilidade veio da matriz funcional previamente inspecionada e foi reconfirmada contra a mesma configuracao e codigo publicado; nao atribui sucesso em runtime.",
        "",
        "## Matriz completa dos 68 nos",
        "",
        "Classes: S = STRUCTURAL; T = TRANSITIONAL (equivalencia ainda pendente); F = FORBIDDEN de portar como literal de negocio (codigo legado pode permanecer ate cutover).",
        "Os 10 casos F sao **pontos de hardcode identificados**, nao 10 itens que representem todos os literais do legado.",
        "",
        "| No | Tipo | Responsabilidade do legado | Entrada | Saida por porta | Efeito | Classe | Prova SHA-12 |",
        "|---:|---|---|---|---|---|:---:|---|",
    ]
    short = {"STRUCTURAL": "S", "TRANSITIONAL": "T", "FORBIDDEN": "F"}
    for node in report["nodes"]:
        incoming = ",".join(str(x["from"]) for x in node["incoming"]) or "-"
        outgoing = ",".join(str(x["source_port"]) + ":" + str(x["to"]) for x in node["outgoing"]) or "-"
        sha = (node["code_sha256"] or node["query_sha256"] or node["parameter_sha256"])[:12]
        role = node["functional_role"].replace("|", "/")
        lines.append(
            "| " + str(node["ordinal"]) + " | " + node["node_type"]
            + " | " + role + " | " + incoming + " | " + outgoing
            + " | " + node["observed_effect"] + " | " + short[node["business_debt_class"]]
            + " | " + sha + " |"
        )
    lines.extend([
        "",
        "## Portas dos IF e natureza do sinal",
        "",
        "Porta 0 = verdadeiro, 1 = falso. As expressoes abaixo foram conferidas no export publicado; apenas nomes de campos tecnicos e hashes sao expostos.",
        "",
        "| IF | Condicao tecnica (campos lidos) | True:0 | False:1 | SHA-12 condicao |",
        "|---:|---|---|---|---|",
    ])
    for node in report["nodes"]:
        if node["node_type"] != "if":
            continue
        field = ", ".join(node["if_guard_paths"]) or "(expressao indireta)"
        left = ",".join(str(x["to"]) for x in node["outgoing"] if x["source_port"] == 0) or "-"
        right = ",".join(str(x["to"]) for x in node["outgoing"] if x["source_port"] == 1) or "-"
        lines.append(
            "| " + str(node["ordinal"]) + " | " + field + " | " + left
            + " | " + right + " | " + node["if_guard_sha256"][:12] + " |"
        )
    lines.extend([
        "",
        "O IF 25 testa sucesso de validacao tecnica do no 12; IF 29 testa aprovacao tecnica do no 28; IF 62 testa resultado de preflight. Nenhum equivale a aprovacao humana.",
        "",
        "## Onze pontos de PostgreSQL e seus efeitos",
        "",
        "| No | Papel em workflow | Expressao SQL | Verbos visiveis no texto |",
        "|---:|---|---|---|",
    ])
    for node in report["nodes"]:
        if node["node_type"] != "postgres":
            continue
        words = ",".join(node["postgres_lexical_verbs"]) or "(comando dinamico/nao visivel)"
        lines.append("| " + str(node["ordinal"]) + " | " + node["observed_effect"] +
                     " | " + node["postgres_sql_shape"] + " | " + words + " |")
    unreachable = [str(n["ordinal"]) for n in report["nodes"]
                   if n["source_reachability"] == "NOT_REACHABLE_FROM_WEBHOOK"]
    cases = [n for n in report["nodes"] if n["business_debt_class"] == "FORBIDDEN"]
    lines.extend([
        "",
        "## Hardcodes identificados: nao migrar valores para Python/TypeScript",
        "",
        "| No | Achado funcional localizado | Tratamento |",
        "|---:|---|---|",
    ])
    for n in cases:
        lines.append("| " + str(n["ordinal"]) + " | " + n["hardcode_or_migration_risk"] +
                     " | Externalizar via contexto financeiro versionado e aprovado, sem copiar literal |")
    lines.extend([
        "",
        "## Dependencias corretamente separadas",
        "",
        "- Os nos fora da rota inicial do webhook sao: " + ", ".join(unreachable) + ". Nao exclui-los sem verificar chamada indireta, conexao manual ou efeitos historicos.",
        "- Os nos 10 e 58 fazem POST HTTP ao provider LLM. Nao ha prova de invocacao real nesta auditoria.",
        "- Os nos 66/67 recebem SQL por expressao dinamica. Preflight nao autoriza execucao; SQL reparada exige nova aprovacao no Produto.",
        "- O G5 selado e os 77 registros da versao do no 5 continuam sem interpretacao financeira homologada. Esta dependencia nao invalida o inventario estatico concluido.",
        "- FORBIDDEN nesta matriz sinaliza trechos de negocio confirmados no codigo legado, nao auditoria item a item dos milhares de literais existentes.",
        "- Conectores, webhooks, cache e persistencia continuam no n8n; inteligencia dinamica e regras aprovadas vao para LangGraph/contexto sem hardcode.",
        "- Nao foram executados workflow, SQL financeira, LLM, descriptografia, alteracoes de n8n ou de banco.",
        "",
        "## Resultado de aceite desta tarefa",
        "",
        "**Inventario funcional estatico dos 68 nos: CONCLUIDO.**",
        "**Censo da operacao publicado e historico: 68 identidades, 68 corpos/configuracoes conferidos, 78 arestas, 10 IF, 11 PostgreSQL e 2 HTTP.**",
        "**Significado contabil, portabilidade entre clientes reais, Gemini Shadow e paridade numerica: NAO HOMOLOGADOS; fases posteriores.**",
        "",
    ])
    return "\n".join(lines)

def main():
    a = argparse.ArgumentParser()
    for flag in ("workflow", "roles", "baseline", "output"):
        a.add_argument("--" + flag, type=Path, required=True)
    args = a.parse_args()
    workflow_bytes = args.workflow.read_bytes()
    baseline = json.loads(args.baseline.read_text())
    report = build_inventory(
        json.loads(workflow_bytes),
        parse_roles(args.roles.read_text()),
        baseline,
    )
    report["raw_export_sha256"] = sha256(workflow_bytes).hexdigest()
    report["previous_export_sha256"] = baseline["source"]["workflow_export_sha256"]
    report["role_source_sha256"] = sha256(args.roles.read_bytes()).hexdigest()
    report["baseline_crosswalk_sha256"] = sha256(args.baseline.read_bytes()).hexdigest()
    if args.output.exists() or not args.output.parent.is_dir():
        reject("OUTPUT_EXISTS_OR_MISSING_PARENT")
    args.output.write_text(json.dumps(report, ensure_ascii=True, sort_keys=True, separators=(",", ":")) + "\n")
    print("REPORT_SHA256=" + sha256(args.output.read_bytes()).hexdigest())
    print("FUNCTIONAL_INVENTORY=COMPLETE_STATIC")
    print("NODES="+str(report["node_count"]))
    print("EDGES="+str(report["edge_count"]))
    print("BASELINE=EXACT_SOURCE_AND_TOPOLOGY_MATCH")
    print("FINANCIAL_MEANING_APPROVED=false")


if __name__ == "__main__":
    main()
