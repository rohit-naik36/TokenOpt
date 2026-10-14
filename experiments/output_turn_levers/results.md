| arm | n | pass (Wilson 95%) | hidden pass | judge /10 [95% CI] | output tokens | turns | tokens/turn | weighted cost W |
|---|---|---|---|---|---|---|---|---|
| control | 20 | 20/20 (0.84-1.00) | 20/20 | 9.95 [9.85, 10.00] | 2284 [2021, 2530] | 7.70 [6.90, 8.50] | 5748 [5535, 5963] | 19348 [17456, 21210] |
| A | 20 | 20/20 (0.84-1.00) | 20/20 | 9.90 [9.75, 10.00] | 1410 [1162, 1684] | 7.35 [6.30, 8.50] | 5314 [5098, 5550] | 14966 [12973, 17159] |
| B | 20 | 20/20 (0.84-1.00) | 20/20 | 9.80 [9.60, 9.95] | 2064 [1800, 2368] | 8.55 [7.60, 9.55] | 5751 [5543, 5969] | 19075 [17065, 21298] |
| C | 20 | 19/20 (0.76-0.99) | 19/20 | 9.35 [8.90, 9.70] | 1135 [1008, 1266] | 6.60 [5.70, 7.50] | 5175 [5054, 5297] | 13013 [11783, 14278] |

Ratio arm/control (mean ratio, percentile bootstrap 95% CI, 10,000 resamples, seed 20261014); p = permutation test on mean difference, Holm-adjusted over the 3 primaries within arm

| arm | output tokens | turns | tokens/turn | W (mean ratio) | W (geo-mean ratio) | W, output weight 1 | W, output weight 8 | Holm p (out, turns, tpt) |
|---|---|---|---|---|---|---|---|---|
| A | 0.62 [0.49, 0.77] | 0.95 [0.79, 1.14] | 0.92 [0.87, 0.98] | 0.77 [0.65, 0.92] | 0.76 [0.64, 0.90] | 0.86 [0.73, 1.00] | 0.72 [0.60, 0.87] | 0.000, 0.671, 0.020 |
| B | 0.90 [0.76, 1.08] | 1.11 [0.95, 1.29] | 1.00 [0.95, 1.05] | 0.99 [0.85, 1.14] | 0.98 [0.85, 1.14] | 1.03 [0.90, 1.18] | 0.96 [0.82, 1.12] | 0.690, 0.690, 0.989 |
| C | 0.50 [0.42, 0.58] | 0.86 [0.72, 1.01] | 0.90 [0.86, 0.94] | 0.67 [0.59, 0.77] | 0.67 [0.59, 0.78] | 0.77 [0.68, 0.88] | 0.62 [0.54, 0.71] | 0.000, 0.103, 0.000 |

Quality gate (arm >= 95% of control on each; pass rate is the primary signal, judge secondary; n=20 so a pass means 'not distinguishable', not 'equivalent')

| arm | pass rate vs control | pass-rate gate | judge mean vs control | judge gate |
|---|---|---|---|---|
| A | 1.000 | PASS | 0.995 | PASS |
| B | 1.000 | PASS | 0.985 | PASS |
| C | 0.950 | PASS | 0.940 | FAIL |
