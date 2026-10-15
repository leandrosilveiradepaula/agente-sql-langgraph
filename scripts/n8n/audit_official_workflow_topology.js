#!/usr/bin/env node
"use strict";

// Sanitized structural audit of an n8n workflow export. Never print names,
// expressions, parameters, URLs, headers, credentials, script text, or SQL.
const fs = require("node:fs");
const crypto = require("node:crypto");

const MAX_EXPORT_BYTES = 32 * 1024 * 1024;
const MAX_WORKFLOWS = 1000;
const MAX_INDEX_ROWS = 100;
const MAX_NODES = 250;
const ID_RE = /^[A-Za-z0-9_-]{1,128}$/;

function reject(code) {
  process.stdout.write("N8N_TOPOLOGY_AUDIT=" + code + "\n");
  process.exitCode = 2;
}

function kind(type) {
  if (typeof type !== "string") return "unknown";
  const t = type.toLowerCase().split(".").pop();
  if (t === "respondtowebhook") return "response";
  if (t === "httprequest") return "http";
  if (t === "executeworkflow") return "subworkflow";
  if (t === "merge") return "join";
  if (t === "if" || t === "switch" || t === "filter") return "branch";
  if (t === "code" || t === "function" || t === "functionitem") return "code";
  if (t === "postgres" || t === "mysql" || t === "microsoftsql" ||
      t === "sqlite" || t === "duckdb") return "database";
  if (t.endsWith("trigger") || t === "webhook" || t === "start" ||
      t === "formtrigger") return "trigger";
  if (t === "wait") return "wait";
  return "other";
}

function inspect(workflow, index) {
  if (!workflow || typeof workflow !== "object" || !Array.isArray(workflow.nodes)) {
    throw new Error("invalid_export_shape");
  }
  if (workflow.nodes.length > MAX_NODES) {
    throw new Error("too_many_nodes");
  }

  const nodes = workflow.nodes;
  const byName = new Map();
  nodes.forEach((node, i) => {
    if (typeof node.name === "string") byName.set(node.name, i);
  });
  const edges = [];
  const connections = workflow.connections || {};
  if (connections && typeof connections === "object") {
    for (const [source, types] of Object.entries(connections)) {
      const from = byName.get(source);
      if (from === undefined || !types || typeof types !== "object") continue;
      for (const groups of Object.values(types)) {
        if (!Array.isArray(groups)) continue;
        for (const group of groups) {
          if (!Array.isArray(group)) continue;
          for (const edge of group) {
            const to = byName.get(edge && edge.node);
            if (to !== undefined) edges.push([from, to]);
          }
        }
      }
    }
  }

  const counts = Object.create(null);
  for (const node of nodes) {
    const k = kind(node.type);
    counts[k] = (counts[k] || 0) + 1;
  }
  const id = typeof workflow.id === "string" && ID_RE.test(workflow.id)
    ? workflow.id : "invalid_id_" + index;
  const digest = crypto.createHash("sha256")
    .update(typeof workflow.name === "string" ? workflow.name : "")
    .digest("hex").slice(0, 12);
  return {
    id, active: workflow.active === true,
    nodes, edges, counts, digest
  };
}

function main() {
  const file = process.argv[2];
  const selected = process.argv[3] || "";
  if (!file || (selected && !ID_RE.test(selected))) return reject("INVALID_ARGUMENTS");
  let workflows;
  try {
    const stat = fs.statSync(file);
    if (stat.size > MAX_EXPORT_BYTES || stat.size === 0) return reject("EXPORT_SIZE_INVALID");
    const parsed = JSON.parse(fs.readFileSync(file, "utf8"));
    workflows = Array.isArray(parsed)
      ? parsed : (parsed && Array.isArray(parsed.workflows) ? parsed.workflows : [parsed]);
  } catch (_) {
    return reject("EXPORT_READ_FAILED");
  }
  if (!Array.isArray(workflows) || workflows.length > MAX_WORKFLOWS) {
    return reject("EXPORT_COUNT_INVALID");
  }
  let results;
  try {
    results = workflows.map(inspect);
  } catch (_) {
    return reject("EXPORT_STRUCTURE_INVALID");
  }

  process.stdout.write("N8N_AUDIT_MODE=" + (selected ? "DETAIL" : "INDEX") + "\n");
  process.stdout.write("WORKFLOW_COUNT=" + results.length + "\n");
  process.stdout.write("ACTIVE_COUNT=" + results.filter(x => x.active).length + "\n");
  process.stdout.write("EXPORTED_DEFINITION=current_draft_or_legacy\n");
  process.stdout.write("PUBLISHED_VERSION_VERIFIED=false\n");
  process.stdout.write("RAW_WORKFLOW_CONTENT_EXPOSED=false\n");

  if (!selected) {
    const sorted = [...results].sort((a, b) => Number(b.active) - Number(a.active));
    for (const wf of sorted.slice(0, MAX_INDEX_ROWS)) {
      const fmt = key => wf.counts[key] || 0;
      process.stdout.write(
        "WORKFLOW id=" + wf.id +
        " active=" + wf.active +
        " name_fp=" + wf.digest +
        " nodes=" + wf.nodes.length +
        " edges=" + wf.edges.length +
        " triggers=" + fmt("trigger") +
        " responses=" + fmt("response") +
        " http=" + fmt("http") +
        " database=" + fmt("database") +
        " subworkflows=" + fmt("subworkflow") + "\n"
      );
    }
    if (sorted.length > MAX_INDEX_ROWS) {
      process.stdout.write("WORKFLOW_INDEX_TRUNCATED=true\n");
    }
    process.stdout.write("N8N_TOPOLOGY_AUDIT=PASS\n");
    return;
  }

  const wf = results.find(x => x.id === selected);
  if (!wf) return reject("WORKFLOW_NOT_FOUND");
  process.stdout.write("WORKFLOW_ID=" + wf.id + "\n");
  process.stdout.write("WORKFLOW_ACTIVE=" + wf.active + "\n");
  process.stdout.write("WORKFLOW_NAME_FINGERPRINT=" + wf.digest + "\n");
  for (const [i, node] of wf.nodes.entries()) {
    const incoming = wf.edges.filter(([_, to]) => to === i).length;
    const outgoing = wf.edges.filter(([from]) => from === i)
      .map(([_, to]) => to).sort((a, b) => a - b);
    process.stdout.write(
      "NODE index=" + i + " kind=" + kind(node.type) +
      " disabled=" + (node.disabled === true) +
      " incoming=" + incoming +
      " outgoing=" + outgoing.length +
      " to=" + (outgoing.length ? outgoing.join(",") : "-") + "\n"
    );
  }
  process.stdout.write("N8N_TOPOLOGY_AUDIT=PASS\n");
}

main();
