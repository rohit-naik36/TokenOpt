"""Stage 1 analysis for otl-001. Usage: analyze.py RUNS_DIR SCORES_CSV ID_TO_ARM_JSON TOKENOPT_DIR OUT_PREFIX
Joins judge scores to arms only here, after scores were written."""
import csv, json, math, random, sys
from pathlib import Path

runs, scores, mapping, tokenopt, out = map(Path, sys.argv[1:6])
sys.path.insert(0, str(tokenopt))
from tokenopt import census  # noqa: E402

SEED, B, ARMS = 20261014, 10_000, ["control", "A", "B", "C"]
sc = {r["id"]: r for r in csv.DictReader(open(scores))}
rows = []
for i, m in json.load(open(mapping)).items():
    d = runs / m["run_id"]
    res = json.load(open(d / "result.json")); ev = json.load(open(d / "evaluator.json"))
    a = census.account(census.aegis_session(d))
    P, C, O, T = a["P"], a["C"], a["O"], a["turns"]
    assert abs(sum(a["turn_w"]) - ((P - C) + 0.1 * C + 4 * O)) < 1e-6
    rows.append(dict(arm=m["arm"], rep=m["rep"], ok=bool(res["metrics"]["success"]), hidden=bool(ev["hidden_pass"]),
                     judge=sum(int(sc[i][k]) for k in ("correctness", "tests", "minimality", "hygiene")),
                     out=O, turns=T, tpt=(P + O) / T, P=P, C=C,
                     W=(P - C) + 0.1 * C + 4 * O, W1=(P - C) + 0.1 * C + O, W8=(P - C) + 0.1 * C + 8 * O))
assert len(rows) == 80

def col(arm, k): return [r[k] for r in rows if r["arm"] == arm]
def mean(x): return sum(x) / len(x)
def gmean(x): return math.exp(mean([math.log(v) for v in x]))
def pct(x, q): x = sorted(x); return x[min(len(x) - 1, int(q * len(x)))]
def boot(f, *groups):
    rng = random.Random(SEED); v = []
    for _ in range(B): v.append(f(*[[rng.choice(g) for _ in g] for g in groups]))
    return pct(v, .025), pct(v, .975)
def perm_p(x, y):
    rng = random.Random(SEED); obs = abs(mean(x) - mean(y)); z = x + y; n = len(x); c = 0
    for _ in range(B):
        rng.shuffle(z); c += abs(mean(z[:n]) - mean(z[n:])) >= obs
    return (c + 1) / (B + 1)
def wilson(k, n, z=1.96):
    p = k / n; d = 1 + z * z / n; c = p + z * z / (2 * n); h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (c - h) / d, (c + h) / d

res = {}
for arm in ARMS:
    res[arm] = {"n": len(col(arm, "ok")), "pass": sum(col(arm, "ok")), "hidden_pass": sum(col(arm, "hidden")),
                "wilson": wilson(sum(col(arm, "ok")), len(col(arm, "ok")))}
    for k in ("judge", "out", "turns", "tpt", "W", "W1", "W8"):
        x = col(arm, k); res[arm][k] = {"mean": mean(x), "ci": boot(mean, x)}
    res[arm]["W_gmean"] = gmean(col(arm, "W"))
ctl = col("control", "ok")
lines = ["| arm | n | pass (Wilson 95%) | hidden pass | judge /10 [95% CI] | output tokens | turns | tokens/turn | weighted cost W |", "|---|---|---|---|---|---|---|---|---|"]
f = lambda d, p=0: f"{d['mean']:.{p}f} [{d['ci'][0]:.{p}f}, {d['ci'][1]:.{p}f}]"
for arm in ARMS:
    r = res[arm]
    lines.append(f"| {arm} | {r['n']} | {r['pass']}/{r['n']} ({r['wilson'][0]:.2f}-{r['wilson'][1]:.2f}) | {r['hidden_pass']}/{r['n']} | {f(r['judge'],2)} | {f(r['out'])} | {f(r['turns'],2)} | {f(r['tpt'])} | {f(r['W'])} |")
lines += ["", f"Ratio arm/control (mean ratio, percentile bootstrap 95% CI, 10,000 resamples, seed {SEED}); p = permutation test on mean difference, Holm-adjusted over the 3 primaries within arm", "",
          "| arm | output tokens | turns | tokens/turn | W (mean ratio) | W (geo-mean ratio) | W, output weight 1 | W, output weight 8 | Holm p (out, turns, tpt) |", "|---|---|---|---|---|---|---|---|---|"]
ratios = {}
for arm in ARMS[1:]:
    cells = []; ps = []
    for k in ("out", "turns", "tpt", "W"):
        x, y = col(arm, k), col("control", k); rr = mean(x) / mean(y)
        lo, hi = boot(lambda a, b: mean(a) / mean(b), x, y); cells.append((rr, lo, hi)); ratios[(arm, k)] = (rr, lo, hi)
        if k != "W": ps.append(perm_p(x, y))
    x, y = col(arm, "W"), col("control", "W"); g = gmean(x) / gmean(y); glo, ghi = boot(lambda a, b: gmean(a) / gmean(b), x, y)
    sens = [(mean(col(arm, k)) / mean(col("control", k)), *boot(lambda a, b: mean(a) / mean(b), col(arm, k), col("control", k))) for k in ("W1", "W8")]
    order = sorted(range(3), key=lambda i: ps[i]); adj = [0] * 3; run = 0
    for rank, i in enumerate(order): run = max(run, min(1, ps[i] * (3 - rank))); adj[i] = run
    t = lambda c: f"{c[0]:.2f} [{c[1]:.2f}, {c[2]:.2f}]"
    lines.append(f"| {arm} | {t(cells[0])} | {t(cells[1])} | {t(cells[2])} | {t(cells[3])} | {g:.2f} [{glo:.2f}, {ghi:.2f}] | {t(sens[0])} | {t(sens[1])} | {adj[0]:.3f}, {adj[1]:.3f}, {adj[2]:.3f} |")
lines += ["", "Quality gate (arm >= 95% of control on each; pass rate is the primary signal, judge secondary; n=20 so a pass means 'not distinguishable', not 'equivalent')", "",
          "| arm | pass rate vs control | pass-rate gate | judge mean vs control | judge gate |", "|---|---|---|---|---|"]
for arm in ARMS[1:]:
    pr = res[arm]["pass"] / res[arm]["n"]; cp = res["control"]["pass"] / res["control"]["n"]; jr = res[arm]["judge"]["mean"] / res["control"]["judge"]["mean"]
    lines.append(f"| {arm} | {pr / cp:.3f} | {'PASS' if pr >= .95 * cp else 'FAIL'} | {jr:.3f} | {'PASS' if jr >= .95 else 'FAIL'} |")
Path(str(out) + ".md").write_text("\n".join(lines) + "\n", encoding="utf-8")
json.dump({"seed": SEED, "bootstrap": B, "per_arm": res, "rows": rows}, open(str(out) + ".json", "w"), indent=1)
print("\n".join(lines))
