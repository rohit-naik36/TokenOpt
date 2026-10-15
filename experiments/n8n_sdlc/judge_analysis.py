"""Join judge_scores.jsonl to arms via blind_map.json; per-arm mean judge score and ratio vs control.

    python judge_analysis.py

Same pairing and bootstrap as score.py: paired (ticket, rep) units, ticket-clustered percentile
bootstrap, 10000 resamples, seed 20261015, ratio = sum(arm) / sum(control) over resampled units.
Run only after judge_scores.jsonl is final (it was written before blind_map.json was opened).
"""
import json
import random
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).parent
ARMS = ["control", "A", "H", "AH"]
CRIT = ["requirements", "plan", "review", "release_note", "total"]
SEED, B = 20261015, 10_000


def pct(v, q):
    v = sorted(v)
    return v[min(len(v) - 1, int(q * len(v)))]


def main():
    bmap = json.loads((HERE / "blind_map.json").read_text(encoding="utf-8"))
    scored = {r["run_id"]: r for r in map(json.loads, (HERE / "scored.jsonl").read_text(encoding="utf-8").splitlines())}
    rows = []
    for l in (HERE / "judge_scores.jsonl").read_text(encoding="utf-8").splitlines():
        j = json.loads(l)
        assert j["total"] == sum(j[c] for c in CRIT[:4]), j["id"]
        s = scored[bmap[j["id"]]]
        rows.append(dict(j, arm=s["arm"], ticket=s["ticket_id"], rep=s["rep"], defect_hit=s["defect_hit"]))
    assert len(rows) == 160 and len({(r["arm"], r["ticket"], r["rep"]) for r in rows}) == 160
    by = defaultdict(list)
    for r in rows:
        by[r["arm"]].append(r)
    print("Blind judge (secondary), n=40 per arm, scores 0-10 (requirements 0-3, plan 0-2, review 0-3, release_note 0-2)")
    print("arm       " + "".join(f"{c:>14}" for c in CRIT))
    for a in ARMS:
        print(f"{a:<10}" + "".join(f"{sum(r[c] for r in by[a]) / len(by[a]):>14.2f}" for c in CRIT))
    ctl = {(r["ticket"], r["rep"]): r for r in by["control"]}
    print(f"\nRatio arm/control of mean judge score, paired CLUSTER percentile bootstrap, {B} resamples, seed {SEED}")
    for a in ARMS[1:]:
        pairs = [(ctl[(r["ticket"], r["rep"])], r) for r in by[a]]
        tix = defaultdict(list)
        for p in pairs:
            tix[p[0]["ticket"]].append(p)
        keys = sorted(tix)
        line = f"{a:<5}n={len(pairs)}"
        for k in ("total", "review"):
            rng = random.Random(SEED)
            v = []
            for _ in range(B):
                smp = [p for t in (keys[rng.randrange(len(keys))] for _ in keys) for p in tix[t]]
                v.append(sum(p[1][k] for p in smp) / sum(p[0][k] for p in smp))
            r = sum(p[1][k] for p in pairs) / sum(p[0][k] for p in pairs)
            line += f"  {k} {r:.2f} [{pct(v, .025):.2f}, {pct(v, .975):.2f}]"
        print(line + f"  -> secondary gate (mean >= 95% of control): {'PASS' if sum(p[1]['total'] for p in pairs) >= 0.95 * sum(p[0]['total'] for p in pairs) else 'FAIL'}")
    print("\nSanity: mean judge review score by deterministic defect_hit (all arms)")
    for h in (True, False):
        g = [r["review"] for r in rows if r["defect_hit"] == h]
        print(f"  defect_hit={h}: n={len(g)} mean review {sum(g) / len(g):.2f}")
    print("\nMean judge total by ticket (all arms)")
    for t in sorted({r["ticket"] for r in rows}):
        g = [r["total"] for r in rows if r["ticket"] == t]
        print(f"  {t}: {sum(g) / len(g):.2f}")


if __name__ == "__main__":
    main()
