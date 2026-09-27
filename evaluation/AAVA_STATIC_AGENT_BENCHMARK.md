# AAVA Static Agent-Definition Benchmark — Evidence Report

> **Type:** evidence checkpoint (measurement documentation), not implementation.
> **Scope:** static agent *definitions* only — **not** full runtime LLM context.
> **Data hygiene:** this report contains **aggregate statistics only**. No raw
> AAVA agent text, goal strings, workflow names, or tool names are reproduced
> here, because the source workbook is proprietary. The raw dataset and the
> per-agent outputs are **not** committed to this repository.
> **Classifications:** VERIFIED (reproduced here) · OBSERVED (recorded in an
> artifact) · INFERRED (reasoned, not directly measured) · UNKNOWN.

---

## 1. Executive finding

On **4,343 real AAVA agent definitions** (~7.69M input tokens), the current
deterministic optimization saves **0.93% of input tokens on `main` and 0.74%
on the PR branch**, with a **median per-agent saving of 0.0%** — 57–60% of
agents are optimized by essentially nothing. **VERIFIED.**

The previously reported ~24% came from a small set of synthetic prompts the
author constructed; it is **not representative** of this real corpus and must
not be used as evidence of production savings. The PR branch is **worse than
`main`** on this corpus (net +13,944 tokens across the corpus; 650 agents get
larger). This benchmark measures **static agent definitions only** and does
**not** establish any runtime (per-execution) savings, positive or negative.

---

## 2. Dataset

| Item | Value | Class |
|---|---|---|
| Source | `workflow_agent_tool_analytics Copy.xlsx`, sheet `Sheet2` | OBSERVED |
| Raw rows | 111,291 | VERIFIED |
| Rows with a usable definition (≥40 chars) | 5,374 | VERIFIED |
| **Unique agent definitions (dedup by exact text)** | **4,343** | VERIFIED |
| Definition assembled from columns | `role`, `goal`, `backstory`, `description`, `expected_output` (joined with newlines) | VERIFIED |
| Total input tokens (o200k) | 7,693,214 | VERIFIED |
| Per-agent size | median ≈ 847 tok, mean ≈ 1,771, p90 ≈ 4,430, max ≈ 22,397 | OBSERVED |
| `prompt` column populated | 18 / 111,291 (median 1 token) — effectively empty | VERIFIED |
| `executions` column (Sheet2) | near-empty (sum ≈ 82); real usage lives in other sheets, not joined | OBSERVED |

**Static vs runtime:** These are **agent definitions** (the persistent
system-prompt material CrewAI-style agents carry), **not** captured runtime
prompts. VERIFIED — the fields are configuration columns; no tool call/results,
conversation turns, or retrieved context are present.

**Execution-weighted analysis:** **not performed.** The `executions` figures
in `Sheet2` are absent, so savings cannot be weighted by real call volume from
this table alone. Reported numbers are **unweighted** across unique agents.
OBSERVED.

---

## 3. Methodology

| Item | Value | Class |
|---|---|---|
| Tokenizer | `tiktoken` `o200k_base` (tiktoken 0.13.0, Python 3.12.10) | VERIFIED |
| Optimization config | `get_prototype_config()` → pipeline Analyzer → Transformer → Validator (Router/Cache/Summarizer/RAG/FewShot disabled) | VERIFIED |
| Entry point | `CanonicalOptimizer.optimize(messages, model="gpt-4o")` | VERIFIED |
| Input shape | one message per agent: `[{"role":"user","content":<definition>}]` | VERIFIED |
| Savings metric | `(orig_tokens − optimized_tokens) / orig_tokens`, both counted with o200k on message content | VERIFIED |
| Provider / runtime involved? | **No.** Pure in-process transform + local token count; no LLM call, no provider usage | VERIFIED |
| `main` version | `origin/main` @ `22ff302` | VERIFIED |
| `PR` version | `origin/fix/transformer-dedup-order` @ `3272709` (dedup-order fix + verbose-reduction) | VERIFIED |

Rollback behavior: when the Validator returns a non-accept decision the
optimizer restores the original messages (0% saving for that agent). VERIFIED
(738 non-accept = 738 rollback, both versions).

---

## 4. Main vs PR results — VERIFIED

| Version | Input tok | Optimized tok | Savings | Median/agent | Rollbacks (non-accept) |
|---|---:|---:|---:|---:|---:|
| `main` (22ff302) | 7,693,214 | 7,621,979 | **0.93%** | 0.0% | 738 |
| `PR` (3272709) | 7,693,214 | 7,635,923 | **0.74%** | 0.0% | 738 |

Reproduced this session from the raw workbook via `verify_aava.py` (see §14).

---

## 5. Savings distribution — VERIFIED

Per-agent saving buckets (share of 4,343 agents):

| Bucket | `main` | `PR` |
|---|---:|---:|
| 0% | 2,481 (57%) | 2,594 (60%) |
| >0–0.5% | 345 (8%) | 397 (9%) |
| >0.5–1% | 305 (7%) | 308 (7%) |
| >1–5% | 982 (23%) | 861 (20%) |
| >5% | 230 (5%) | 183 (4%) |

The majority of agents fall in the 0% bucket (rolled back or nothing to
remove). Only ~5% of agents exceed 5% savings, and the PR shifts agents
*toward* the low buckets relative to `main`.

---

## 6. Transformation-level analysis — VERIFIED (from optimizer metrics) / INFERRED (attribution)

Captured from the optimizer's own `transformer_metrics` across the corpus (`main`):

| Signal | Value | Class |
|---|---:|---|
| Agents with any saving | 1,862 / 4,343 | VERIFIED |
| Agents where P2 prose was transformed | 1,960 | VERIFIED |
| Total sentences pruned (duplicate/certified-redundant) | 7,680 | VERIFIED |
| Messages removed (P3 removal) | 0 | VERIFIED |
| Local-preflight fallbacks | 26 | VERIFIED |
| Rolled-back agents (kept original) | 738 | VERIFIED |

**Mechanism (traced from `tokenopt/pipeline/transformer.py`, not inferred from
metric names):** the only lossy operations available are (a) whitespace
normalization, (b) certified inline filler removal, (c) sentence pruning of
exact duplicates and certified-redundant/pleasantry sentences. **No message
removal occurs** (single-message inputs; P3 removal count = 0). Therefore all
realized savings come from **filler + whitespace + intra-message sentence
pruning on P2 prose**. INFERRED (attribution): the small savings reflect that
dense agent-definition text contains little certified filler and few duplicate
sentences; most sentences are directive/technical and are preserved.

---

## 7. PR regression analysis — VERIFIED

| Measure | Value |
|---|---:|
| Agents where PR output is **larger** than main | 650 |
| Aggregate extra tokens on those agents | +15,786 |
| Agents where PR output is smaller than main | 62 |
| Aggregate tokens saved on those | −1,842 |
| **Net PR vs main** | **+13,944 tokens (PR worse)** |
| Largest single-agent regression | +504 tokens |

**Mechanism (VERIFIED by reproducing one agent):** the PR reorders the
transform — it splits and prunes sentences *before* stripping inline filler
(and strips filler per-sentence), whereas `main` strips filler globally first.
On dense text, some sentences that become identical only *after* `main`'s
global filler strip are then deduplicated by `main`; under the PR ordering they
are compared before filler removal, remain distinct, and are not deduplicated.
Net effect on this corpus: the PR prunes less. (Confirmed on a representative
agent: `main` optimized output 7,027 chars vs PR 8,437 chars, both `accept`,
no rollback.)

Note: the PR's reordering is a legitimate *correctness* fix for a different
case (duplicates hidden behind a *leading* filler word) and is covered by new
unit tests. Its regression here is on the aggregate token metric for this
specific corpus, not a test failure.

---

## 8. Synthetic-vs-real comparison

| Corpus | Savings | Class |
|---|---:|---|
| Synthetic (8 author-written enterprise prompts) | ~16–24% | OBSERVED (prior session) |
| **Real AAVA static agent definitions (4,343)** | **~0.7–0.9%** | VERIFIED |

The synthetic result is not usable as production evidence because the synthetic
prompts were **authored to contain exactly what the transformer removes** —
conversational filler ("please/kindly/basically"), greetings/thanks, and
repeated boilerplate paragraphs. Real agent definitions are dense directive
specifications with little of that redundancy. The gap is a corpus-construction
artifact, not a model or tokenizer difference. INFERRED (strong).

---

## 9. Benchmark limitations

- **Static definitions only** — not runtime prompts. VERIFIED.
- **Unweighted** — not weighted by real execution volume (data unavailable in the joined table). OBSERVED.
- **Token-only** — measures input-token reduction of the definition text; no answer-quality or task-fidelity evaluation is included in this run. VERIFIED.
- **No provider involvement** — local tokenizer estimate; not provider-reported usage or billing. VERIFIED.
- Raw dataset and per-agent outputs are session-local (scratchpad), not committed; exact reproduction requires re-supplying the workbook. OBSERVED.

---

## 10. What this proves — VERIFIED

- On the static agent-definition corpus, current optimization yields **~0.9% input-token reduction, median 0%**.
- The strategy's realized savings come only from filler/whitespace/duplicate-sentence pruning of prose; there is little such redundancy in this corpus.
- The PR branch **regresses** this corpus versus `main` (net +13,944 tokens).
- The ~24% synthetic figure is **not representative** of this workload.

## 11. What this does NOT prove

- It does **not** establish runtime (per-execution) savings — positive or negative — for real AAVA workloads. VERIFIED (out of scope of the data).
- It does **not** measure answer quality or task fidelity on this corpus.
- It does **not** measure cost/billing impact.

## 12. What is UNKNOWN (evidence genuinely absent)

- Runtime tool schemas injected into prompts. UNKNOWN.
- Tool outputs returned mid-execution. UNKNOWN.
- Conversation/turn history in multi-step runs. UNKNOWN.
- Retrieved (RAG) context. UNKNOWN.
- The actual assembled per-execution prompt. UNKNOWN.
- Output-token impact. UNKNOWN.
- Provider billing impact and whether prompt caching is enabled. UNKNOWN.

## 13. Required next evidence

To evaluate the optimization strategy against real AAVA cost, capture **real
runtime execution traces**: the full message list sent to the model (system +
injected tool schemas + tool call/results + history) and the response, for a
few high-volume workflows. Without traces, any runtime savings figure would be
modeled, not measured.

---

## Critical product question

> Does this benchmark provide evidence that the current optimization strategy
> has meaningful value on real AAVA workloads?

**No — not on the evidence available.** On real static agent definitions the
strategy delivers ~0.9% (median 0%), which is not meaningful, and this
benchmark does not cover the runtime context where the cost actually
concentrates. It provides **no** evidence of meaningful value on real AAVA
workloads, and it should not be read as evidence of *absence* of value at
runtime either — runtime is simply unmeasured here. **Evidence-based, not a
sales claim.**

---

## Recommendation regarding the PR

**Do not merge the PR on the basis of the synthetic benchmark.** On the real
static corpus the PR is a net regression versus `main` (+13,944 tokens; 650
agents larger). The PR's dedup-order change is a valid correctness fix with
tests, but its aggregate token effect on real dense text is negative. Hold the
PR unmerged pending (a) runtime-trace evidence and (b) a decision on the
transform ordering that does not regress dense corpora. VERIFIED basis.

---

## 14. Reproduction — files, commands, verification

**Scripts / data (session-local scratchpad; not committed):**
- `aava_agents.json` — 4,343 unique agent definitions extracted from `Sheet2`.
- `verify_aava.py` — runs each definition through `CanonicalOptimizer(get_prototype_config())`, records o200k tokens + `transformer_metrics`.
- `aava_full_main.json`, `aava_full_pr.json` — per-agent outputs.

**Commands:**
```
# main @ 22ff302, PR @ 3272709 checked out as detached worktrees
PYTHONPATH=<v_main> python verify_aava.py main
PYTHONPATH=<v_pr>   python verify_aava.py pr
```

**Verification results (this run):**
- `main: 4343 agents  7,693,214 -> 7,621,979  saved 0.93%  non-accept=738  rollback=738`
- `pr:   4343 agents  7,693,214 -> 7,635,923  saved 0.74%  non-accept=738  rollback=738`
- tokenizer: tiktoken 0.13.0 `o200k_base`; Python 3.12.10.

**Integrity confirmation:**
- No application code changed (`tokenopt/**`). VERIFIED.
- No tests changed (`tests/**`). VERIFIED.
- The PR branch commits are untouched; nothing committed or pushed for this task. VERIFIED.
- Measurements were produced from read-only detached worktrees of `origin/main` and `origin/fix/transformer-dedup-order`.
