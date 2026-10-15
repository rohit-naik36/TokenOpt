"""Stage 2 scoring: Stage 1 deterministic checks on Claude outputs, plus usage, W and dollar endpoints.

    python stage2_score.py [--runs full_s2_runs.jsonl] [--outputs full_s2_outputs.jsonl] [--out full_s2_scored.jsonl]
    python stage2_score.py --check-stage1      # reproduce Stage 1 bootstrap numbers from scored.jsonl

Imports the Stage 1 check functions from score.py and does not change them. The differences from score.py are
the ones recorded in STAGE2_PREREGISTRATION.md section 17: an input adapter (usage-shaped rows), W with the
cache terms of section 6, a dollar endpoint, and a reimplemented cluster bootstrap (checked against Stage 1).
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path

import score as s1
import stage2_cost as cost

HERE = Path(__file__).parent
ARMS = s1.ARMS
STAGES = s1.STAGES
SEED, B = s1.SEED, s1.B
MODEL = "claude-haiku-5-5"


def load_stage2(runs_path, outputs_path):
    rows = [json.loads(l) for l in runs_path.read_text(encoding="utf-8").splitlines() if l.strip()]
    outs = {}
    for o in (json.loads(l) for l in outputs_path.read_text(encoding="utf-8").splitlines() if l.strip()):
        outs[(o["run_id"], o["stage"])] = o["output"]
    calls = defaultdict(list)
    summaries = {}
    for r in rows:
        if r["kind"] == "call":
            calls[r["run_id"]].append(r)
        elif r["kind"] == "run":
            summaries[r["run_id"]] = r
    return summaries, calls, outs


def score_run(summary, calls, outs, gt, prices):
    """One run in the Stage 1 shape, then Stage 1 checks, then Stage 2 endpoints."""
    rid = summary["run_id"]
    by_stage = {c["stage"]: c for c in calls}
    if set(by_stage) != set(STAGES) or len(calls) != 5:
        raise ValueError(f"{rid}: expected one call per stage, got {sorted(by_stage)}")
    checks, rep, texts = {}, {}, {}
    prompt_t = out_t = cr_t = cc_t = 0
    dollars_total = 0.0
    for st in STAGES:
        c = by_stage[st]
        u = cost.as_usage(c["usage"])
        trunc = c["stop_reason"] == "max_tokens"  # section 12.4: max_tokens replaces done_reason=length
        text = outs[(rid, st)]
        texts[st] = text
        checks[st] = s1.check_stage(st, s1.parse_json(text)) + (["truncated"] if trunc else [])
        rep[st] = not s1.check_stage(st, s1.parse_json_repaired(text)) and not trunc
        d = cost.dollars(u, prices, MODEL)
        if d is None:
            raise ValueError(f"{rid}/{st}: unpriced units in usage")
        dollars_total += d
        prompt_t += u["input_tokens"] + u["cache_creation_input_tokens"] + u["cache_read_input_tokens"]
        out_t += u["output_tokens"]
        cc_t += u["cache_creation_input_tokens"]
        cr_t += u["cache_read_input_tokens"]
    hit, other = s1.defect_hit(s1.parse_json(texts["review"]), gt)
    hit_rep, _ = s1.defect_hit(s1.parse_json_repaired(texts["review"]), gt)
    rv = s1.parse_json(texts["review"]) or {}
    usage_in = prompt_t - cc_t - cr_t  # uncached input
    w = usage_in + cc_t * 1.0 + cr_t * cost.W_CACHE_READ + out_t * cost.W_OUTPUT
    return dict(
        run_id=rid, ticket_id=summary["ticket"], arm=summary["arm"], rep=summary["rep"], wall_s=summary["wall_s"],
        stage_checks=checks, stages_ok={s: not c for s, c in checks.items()}, stages_ok_repaired=rep,
        defect_hit=hit, defect_hit_repaired=hit_rep, other_findings=other, verdict_approve=rv.get("verdict") == "approve",
        prompt_tokens=prompt_t, output_tokens=out_t, cache_creation_tokens=cc_t, cache_read_tokens=cr_t,
        total_tokens=prompt_t + out_t, W=w,
        W_out1=usage_in + cc_t + cr_t * cost.W_CACHE_READ + out_t * 1.0,
        W_out8=usage_in + cc_t + cr_t * cost.W_CACHE_READ + out_t * 8.0,
        dollars=dollars_total,
        quality_pass=all(not c for c in checks.values()) and hit,
        quality_pass_repaired=all(rep.values()) and hit_rep,
    )


def cluster_ratio_ci(pairs, key):
    """Stage 1 method (score.py main): ratio of sums over paired units; ticket-cluster percentile bootstrap."""
    r = sum(p[1][key] for p in pairs) / sum(p[0][key] for p in pairs)
    rng = random.Random(SEED)
    tix = defaultdict(list)
    for p in pairs:
        tix[p[0]["ticket_id"]].append(p)
    keys = sorted(tix)
    v = []
    for _ in range(B):
        smp = [p for t in (keys[rng.randrange(len(keys))] for _ in keys) for p in tix[t]]
        v.append(sum(p[1][key] for p in smp) / sum(p[0][key] for p in smp))
    return r, s1.pct(v, 0.025), s1.pct(v, 0.975)


def pair_units(scored):
    by = defaultdict(list)
    for s in scored:
        by[s["arm"]].append(s)
    ctl = {(s["ticket_id"], s["rep"]): s for s in by["control"]}
    return {arm: [(ctl[(s["ticket_id"], s["rep"])], s) for s in by[arm] if (s["ticket_id"], s["rep"]) in ctl] for arm in ARMS[1:]}


def check_stage1():
    """Reproduce the published Stage 1 ratios from scored.jsonl (summary.txt): the bootstrap must match."""
    scored = [json.loads(l) for l in (HERE / "scored.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
    expected = {"A": {"W": (0.90, 0.86, 0.93), "output_tokens": (0.82, 0.77, 0.87), "total_tokens": (0.94, 0.91, 0.96)},
                "H": {"W": (0.71, 0.66, 0.75), "output_tokens": (0.90, 0.81, 0.98), "total_tokens": (0.60, 0.57, 0.62)},
                "AH": {"W": (0.67, 0.64, 0.69), "output_tokens": (0.79, 0.74, 0.84), "total_tokens": (0.59, 0.58, 0.61)}}
    ok = True
    for arm, keys in pair_units(scored).items():
        for k, (er, elo, ehi) in expected[arm].items():
            r, lo, hi = cluster_ratio_ci(keys, k)
            match = (round(r, 2), round(lo, 2), round(hi, 2)) == (er, elo, ehi)
            ok &= match
            print(f"Stage 1 {arm:<3} {k:<14} got {r:.2f} [{lo:.2f}, {hi:.2f}]  published {er:.2f} [{elo:.2f}, {ehi:.2f}]  {'OK' if match else 'MISMATCH'}")
    print("REPRODUCES STAGE 1" if ok else "DOES NOT REPRODUCE STAGE 1")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--runs", type=Path, default=HERE / "full_s2_runs.jsonl")
    ap.add_argument("--outputs", type=Path, default=HERE / "full_s2_outputs.jsonl")
    ap.add_argument("--out", type=Path, default=HERE / "full_s2_scored.jsonl")
    ap.add_argument("--check-stage1", action="store_true")
    a = ap.parse_args()
    if a.check_stage1:
        check_stage1()
        return
    gt = json.loads((HERE / "tickets" / "ground_truth.json").read_text(encoding="utf-8"))["tickets"]
    prices = cost.load_prices()
    summaries, calls, outs = load_stage2(a.runs, a.outputs)
    scored = [score_run(summaries[r], calls[r], outs, gt[summaries[r]["ticket"]], prices)
              for r in sorted(summaries) if summaries[r]["status"] == "ok"]
    a.out.write_text("".join(json.dumps(s) + "\n" for s in scored), encoding="utf-8", newline="\n")
    print(f"scored {len(scored)} runs -> {a.out.name}")


if __name__ == "__main__":
    main()
