# Phase 1b census report (no model calls)
Source: `census.py` -> `results/census.json`; test `test_census.py` (3 pass). Prices ASSUMED: uncached 1, cached 0.1, output 4 (sensitivity grid in the json). Provider usage is truth; o200k only apportions. Numbers below are token share / weighted-cost share. Pooled by trace set; regimes are not mixed.

## Data
| set | sessions | turns | content | note |
|---|---|---|---|---|
| opencode (read-only analysis) | 2 | 15 | full messages | 1 of 2 has the cache anomaly |
| Aegis T1 bug-fix controls (baseline_variance, t1a, t1b) | 30 (+20 treatment) | 446 total | via raw/stream.jsonl | one task only; t1a r20 excluded (misaligned) |
| Multi-agent / nested | 0 real | n/a | n/a | only a reconstructed 3-agent AAVA workflow, no per-turn usage |

## Shares
| | Aegis controls (n=10 per set) | opencode (n=2) |
|---|---|---|
| Static prefix (system+tools+task) | 55-67% / 30-36% | 34% / 23% |
| Output | 3.8-4.7% / 44-45% (about half is tool-call args = the work product) | 0.7% / 7.9% |
| Test/CI/build output | 5.5-7.7% / 5.0-5.8% | 0 |
| File reads | 4.5-6.8% / 2.6-4.0% | 64% / 68% (42% at first entry, 26% re-billed) |
| JSON/logs, diffs | 0 (none in data) | 0 |
| Cache-prefix breaks | 1 small in 49 sessions (0.4% of one set) | 2 breaks, 36.3% of trace 1, 22.2% pooled |
| One average turn | 12-15% of session cost (turns range 5-28 on the same task) | 15% |

Re-billing: a tool result costs 3-5x its first-entry tokens over later turns, about 40-60% of its weighted cost. Classifier: tool-name and content classifiers disagree 0 times; no human labels.

## Ranked levers (upper bound = share at 100% removal; no compression rate assumed)
| rank | lever | type | Aegis (weighted) | opencode (weighted) | evidence |
|---|---|---|---|---|---|
| 1 | Output reduction | turn reduction / other | 44-45% | 7.9% | measured; half is work product |
| 2 | One fewer turn | turn reduction | 12-15% | ~15% | measured; success impact unknown |
| 3 | File-read handler (outline) | handler | 2.6-4.0% | 68% | opencode n=2, body-needed risk |
| 4 | Test/CI handler | handler | 5.0-5.8% | 0 | measured on one task |
| 5 | Cache-break avoidance | cache discipline | 0-0.4% | 22% | cause undiagnosed |
| 6 | Handoff contract | handoff contract | UNKNOWN | UNKNOWN | no real nested trace |
| 7 | JSON/log, diff handlers | handler | 0 | 0 | no such content in data |

## Decision rule
- Aegis bug-fix regime: all context levers combined at 100% removal = 7.6-9.8% weighted (10-15% of tokens). Below 25% even at perfect removal; prior measured compression on coding tool results is about 0-1%. Reaching 25% would need about 46% of output cost removed, which changes what the agent writes.
- opencode read-heavy regime: ceiling 68% (file reads) + 22% (breaks), but n=2, no outcome label, and lossy outlines changed decisions in prior tests.
- Multi-agent: UNKNOWN. Reconstructed workflow: agent 3's prompt is about 20% verbatim overlap with agent 2's output; about 33% of estimated tokens sit on lines never echoed in an agent's output, mostly necessary instructions (n=1, no cost).

## Summary
1. On bug-fix work, tool results are about 10% of weighted cost; output is 44-45%.
2. Structured handler targets (test/CI) cap at 5-6%; JSON/log and diff are absent from our data.
3. Read-heavy work is the only regime with a large addressable share (file reads 68%), and it is two sessions.
4. Cache breaks are rare except one session (36.3%), cause unknown.
5. Handoff bloat and nested workflows are unmeasured; no real trace exists.
