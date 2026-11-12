'use strict';
// Audit-only: parse published n8n JavaScript without executing any node code.
// No LLM, benchmark or business SQL. Never emit raw literals, hashes of literal
// values, prompts or full code. The parser path is explicit and external.
const fs = require('node:fs');
const crypto = require('node:crypto');

function fail(reason) {
  process.stderr.write('LITERAL_AST_AUDIT_REJECTED=' + reason + '\n');
  process.exitCode = 2;
  throw new Error(reason);
}
function parseArgs(argv) {
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    const key = argv[i];
    if (!key || !key.startsWith('--') || i + 1 >= argv.length || args[key]) {
      fail('ARGUMENTS_INVALID');
    }
    args[key] = argv[i + 1];
  }
  for (const key of ['--workflow', '--literal-baseline', '--policy', '--parser-path']) {
    if (!args[key]) fail('ARGUMENT_MISSING');
  }
  return args;
}
function sha(value) {
  return crypto.createHash('sha256').update(value, 'utf8').digest('hex');
}
function fold(value) {
  return value.toLowerCase().normalize('NFKD').replace(/[\u0300-\u036f]/g,'');
}
function validatePolicy(policy) {
  if (policy.contract !== 'legacy-n8n-audit-review-signals-v1'
    || policy.source_use !== 'EVALUATION_ONLY_NEVER_GENERATOR'
    || policy.human_financial_approval !== false
    || !Array.isArray(policy.review_stems)
    || !Array.isArray(policy.business_review_nodes)
    || !Array.isArray(policy.transitional_review_nodes)) fail('POLICY_INVALID');
  const values = new Set([...policy.business_review_nodes, ...policy.transitional_review_nodes]);
  if (values.size !== policy.business_review_nodes.length + policy.transitional_review_nodes.length
    || [...values].some(n => !Number.isInteger(n) || n < 1 || n > 68)
    || policy.review_stems.some(term => typeof term !== 'string' || !/^[a-z]{3,64}$/i.test(fold(term)))) {
    fail('POLICY_UNTRUSTED');
  }
  return {
    ...policy,
    review_stems: policy.review_stems.map(fold),
    businessSet: new Set(policy.business_review_nodes),
    transitionSet: new Set(policy.transitional_review_nodes),
  };
}
function candidate(line, enclosingFunction, ordinal, policy) {
  const raw = fold(line);
  const scope = fold(enclosingFunction || '');
  const matches = (v) => policy.review_stems.some(term => v.includes(term));
  if (matches(raw) || (policy.businessSet.has(ordinal) && matches(scope))) return 'F';
  if (policy.transitionSet.has(ordinal)) return 'T';
  if (!policy.businessSet.has(ordinal)) return 'S';
  return 'U';
}
function collect(node, parentFunction, sourceLines, ordinal, policy, entries) {
  if (!node || typeof node !== 'object') return;
  if (Array.isArray(node)) {
    for (const child of node) collect(child, parentFunction, sourceLines, ordinal, policy, entries);
    return;
  }
  let functionName = parentFunction;
  if (node.type === 'FunctionDeclaration' && node.id && typeof node.id.name === 'string') {
    functionName = node.id.name;
  } else if ((node.type === 'FunctionExpression' || node.type === 'ArrowFunctionExpression')
             && node.id && typeof node.id.name === 'string') {
    functionName = node.id.name;
  }
  if ((node.type === 'Literal' && typeof node.value === 'string') || node.type === 'TemplateLiteral') {
    const line = node.loc.start.line;
    const staticSize = node.type === 'Literal'
      ? node.value.length
      : node.quasis.reduce((sum, item) => sum + (item.value.raw || '').length, 0);
    const kind = node.type === 'Literal' ? 's' : 't';
    const category = candidate(sourceLines[line - 1] || '', functionName, ordinal, policy);
    entries.push([node.start, line, node.loc.start.column, kind, staticSize <= 10 ? 'q' : 'l', category]);
  }
  for (const key of Object.keys(node)) {
    if (key === 'loc' || key === 'range' || key === 'start' || key === 'end') continue;
    const child = node[key];
    if (!child || typeof child !== 'object') continue;
    if (key === 'value' && node.type === 'Literal') continue;
    if (Array.isArray(child)) {
      for (const item of child) {
        if (item && typeof item === 'object' && typeof item.type === 'string') {
          collect(item, functionName, sourceLines, ordinal, policy, entries);
        }
      }
    } else if (typeof child.type === 'string') {
      collect(child, functionName, sourceLines, ordinal, policy, entries);
    }
  }
}
function main() {
  const args = parseArgs(process.argv.slice(2));
  const acorn = require(args['--parser-path']);
  if (typeof acorn.parse !== 'function') fail('ACORN_NOT_AVAILABLE');
  const content = JSON.parse(fs.readFileSync(args['--workflow'], 'utf8'));
  const workflow = Array.isArray(content) ? content[0] : content;
  const legacy = JSON.parse(fs.readFileSync(args['--literal-baseline'], 'utf8'));
  const rawPolicy = JSON.parse(fs.readFileSync(args['--policy'], 'utf8'));
  const policy = validatePolicy(rawPolicy);
  if (!workflow || !workflow.active || workflow.versionId !== workflow.activeVersionId
      || !Array.isArray(workflow.nodes) || workflow.nodes.length !== 68
      || legacy.code_node_count !== 41 || legacy.counts.string_literal_count !== 3403
      || legacy.counts.literal_over_10_count !== 1987) fail('BASELINE_INCOMPATIBLE');
  const indexed = new Map(legacy.nodes.map(n => [n.node_ordinal,n]));
  if (indexed.size !== 41) fail('LEGACY_INDEX_AMBIGUOUS');
  const result = {
    contract: 'legacy-n8n-ast-all-literal-source-inventory-v1',
    status: 'ALL_AST_LITERALS_PINNED_CLASSIFICATION_CANDIDATES_ONLY',
    parser: 'acorn',
    parser_version: acorn.version,
    published_workflow_sha256: sha(fs.readFileSync(args['--workflow'], 'utf8')),
    review_policy_sha256: sha(fs.readFileSync(args['--policy'], 'utf8')),
    legacy_original_literal_count: 3403,
    legacy_long_anchor_count: 1987,
    legacy_short_unanchored_count: 1416,
    code_nodes: 41,
    raw_literal_values_published: false,
    original_literal_hashes_published: false,
    financial_semantics_approved: false,
    benchmark_accessed: false,
    node_code_executed: false,
    customer_financial_sql_executed: false,
    nodes: [],
  };
  for (let i=0;i<workflow.nodes.length;i++) {
    const node=workflow.nodes[i];
    if (!node.type.endsWith('.code')) continue;
    const ordinal=i+1;
    const code=node.parameters && node.parameters.jsCode;
    const base=indexed.get(ordinal);
    if (typeof code!=='string' || !base || base.code_sha256!==sha(code)) fail('NODE_SOURCE_DRIFT');
    let ast;
    try {
      ast=acorn.parse(code,{
        ecmaVersion: 'latest', sourceType: 'script',
        allowReturnOutsideFunction: true,allowAwaitOutsideFunction: true, locations:true,
      });
    } catch (error) {
      fail('JS_PARSE_FAILED_NODE_'+ordinal);
    }
    const lines=code.split('\n');
    const entries=[];
    collect(ast,null,lines,ordinal,policy,entries);
    entries.sort((a,b)=>a[0]-b[0]);
    for (let j=1;j<entries.length;j++) if (entries[j][0]===entries[j-1][0]) fail('DUPLICATE_OFFSET');
    const categories={F:0,T:0,S:0,U:0};
    const sizes={q:0,l:0};
    for (const item of entries) {
      categories[item[5]]+=1;
      sizes[item[4]]+=1;
    }
    result.nodes.push({
      ordinal,
      code_sha256:base.code_sha256,
      source_line_count:lines.length,
      previous_count:base.string_literal_count,
      syntax_literal_count:entries.length,
      delta_from_legacy:entries.length-base.string_literal_count,
      short_syntax_literals:sizes.q,
      long_syntax_literals:sizes.l,
      candidate_counts:categories,
      entries,
    });
  }
  if (result.nodes.length!==41) fail('CODE_NODE_COUNT_MISMATCH');
  result.syntax_literal_total=result.nodes.reduce((n,node)=>n+node.syntax_literal_count,0);
  result.short_syntax_literals=result.nodes.reduce((n,node)=>n+node.short_syntax_literals,0);
  result.long_syntax_literals=result.nodes.reduce((n,node)=>n+node.long_syntax_literals,0);
  result.delta_from_legacy=result.syntax_literal_total-3403;
  result.candidate_counts={F:0,T:0,S:0,U:0};
  for(const node of result.nodes) {
    for(const name of Object.keys(result.candidate_counts)) result.candidate_counts[name]+=node.candidate_counts[name];
  }
  process.stdout.write(JSON.stringify(result)+'\n');
}
main();
