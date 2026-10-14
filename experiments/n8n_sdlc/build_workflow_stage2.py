"""Generate workflow_stage2.json: the Stage 1 SDLC chain with an Anthropic Messages backend. Stdlib only.

    python build_workflow_stage2.py

Stage 1 (build_workflow.py -> workflow.json) is frozen and not touched. Both backends run through the same
five HTTP Request nodes; the webhook input `backend` selects the endpoint, body shape and usage mapping.

Failure handling: HTTP nodes use neverError, so a 429/529/5xx comes back as data. Each `guard_<stage>` Code
node checks the stage before it and, on a non-200, throws `SDLC_STAGE_FAILED {json}` carrying the failed
stage's status, retry-after and request-id plus the completed earlier stages (their usage is billed and must be
logged). The runner parses that error and retries the run with backoff. The last stage is checked in `collect`.

Latency: each guard stamps `t_start` just before its stage; stage latency = next guard's stamp minus this one
(includes n8n overhead, so it is an upper bound on API latency).

The API key is read from the n8n container environment ($env.ANTHROPIC_API_KEY, set with `docker run -e NAME`);
it is never in the webhook payload, the workflow JSON, or the execution data (EXECUTIONS_DATA_SAVE_ON_ERROR=none).
"""
import json
import uuid
from pathlib import Path

HERE = Path(__file__).parent
STAGES = ["triage", "requirements", "plan", "review", "release_note"]
SYSTEM = {s: (HERE / "prompts" / f"{s}.txt").read_text(encoding="utf-8").strip() for s in STAGES}
ARM_A = (HERE / "prompts" / "arm_A.txt").read_text(encoding="utf-8")
for text in [*SYSTEM.values(), ARM_A]:
    assert "{{" not in text and "}}" not in text  # n8n expression delimiters

# Shared helpers. Used in Code nodes (no expression parsing) and inside the jsonBody expression.
COMMON = r"""
const STAGES = ['triage', 'requirements', 'plan', 'review', 'release_note'];
const P = $('Webhook').first().json.body;
function got(s) {
  try { const j = $(s).first().json; return j && j.statusCode !== undefined ? j : null; } catch (e) { return null; }
}
function startOf(s) {
  try { return $('guard_' + s).first().json.t_start; } catch (e) { return null; }
}
function textOf(j) {
  const b = (j && j.body) || {};
  if (P.backend === 'anthropic') return (b.content || []).filter(c => c.type === 'text').map(c => c.text).join('');
  return b.message ? b.message.content : null;
}
function usageOf(j) {
  const b = (j && j.body) || {};
  if (P.backend === 'anthropic') return b.usage || null;
  return { input_tokens: b.prompt_eval_count, output_tokens: b.eval_count };
}
function summary(k) {
  const s = STAGES[k];
  const j = got(s) || {};
  const b = j.body || {};
  const h = j.headers || {};
  const start = startOf(s);
  const end = (k + 1 < STAGES.length ? startOf(STAGES[k + 1]) : null) || Date.now();
  return {
    http_status: j.statusCode === undefined ? null : j.statusCode,
    request_id: h['request-id'] || null,
    stop_reason: b.stop_reason || b.done_reason || null,
    usage_raw: usageOf(j),
    output: textOf(j),
    latency_ms: start ? end - start : null
  };
}
function failure(k) {
  const s = STAGES[k];
  const j = got(s) || {};
  const b = j.body || {};
  const h = j.headers || {};
  const completed = {};
  for (let i = 0; i < k; i++) { const c = summary(i); delete c.output; completed[STAGES[i]] = c; }
  const payload = {
    failed_stage: s,
    http_status: j.statusCode === undefined ? null : j.statusCode,
    error_type: (b.error && b.error.type) || b.type || null,
    error_message: String((b.error && b.error.message) || b.error || '').slice(0, 300),
    request_id: h['request-id'] || null,
    retry_after: h['retry-after'] || null,
    completed: completed
  };
  return new Error('SDLC_STAGE_FAILED ' + JSON.stringify(payload));
}
"""

BODY_LIB = r"""
const STAGE = __STAGE__;
const SYSTEM = __SYSTEM__;
const ARM_A = __ARM_A__;
__COMMON__
const idx = STAGES.indexOf(STAGE);
const raw = {};
for (const s of STAGES.slice(0, idx)) raw[s] = textOf(got(s));
function parseJ(t) {
  if (typeof t !== 'string') return null;
  const s = t.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
  const a = s.indexOf('{'), b = s.lastIndexOf('}');
  if (a < 0 || b < a) return null;
  const body = s.slice(a, b + 1);
  for (const tail of ['', ']', '] }', ']', ' }']) {
    try { return JSON.parse(body + tail); } catch (e) { }
  }
  return null;
}
function up(s) {
  const o = parseJ(raw[s]);
  return o === null ? { unparsed_upstream: String(raw[s] || '').slice(0, 1500) } : o;
}
function plain(stage) {
  const parts = ['## Ticket', JSON.stringify(P.ticket, null, 2)];
  for (const s of STAGES.slice(0, STAGES.indexOf(stage))) {
    parts.push('## Output of ' + s + ' stage', raw[s] === undefined ? '(missing)' : raw[s]);
  }
  if (stage === 'review') parts.push('## Diff', P.diff);
  return parts.join('\n\n');
}
function needed(stage) {
  const t = P.ticket;
  if (stage === 'triage') return { title: t.title, description: t.description, labels: t.labels, priority_hint: t.priority_hint, environment: t.environment };
  const tr = up('triage');
  if (stage === 'requirements') return { title: t.title, description: t.description, triage: { severity: tr.severity, category: tr.category, component: tr.component } };
  const rq = up('requirements');
  if (stage === 'plan') return { title: t.title, acceptance_criteria: rq.acceptance_criteria, component: tr.component, risk_flags: tr.risk_flags };
  const pl = up('plan');
  const steps = Array.isArray(pl.steps) ? pl.steps : [];
  if (stage === 'review') return { title: t.title, acceptance_criteria: rq.acceptance_criteria, plan_steps: steps.map(x => ({ description: x.description, files: x.files })), diff: P.diff };
  const rv = up('review');
  const findings = Array.isArray(rv.findings) ? rv.findings : [];
  return { ticket_id: t.id, title: t.title, user_story: rq.user_story, category: tr.category, review_verdict: rv.verdict, review_finding_count: findings.length };
}
const ARMS = ['control', 'A', 'H', 'AH'];
if (ARMS.indexOf(P.arm) < 0) throw new Error('bad arm: ' + P.arm);
const useH = P.arm === 'H' || P.arm === 'AH';
const useA = P.arm === 'A' || P.arm === 'AH';
const sys = SYSTEM[STAGE] + (useA ? '\n\n' + ARM_A : '');
const user = useH ? JSON.stringify(needed(STAGE), null, 2) : plain(STAGE);
if (P.backend === 'anthropic') {
  const sysBlock = { type: 'text', text: sys };
  if (P.caching === 'fixed') sysBlock.cache_control = { type: 'ephemeral' };
  return { model: P.model, max_tokens: P.max_tokens, system: [sysBlock], messages: [{ role: 'user', content: user }], thinking: { type: 'disabled' } };
}
return {
  model: P.model, stream: false, think: false, keep_alive: '10m',
  options: { temperature: P.temperature, seed: P.seed, num_ctx: 12288, num_predict: P.max_tokens },
  messages: [{ role: 'system', content: sys }, { role: 'user', content: user }]
};
"""


def body_expr(stage: str) -> str:
    lib = (
        BODY_LIB.replace("__STAGE__", json.dumps(stage))
        .replace("__SYSTEM__", json.dumps(SYSTEM))
        .replace("__ARM_A__", json.dumps(ARM_A))
        .replace("__COMMON__", COMMON)
    )
    assert "{{" not in lib and "}}" not in lib, [m for m in ("{{", "}}") if m in lib]
    return "={{ (function () {" + lib + "})() }}"


def guard_code(i: int) -> str:
    check = ""
    if i > 0:
        check = f"const prev = got(STAGES[{i - 1}]);\nif (prev && prev.statusCode !== 200) throw failure({i - 1});\n"
    return COMMON + "\n" + check + "return [{ json: { t_start: Date.now() } }];"


COLLECT = COMMON + r"""
const last = got('release_note');
if (last && last.statusCode !== 200) throw failure(STAGES.length - 1);
const stages = {};
STAGES.forEach((s, k) => { stages[s] = summary(k); });
return [{ json: { run_id: P.run_id, ticket_id: P.ticket.id, arm: P.arm, backend: P.backend, model: P.model,
  caching: P.caching, stages: stages } }];
"""

URL = (
    "={{ $('Webhook').first().json.body.backend === 'anthropic' "
    "? ($('Webhook').first().json.body.anthropic_base_url || 'https://api.anthropic.com').replace(/\\/$/, '') + '/v1/messages' "
    ": $('Webhook').first().json.body.ollama_base_url.replace(/\\/$/, '') + '/api/chat' }}"
)
API_KEY = "={{ $('Webhook').first().json.body.backend === 'anthropic' ? $env.ANTHROPIC_API_KEY : 'not-used' }}"

nodes = [
    {
        "parameters": {"httpMethod": "POST", "path": "sdlc-bench-s2", "responseMode": "lastNode", "options": {}},
        "id": "00000000-0000-4000-8000-000000000001",
        "name": "Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 0],
        "webhookId": str(uuid.UUID("5d1c2b3a-0000-4000-8000-5d1c2b3a0002")),
    }
]
connections = {}
prev_node = "Webhook"
x = 0


def add(node):
    global prev_node
    nodes.append(node)
    connections.setdefault(prev_node, {"main": [[{"node": node["name"], "type": "main", "index": 0}]]})
    prev_node = node["name"]


for i, s in enumerate(STAGES):
    x += 250
    add({
        "parameters": {"jsCode": guard_code(i).strip()},
        "id": f"00000000-0000-4000-8000-00000000002{i}",
        "name": f"guard_{s}",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [x, 0],
    })
    x += 250
    add({
        "parameters": {
            "method": "POST",
            "url": URL,
            "sendHeaders": True,
            "headerParameters": {"parameters": [
                {"name": "x-api-key", "value": API_KEY},
                {"name": "anthropic-version", "value": "2023-06-01"},
            ]},
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": body_expr(s),
            "options": {"timeout": 900000, "response": {"response": {"fullResponse": True, "neverError": True}}},
        },
        "id": f"00000000-0000-4000-8000-00000000003{i}",
        "name": s,
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [x, 0],
    })
x += 250
add({
    "parameters": {"jsCode": COLLECT.strip()},
    "id": "00000000-0000-4000-8000-000000000099",
    "name": "collect",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x, 0],
})

# Error routing: a guard or collect that throws sends its item to collect_fail (error output 1), which
# returns the failure as normal data. A thrown webhook error would lose the message and the billed usage.
COLLECT_FAIL = r"""
const MARK = 'SDLC_STAGE_FAILED ';
function findMark(v) {
  if (typeof v === 'string') return v.indexOf(MARK) >= 0 ? v : null;
  if (v && typeof v === 'object') {
    for (const k of Object.keys(v)) { const r = findMark(v[k]); if (r) return r; }
  }
  return null;
}
const msg = findMark($input.all().map(it => it.json)) || '';
let payload;
const from = msg.indexOf('{', msg.indexOf(MARK)), to = msg.lastIndexOf('}');
try { payload = JSON.parse(msg.slice(from, to + 1)); } catch (e) { payload = { unparsed: msg.slice(0, 500), len: msg.length, err: String(e).slice(0, 200) }; }
return [{ json: { sdlc_failure: payload } }];
"""
nodes.append({
    "parameters": {"jsCode": COLLECT_FAIL.strip()},
    "id": "00000000-0000-4000-8000-000000000098",
    "name": "collect_fail",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [x + 250, 300],
})
for node in nodes:
    if node["name"].startswith("guard_") or node["name"] == "collect":
        node["onError"] = "continueErrorOutput"
for s in STAGES:
    connections[f"guard_{s}"]["main"].append([{"node": "collect_fail", "type": "main", "index": 0}])
connections["collect"] = {"main": [[], [{"node": "collect_fail", "type": "main", "index": 0}]]}

wf = {
    "id": "sdlcbench0000002",
    "name": "sdlc-bench-stage2",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none", "saveDataErrorExecution": "none"},
    "pinData": {},
}
(HERE / "workflow_stage2.json").write_text(json.dumps(wf, indent=1) + "\n", encoding="utf-8", newline="\n")
print("workflow_stage2.json written:", len(nodes), "nodes")
