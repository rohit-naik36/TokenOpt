"""Stage 2 tables: per-arm totals, ratios vs control with ticket-cluster CIs, pre-registered gates, Stage 1 side by side.

    python stage2_analysis.py            # prints the markdown tables used in STAGE2_RESULTS.md

Uses stage2_score.cluster_ratio_ci (checked against Stage 1 numbers) and score.wilson/pct. Decision labels follow
STAGE2_PREREGISTRATION.md section 10; the quality gate follows score.py (format component uninformative if control < 0.5).
"""
import json
from collections import Counter, defaultdict
from pathlib import Path

import score as s1
import stage2_score as s2

HERE = Path(__file__).parent
ARMS = s1.ARMS
ENDPOINTS = [("W", "W"), ("total tokens", "total_tokens"), ("output tokens", "output_tokens"), ("dollars", "dollars")]
SENS = [("W out=1", "W_out1"), ("W out=8", "W_out8")]


def label(lo, hi):
    if hi < 1:
        return "reduction"
    if lo > 1:
        return "increase"
    if lo >= 0.90 and hi <= 1.10:
        return "no material effect"
    return "inconclusive"


def load(path):
    rows = [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]
    return rows


def by_arm(scored):
    d = defaultdict(list)
    for s in scored:
        d[s["arm"]].append(s)
    return d


def main():
    s2_scored = load(HERE / "full_s2_scored.jsonl")
    s1_scored = load(HERE / "scored.jsonl")
    S2, S1 = by_arm(s2_scored), by_arm(s1_scored)
    pairs2, pairs1 = s2.pair_units(s2_scored), s2.pair_units(s1_scored)

    print("## Per-arm means and totals (Stage 2, Haiku 5.5)\n")
    print("| arm | runs | input tokens (uncached) | cache write | cache read | output | total | mean $/run | total $ |")
    print("|---|---|---|---|---|---|---|---|---|")
    for a in ARMS:
        g = S2[a]
        tot = lambda k: sum(x[k] for x in g)
        uncached = sum(x["prompt_tokens"] - x["cache_creation_tokens"] - x["cache_read_tokens"] for x in g)
        print(f"| {a} | {len(g)} | {uncached:,} | {tot('cache_creation_tokens'):,} | {tot('cache_read_tokens'):,} | {tot('output_tokens'):,} | {tot('total_tokens'):,} | {tot('dollars') / len(g):.5f} | {tot('dollars'):.6f} |")
    print("\nAll-arm totals: input %s, output %s, dollars %.6f" % (
        f"{sum(x['prompt_tokens'] for x in s2_scored):,}", f"{sum(x['output_tokens'] for x in s2_scored):,}", sum(x["dollars"] for x in s2_scored)))

    print("\n## Ratio arm / control, ticket-cluster bootstrap (10,000 resamples, seed 20261015)\n")
    print("| arm | endpoint | Stage 2 ratio [95% CI] | Stage 2 reading | Stage 1 ratio [95% CI] | Stage 1 reading |")
    print("|---|---|---|---|---|---|")
    ratios2 = {}
    for arm in ARMS[1:]:
        for name, key in ENDPOINTS + SENS:
            r2, lo2, hi2 = s2.cluster_ratio_ci(pairs2[arm], key)
            ratios2[(arm, key)] = (r2, lo2, hi2)
            if key in ("W_out1", "W_out8"):
                print(f"| {arm} | {name} | {r2:.2f} [{lo2:.2f}, {hi2:.2f}] | sensitivity | | |")
                continue
            if key == "dollars":
                s1cell, s1read = "n/a (no dollars in Stage 1)", "n/a"
            else:
                r1, lo1, hi1 = s2.cluster_ratio_ci(pairs1[arm], key)
                s1cell, s1read = f"{r1:.2f} [{lo1:.2f}, {hi1:.2f}]", label(lo1, hi1)
            print(f"| {arm} | {name} | {r2:.2f} [{lo2:.2f}, {hi2:.2f}] | {label(lo2, hi2)} | {s1cell} | {s1read} |")

    print("\n## Quality gate (pre-registered, section 10; score.py rule)\n")
    print("| arm | format rate (all 5 stages ok) | defect-hit | format gate | defect-hit gate | composite pass (Wilson 95%) | composite, repaired-brace |")
    print("|---|---|---|---|---|---|---|")
    fmt = lambda x: all(x["stages_ok"].values())
    gates2 = {}
    for arm in ARMS:
        g = S2[arm]; n = len(g)
        f = sum(fmt(x) for x in g); h = sum(x["defect_hit"] for x in g)
        qp = sum(x["quality_pass"] for x in g); qr = sum(x["quality_pass_repaired"] for x in g)
        cf = sum(fmt(x) for x in S2["control"]) / len(S2["control"]); ch = sum(x["defect_hit"] for x in S2["control"]) / len(S2["control"])
        af, ah = f / n, h / n
        if arm == "control":
            fg, hg = "reference", "reference"
        else:
            fg = "n/a (control format < 0.5)" if cf < 0.5 else ("PASS" if af >= 0.95 * cf else "FAIL")
            hg = "PASS" if ah >= 0.95 * ch else "FAIL"
        gates2[arm] = (fg, hg)
        lo, hi = s1.wilson(qp, n)
        print(f"| {arm} | {f}/{n} ({af:.2f}) | {h}/{n} ({ah:.2f}) | {fg} | {hg} | {qp}/{n} ({lo:.2f}-{hi:.2f}) | {qr}/{n} |")

    print("\n## Stage 1 vs Stage 2 quality gate (same rule, side by side)\n")
    print("| arm | Stage 1 format | Stage 1 defect-hit | Stage 1 gate | Stage 2 format | Stage 2 defect-hit | Stage 2 gate |")
    print("|---|---|---|---|---|---|---|")
    for arm in ARMS:
        n1, n2 = len(S1[arm]), len(S2[arm])
        f1 = sum(fmt(x) for x in S1[arm]) / n1; h1 = sum(x["defect_hit"] for x in S1[arm]) / n1
        f2 = sum(fmt(x) for x in S2[arm]) / n2; h2 = sum(x["defect_hit"] for x in S2[arm]) / n2
        g1 = gate_text(S1, arm, fmt)
        g2 = gates2[arm]
        print(f"| {arm} | {f1:.2f} | {h1:.2f} | {g1} | {f2:.2f} | {h2:.2f} | {g2[0]} / {g2[1]} |")

    print("\n## Transfer rule (section 10): Stage 1 direction on W with CI excluding 1, same in Stage 2 with gate pass\n")
    for arm in ARMS[1:]:
        r1, lo1, hi1 = s2.cluster_ratio_ci(pairs1[arm], "W")
        r2, lo2, hi2 = ratios2[(arm, "W")]
        d1 = label(lo1, hi1); d2 = label(lo2, hi2)
        gate_ok = gates2[arm][1] == "PASS" and gates2[arm][0] in ("PASS", "n/a (control format < 0.5)")
        transferred = d1 == d2 and d2 in ("reduction", "increase") and gate_ok
        print(f"- {arm}: Stage 1 W {d1}; Stage 2 W {d2}; Stage 2 defect-hit gate {gates2[arm][1]} -> {'transferred' if transferred else 'not transferred'}")

    print("\n## Mean prompt / output tokens per stage per run, Stage 2\n")
    stages = s1.STAGES
    calls = [r for r in load(HERE / "full_s2_runs.jsonl") if r["kind"] == "call"]
    print("| arm | " + " | ".join(stages) + " |")
    print("|---|" + "---|" * len(stages))
    for arm in ARMS:
        cells = []
        for st in stages:
            cs = [c for c in calls if c["arm"] == arm and c["stage"] == st]
            p = sum(c["usage"]["input_tokens"] + c["usage"]["cache_creation_input_tokens"] + c["usage"]["cache_read_input_tokens"] for c in cs) / len(cs)
            o = sum(c["usage"]["output_tokens"] for c in cs) / len(cs)
            cells.append(f"{p:.0f} / {o:.0f}")
        print(f"| {arm} | " + " | ".join(cells) + " |")

    print("\n## Stop reasons and truncation (Stage 2)\n")
    print("stop_reason:", dict(Counter(c["stop_reason"] for c in calls)), "| max_tokens count:", sum(c["stop_reason"] == "max_tokens" for c in calls))


def gate_text(S, arm, fmt):
    if arm == "control":
        return "reference"
    cf = sum(fmt(x) for x in S["control"]) / len(S["control"])
    ch = sum(x["defect_hit"] for x in S["control"]) / len(S["control"])
    af = sum(fmt(x) for x in S[arm]) / len(S[arm]); ah = sum(x["defect_hit"] for x in S[arm]) / len(S[arm])
    fg = "n/a" if cf < 0.5 else ("PASS" if af >= 0.95 * cf else "FAIL")
    hg = "PASS" if ah >= 0.95 * ch else "FAIL"
    return f"{fg} / {hg}"


if __name__ == "__main__":
    main()
