"""Generate workflow.json from the frozen prompt files. Usage: python build_workflow.py

Prompt texts live in prompts/*.txt and are embedded verbatim; workflow.json is a build artifact.
Arm, model, Ollama base URL, ticket and diff are inputs in the webhook payload.
"""
import json
from pathlib import Path

HERE = Path(__file__).parent
STAGES = ["triage", "requirements", "plan", "review", "release_note"]
SYSTEM = {s: (HERE / "prompts" / f"{s}.txt").read_text(encoding="utf-8").strip() for s in STAGES}
ARM_A = (HERE / "prompts" / "arm_A.txt").read_text(encoding="utf-8")
for text in [*SYSTEM.values(), ARM_A]:
    assert "{{" not in text and "}}" not in text  # n8n expression delimiters

LIB = r"""
const SYSTEM = __SYSTEM__;
const ARM_A = __ARM_A__;
const STAGES = ['triage', 'requirements', 'plan', 'review', 'release_note'];
const P = $('Webhook').first().json.body;
const raw = {};
for (const s of STAGES) { try { raw[s] = $(s).first().json.message.content; } catch (e) { } }

function parseJ(t) {
  if (typeof t !== 'string') return null;
  const s = t.trim().replace(/^```(?:json)?\s*/i, '').replace(/```\s*$/, '');
  const a = s.indexOf('{'), b = s.lastIndexOf('}');
  if (a < 0 || b < a) return null;
  try { return JSON.parse(s.slice(a, b + 1)); } catch (e) { return null; }
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
return {
  model: P.model, stream: false, think: false, keep_alive: '10m',
  options: { temperature: 0, seed: 7, num_ctx: 12288, num_predict: 2048 },
  messages: [{ role: 'system', content: sys }, { role: 'user', content: user }]
};
"""


def body_expr(stage: str) -> str:
    lib = (
        LIB.replace("__SYSTEM__", json.dumps(SYSTEM)).replace("__ARM_A__", json.dumps(ARM_A))
    )
    lib = f"const STAGE = {json.dumps(stage)};" + lib
    assert "{{" not in lib and "}}" not in lib, [m for m in ("{{", "}}") if m in lib]
    return "={{ (function () {" + lib + "})() }}"


FINAL = r"""
const P = $('Webhook').first().json.body;
const stages = {};
for (const s of ['triage', 'requirements', 'plan', 'review', 'release_note']) {
  const r = $(s).first().json;
  stages[s] = {
    prompt_eval_count: r.prompt_eval_count,
    eval_count: r.eval_count,
    turns: 1,
    output: r.message ? r.message.content : null,
    total_duration: r.total_duration,
    done_reason: r.done_reason
  };
}
return [{ json: { run_id: P.run_id, ticket_id: P.ticket.id, arm: P.arm, stages: stages } }];
"""

nodes = [
    {
        "parameters": {"httpMethod": "POST", "path": "sdlc-bench", "responseMode": "lastNode", "options": {}},
        "id": "00000000-0000-4000-8000-000000000001",
        "name": "Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 0],
        "webhookId": "5d1c2b3a-0000-4000-8000-5d1c2b3a0001",
    }
]
connections = {"Webhook": {"main": [[{"node": STAGES[0], "type": "main", "index": 0}]]}}
for i, s in enumerate(STAGES):
    nodes.append(
        {
            "parameters": {
                "method": "POST",
                "url": "={{ $('Webhook').first().json.body.ollama_base_url.replace(/\\/$/, '') + '/api/chat' }}",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": body_expr(s),
                "options": {"timeout": 900000},
            },
            "id": f"00000000-0000-4000-8000-00000000001{i}",
            "name": s,
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [250 * (i + 1), 0],
        }
    )
    nxt = STAGES[i + 1] if i + 1 < len(STAGES) else "collect"
    connections[s] = {"main": [[{"node": nxt, "type": "main", "index": 0}]]}
nodes.append(
    {
        "parameters": {"jsCode": FINAL.strip()},
        "id": "00000000-0000-4000-8000-000000000099",
        "name": "collect",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [250 * (len(STAGES) + 1), 0],
    }
)
wf = {
    "id": "sdlcbench0000001",
    "name": "sdlc-bench",
    "nodes": nodes,
    "connections": connections,
    "active": False,
    "settings": {"executionOrder": "v1", "saveDataSuccessExecution": "none"},
    "pinData": {},
}
(HERE / "workflow.json").write_text(json.dumps(wf, indent=1) + "\n", encoding="utf-8", newline="\n")
print("workflow.json written:", len(nodes), "nodes")
