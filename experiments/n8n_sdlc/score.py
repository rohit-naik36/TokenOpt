"""Deterministic quality checks, token tables and bootstrap analysis. stdlib only.

    python score.py runs.jsonl [--out scored.jsonl]

This is the only script that reads tickets/ground_truth.json.

MATCH RULE (fixed before any run): the review stage "identifies the planted defect" iff its output parses
as JSON and at least one entry in `findings` has (a) a `file` field whose final path component equals the
final component of the planted file in ground_truth.json (case-insensitive), AND (b) `issue` + " " +
`suggested_fix` text that matches at least one of that ticket's `match_regexes` (case-insensitive).
Line numbers are recorded but not required. Findings that do not match are counted as `other_findings`
(a false-positive signal, secondary). A review with verdict "approve" can still match (verdict is not part
of the rule) but is reported separately as `verdict_approve`.

Stage checks (all must hold for a stage to be ok): output parses as one JSON object (tolerant of a
markdown fence; same parser as the workflow), required keys present with the right types/enums, list
lengths inside the stated range, and done_reason != "length" (truncated output).
  triage: severity P0-P3, category bug|feature|chore|security, component str, summary str,
          risk_flags list, needs_security_review bool
  requirements: user_story str, acceptance_criteria list of 3-6 str, non_goals list, open_questions list
  plan: steps list of 3-7 {id, description, files}, risks list, test_plan list
  review: verdict approve|request_changes, findings list (<= 6) of {file, line, severity, issue,
          suggested_fix}, summary str
  release_note: title str, summary str (<= 60 words), changes list of 1-4 str, breaking bool, upgrade_notes str
Run quality pass (composite, reported) = every stage ok AND review identifies the planted defect.
QUALITY GATE (two components, each arm >= 95% of control): format rate (every stage ok) and defect-hit rate. If the
control format rate is < 0.5 the format component is declared uninformative and is not used for the gate.
The "repaired-brace" variant (output that only lacks closing brackets) is reported as a secondary column.

Cost: W = prompt_eval_count + 4 * eval_count (uncached 1, output 4). The model is unloaded before every
run, so prompt_eval_count is the full prompt (no KV-cache reuse) and no cached-token term is needed.
"""
import argparse
import json
import math
import random
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ARMS = ["control", "A", "H", "AH"]
STAGES = ["triage", "requirements", "plan", "review", "release_note"]
SEED, B = 20261015, 10_000


def parse_json(t):
    """Same tolerant parse as workflow.json: strip a fence, take first '{' to last '}'."""
    if not isinstance(t, str):
        return None
    s = re.sub(r"```\s*$", "", re.sub(r"^```(?:json)?\s*", "", t.strip(), flags=re.I))
    a, b = s.find("{"), s.rfind("}")
    if a < 0 or b < a:
        return None
    try:
        o = json.loads(s[a : b + 1])
    except json.JSONDecodeError:
        return None
    return o if isinstance(o, dict) else None


def parse_json_repaired(t):
    """Secondary: also accept output that only lacks closing brackets (same repair as the workflow's upstream parse)."""
    o = parse_json(t)
    if o is not None or not isinstance(t, str):
        return o
    s = re.sub(r"```\s*$", "", re.sub(r"^```(?:json)?\s*", "", t.strip(), flags=re.I))
    a = s.find("{")
    if a < 0:
        return None
    for tail in ("}", "]}", "}}", "]}}"):
        try:
            o = json.loads(s[a:] + tail)
            return o if isinstance(o, dict) else None
        except json.JSONDecodeError:
            pass
    return None


def _str(x):
    return isinstance(x, str)


def _strs(x, lo, hi):
    return isinstance(x, list) and lo <= len(x) <= hi and all(_str(i) for i in x)


def check_stage(stage, o):
    """Return list of failed checks (empty = ok)."""
    if o is None:
        return ["not_json"]
    f = []
    if stage == "triage":
        if o.get("severity") not in ("P0", "P1", "P2", "P3"): f.append("severity")
        if o.get("category") not in ("bug", "feature", "chore", "security"): f.append("category")
        if not _str(o.get("component")): f.append("component")
        if not _str(o.get("summary")): f.append("summary")
        if not isinstance(o.get("risk_flags"), list): f.append("risk_flags")
        if not isinstance(o.get("needs_security_review"), bool): f.append("needs_security_review")
    elif stage == "requirements":
        if not _str(o.get("user_story")): f.append("user_story")
        if not _strs(o.get("acceptance_criteria"), 3, 6): f.append("acceptance_criteria_3_6")
        if not isinstance(o.get("non_goals"), list): f.append("non_goals")
        if not isinstance(o.get("open_questions"), list): f.append("open_questions")
    elif stage == "plan":
        st = o.get("steps")
        if not (isinstance(st, list) and 3 <= len(st) <= 7 and all(isinstance(s, dict) and {"id", "description", "files"} <= s.keys() for s in st)):
            f.append("steps_3_7")
        if not isinstance(o.get("risks"), list): f.append("risks")
        if not isinstance(o.get("test_plan"), list): f.append("test_plan")
    elif stage == "review":
        if o.get("verdict") not in ("approve", "request_changes"): f.append("verdict")
        fi = o.get("findings")
        if not (isinstance(fi, list) and len(fi) <= 6 and all(isinstance(x, dict) and {"file", "line", "severity", "issue", "suggested_fix"} <= x.keys() for x in fi)):
            f.append("findings")
        if not _str(o.get("summary")): f.append("summary")
    elif stage == "release_note":
        if not _str(o.get("title")): f.append("title")
        if not (_str(o.get("summary")) and len(o["summary"].split()) <= 60): f.append("summary_le_60_words")
        if not _strs(o.get("changes"), 1, 4): f.append("changes_1_4")
        if not isinstance(o.get("breaking"), bool): f.append("breaking")
        if not _str(o.get("upgrade_notes")): f.append("upgrade_notes")
    return f


def defect_hit(review, gt):
    if review is None or not isinstance(review.get("findings"), list):
        return False, 0
    want = gt["file"].replace("\\", "/").split("/")[-1].lower()
    hit, other = False, 0
    for x in review["findings"]:
        if not isinstance(x, dict):
            continue
        got = str(x.get("file", "")).replace("\\", "/").split("/")[-1].lower()
        text = f"{x.get('issue', '')} {x.get('suggested_fix', '')}"
        if got == want and any(re.search(p, text, re.I) for p in gt["match_regexes"]):
            hit = True
        else:
            other += 1
    return hit, other


def wilson(k, n, z=1.96):
    if n == 0:
        return (float("nan"),) * 2
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", type=Path)
    ap.add_argument("--out", type=Path)
    a = ap.parse_args()
    gt = json.loads((HERE / "tickets" / "ground_truth.json").read_text(encoding="utf-8"))["tickets"]
    rows = [json.loads(l) for l in a.runs.read_text(encoding="utf-8").splitlines() if l.strip()]
    runs = {r["run_id"]: r for r in rows if r["kind"] == "run" and r["status"] == "ok"}
    herr = [r for r in rows if r["kind"] == "run" and r["status"] != "ok"]
    stages = defaultdict(dict)
    for r in rows:
        if r["kind"] == "stage" and r["run_id"] in runs:
            stages[r["run_id"]][r["stage"]] = r
    scored = []
    for rid, run in runs.items():
        st = stages[rid]
        if len(st) != 5:
            continue
        checks = {s: check_stage(s, parse_json(st[s]["output"])) + (["truncated"] if st[s].get("done_reason") == "length" else []) for s in STAGES}
        rep = {s: not check_stage(s, parse_json_repaired(st[s]["output"])) and st[s].get("done_reason") != "length" for s in STAGES}
        hit, other = defect_hit(parse_json(st["review"]["output"]), gt[run["ticket_id"]])
        hit_rep, _ = defect_hit(parse_json_repaired(st["review"]["output"]), gt[run["ticket_id"]])
        rv = parse_json(st["review"]["output"]) or {}
        eval_t = sum(st[s]["eval_count"] for s in STAGES); prompt_t = sum(st[s]["prompt_eval_count"] for s in STAGES)
        scored.append(dict(run_id=rid, ticket_id=run["ticket_id"], arm=run["arm"], rep=run["rep"], wall_s=run["wall_s"],
                           stage_checks=checks, stages_ok={s: not c for s, c in checks.items()}, stages_ok_repaired=rep, defect_hit=hit, defect_hit_repaired=hit_rep, other_findings=other,
                           verdict_approve=rv.get("verdict") == "approve", prompt_tokens=prompt_t, output_tokens=eval_t,
                           total_tokens=prompt_t + eval_t, W=prompt_t + 4 * eval_t, W_out1=prompt_t + eval_t, W_out8=prompt_t + 8 * eval_t,
                           per_stage={s: dict(prompt=st[s]["prompt_eval_count"], output=st[s]["eval_count"], total_duration_s=round((st[s]["total_duration"] or 0) / 1e9, 1)) for s in STAGES},
                           quality_pass=all(not c for c in checks.values()) and hit,
                           quality_pass_repaired=all(rep.values()) and hit_rep))
    if a.out:
        a.out.write_text("".join(json.dumps(s) + "\n" for s in scored), encoding="utf-8", newline="\n")

    by = defaultdict(list)
    for s in scored:
        by[s["arm"]].append(s)
    print(f"runs ok: {len(scored)}; harness-error attempts: {len(herr)} ({sorted({r['run_id'] for r in herr})})\n")
    print("Per arm, per stage: mean prompt tokens / output tokens")
    print("arm      " + "".join(f"{s:>20}" for s in STAGES) + "   wall_s/run")
    for arm in ARMS:
        g = by[arm]
        if g:
            m = lambda s, k: sum(x["per_stage"][s][k] for x in g) / len(g)
            print(f"{arm:<9}" + "".join(f"{m(s, 'prompt'):>11.0f}/{m(s, 'output'):<8.0f}" for s in STAGES) + f"   {sum(x['wall_s'] for x in g) / len(g):.0f}")
    print("\nPer arm: totals and quality (n = runs)")
    print("arm      n  prompt  output  total      W  | stage-ok " + " ".join(f"{s[:5]:>5}" for s in STAGES) + " | defect_hit  quality_pass (Wilson)  [repaired-brace variant]")
    for arm in ARMS:
        g = by[arm]
        if not g:
            continue
        n = len(g); mean = lambda k: sum(x[k] for x in g) / n
        ok = " ".join(f"{sum(x['stages_ok'][s] for x in g):>5}" for s in STAGES)
        qp = sum(x["quality_pass"] for x in g); lo, hi = wilson(qp, n)
        print(f"{arm:<7}{n:>3}{mean('prompt_tokens'):>8.0f}{mean('output_tokens'):>8.0f}{mean('total_tokens'):>7.0f}{mean('W'):>8.0f}  |          {ok} | {sum(x['defect_hit'] for x in g):>5}/{n}  {qp}/{n} ({lo:.2f}-{hi:.2f})  [{sum(x['quality_pass_repaired'] for x in g)}/{n}]")
    ctl = {(s["ticket_id"], s["rep"]): s for s in by["control"]}
    if len(ctl) >= 2:
        print(f"\nRatio arm/control, paired CLUSTER percentile bootstrap (resamples tickets, keeps their reps), {B} resamples, seed {SEED}")
        for arm in ARMS[1:]:
            pairs = [(ctl[(s["ticket_id"], s["rep"])], s) for s in by[arm] if (s["ticket_id"], s["rep"]) in ctl]
            if len(pairs) < 2:
                continue
            line = f"{arm:<5}n={len(pairs)}"
            for k in ("output_tokens", "total_tokens", "W", "W_out1", "W_out8"):
                rng = random.Random(SEED); v = []
                tix = defaultdict(list)
                for p in pairs:
                    tix[p[0]["ticket_id"]].append(p)
                keys = sorted(tix)
                for _ in range(B):  # cluster bootstrap: resample TICKETS, keep all reps of each drawn ticket
                    smp = [p for t in (keys[rng.randrange(len(keys))] for _ in keys) for p in tix[t]]
                    v.append(sum(p[1][k] for p in smp) / sum(p[0][k] for p in smp))
                r = sum(p[1][k] for p in pairs) / sum(p[0][k] for p in pairs)
                line += f"  {k} {r:.2f} [{pct(v, .025):.2f}, {pct(v, .975):.2f}]"
            rate = lambda i, f: sum(f(p[i]) for p in pairs) / len(pairs)
            fmt = lambda x: all(x["stages_ok"].values())
            c_f, a_f, c_h, a_h = rate(0, fmt), rate(1, fmt), rate(0, lambda x: x["defect_hit"]), rate(1, lambda x: x["defect_hit"])
            g_f = "n/a (control format rate < 0.5)" if c_f < 0.5 else ("PASS" if a_f >= 0.95 * c_f else "FAIL")
            g_h = "PASS" if a_h >= 0.95 * c_h else "FAIL"
            line += f"\n      quality gate: format {a_f:.2f} vs {c_f:.2f} -> {g_f}; defect_hit {a_h:.2f} vs {c_h:.2f} -> {g_h}; composite {rate(1, lambda x: x['quality_pass']):.2f} vs {rate(0, lambda x: x['quality_pass']):.2f}"
            print(line)
    else:
        print("\n(fewer than 2 control runs: no CIs)")
    bad = [(s["run_id"], {k: v for k, v in s["stage_checks"].items() if v}, s["defect_hit"]) for s in scored if not s["quality_pass"]]
    if bad:
        print("\nQuality failures (run, failed checks, defect_hit):")
        for b in bad:
            print(" ", b)


if __name__ == "__main__":
    main()
