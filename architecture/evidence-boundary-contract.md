# Evidence Boundary & Claim Integrity Contract (CP8)

**Status**: Normative — changes require architecture decision and approval gate.

---

## Purpose

This contract establishes a strict **evidence boundary** between what TokenOpt *estimates locally* and what the *provider actually observes*. It forbids silent substitution, conflation, or mislabeling of these fundamentally different measurement classes.

---

## Evidence and Claim Classification

Every reported evidence item or claim in TokenOpt evidence carries an explicit **classification** describing its evidentiary status or intended role. These classifications are not five equivalent types of measurement; they describe the nature of the evidence supporting a claim.

| Classification | Definition | Examples |
|----------------|------------|----------|
| **OBSERVED** | Directly measured from an external/provider observation or execution result. Immutable fact. | `provider_input_tokens`, `provider_output_tokens`, `provider_total_tokens` (when explicitly supplied by provider), `total_latency_ms`, `validation_decision`, `rollback_applied` |
| **VERIFIED** | Established by a deterministic validation or test. | `invariants_checked`, `invariants_passed`, `invariants_failed`, `task_fidelity.baseline_passed`, `task_fidelity.tokenopt_passed` |
| **DIAGNOSTIC** | Informational evidence that does not establish correctness or provider-observed behavior. Computed for insight only; never gates pass/fail or claim validity. | `semantic_diagnostics.similarity_score`, `estimated_original_tokens`, `estimated_optimized_tokens`, `estimated_tokens_saved`, `pipeline_latency_ms`, `model_latency_ms` |
| **TARGET** | Desired future performance/behavior; not an observed measurement. A configured goal or threshold. | `compression_ratio`, `cache_similarity_threshold`, `summarization_threshold` |
| **NOT_PROVABLE** | A claim for which the current evidence is insufficient to establish the claim. Cannot be established with current instrumentation; explicitly acknowledged as unknown. | Provider token counts when provider returns `None`, true semantic equivalence, actual provider cost without usage data |

---

## The Evidence Boundary: LOCAL_ESTIMATE vs PROVIDER_OBSERVATION

### LOCAL_ESTIMATE (DIAGNOSTIC)

Computed entirely by TokenOpt using local tokenizers (`tiktoken`) on message structures **before** and **after** pipeline transformation.

| Field | Source | Classification |
|-------|--------|----------------|
| `estimated_original_tokens` | `count_message_tokens(original_messages, model)` at pipeline entry | **DIAGNOSTIC** |
| `estimated_optimized_tokens` | `count_message_tokens(optimized_messages, model)` at pipeline exit | **DIAGNOSTIC** |
| `estimated_tokens_saved` | `estimated_original_tokens - estimated_optimized_tokens` | **DIAGNOSTIC** |

**Properties:**
- Available for every request (never `None`)
- Uses TokenOpt's tokenizer, which may differ from provider's tokenizer
- Represents *attempted* optimization, not *delivered* optimization
- Must **never** be used to calculate cost, billing, or provider-side reduction

### PROVIDER_OBSERVATION (OBSERVED)

Returned by the provider API in the response usage object.

| Field | Source | Classification |
|-------|--------|----------------|
| `provider_input_tokens` | `response.usage.prompt_tokens` / `input_tokens` / `prompt_eval_count` | **OBSERVED** |
| `provider_output_tokens` | `response.usage.completion_tokens` / `output_tokens` / `eval_count` | **OBSERVED** |
| `provider_total_tokens` | `response.usage.total_tokens` / `total_eval_count` | **OBSERVED** |

**Provider-Total Distinction:**

- **PROVIDER-REPORTED TOTAL**: A total token value explicitly supplied by the provider (e.g., `response.usage.total_tokens`, `total_eval_count`). This is an OBSERVED measurement.

- **PROVIDER-DERIVED TOTAL**: A total calculated by TokenOpt exclusively from provider-reported components, i.e., `provider_input_tokens + provider_output_tokens`. This is **not** a provider-reported total unless the provider explicitly supplied that total field. A provider-derived total must NOT be described or labeled as a provider-reported total.

The `extract_provider_usage_safe` function returns `provider_total_tokens` as `None` when the provider does not explicitly supply a total field, rather than deriving it from components. This preserves the distinction at the evidence layer.

**Properties:**
- May be `None` if provider omits usage, returns malformed data, or returns `0` for non-empty input
- Represents what the provider *actually billed* (or would bill)
- **Only** basis for cost projection and provider-side reduction claims
- If `None`, the quantity is **NOT_PROVABLE** — no fallback to local estimates

---

## Explicit Prohibitions

1. **No Silent Substitution**: When `provider_input_tokens` is `None`, `estimated_original_tokens` must **not** be used in its place. The result is `NOT_PROVABLE`.

2. **No Conflated Labels**: Reports must distinguish:
   - "Estimated Tokens Saved" (LOCAL_ESTIMATE, DIAGNOSTIC)
   - "Provider-Reported Input Tokens Saved" (PROVIDER_OBSERVATION, OBSERVED)
   - "Provider-Reported Input Reduction %" (PROVIDER_OBSERVATION, OBSERVED)

3. **No Cross-Basis Arithmetic**: Never compute `baseline.provider_input_tokens - tokenopt.estimated_optimized_tokens`. Cross-basis deltas are meaningless.

4. **No Diagnostic-to-Claim Promotion**: `semantic_diagnostics.similarity_score`, `estimated_tokens_saved`, or any DIAGNOSTIC metric must never appear in a claim summary without explicit "DIAGNOSTIC" classification.

5. **No Pass/Fail from DIAGNOSTIC**: Validation decisions (`ACCEPT`/`REJECT`), rollback, and `ExecutionStatus` must depend only on OBSERVED and VERIFIED classes.

---

## Reporter Requirements

All evidence reporters (JSONL, CSV, Markdown) must:

1. **Column/Field Names**: Use unambiguous prefixes:
   - `estimated_*` for LOCAL_ESTIMATE
   - `provider_*` for PROVIDER_OBSERVATION
   - `diagnostic_*` for other DIAGNOSTIC
   - `verified_*` for VERIFIED
   - `target_*` for TARGET

2. **Missing Provider Data**: Render as `N/A` or `null` — never as `0` or a local estimate.

3. **Aggregation Gates**: Aggregated totals (sums, averages) over PROVIDER_OBSERVATION fields must only include records where **all** contributing records have non-`None` values. If any record lacks provider data, the aggregate is `NOT_PROVABLE` (rendered as `N/A`).

4. **Classification Annotations**: Human-readable outputs (Markdown) must include a **Classification** column or annotation for every metric row (OBSERVED / VERIFIED / DIAGNOSTIC / TARGET / NOT_PROVABLE).

---

## Evidence Harness Compliance

The `EvidenceHarness` and adapters already enforce:

- `BaselineExecutionResult` captures only PROVIDER_OBSERVATION fields (may be `None`)
- `TokenOptExecutionResult` captures both LOCAL_ESTIMATE (always int) and PROVIDER_OBSERVATION (may be `None`)
- `ComparisonEvidence.provider_tokens_saved` returns `None` if either baseline or TokenOpt lacks provider input tokens
- `semantic_diagnostics` is explicitly DIAGNOSTIC and never affects `ExecutionStatus`
- `_ContextCaptureStage` is telemetry-only (reads `ctx.metrics`, never mutates `ctx.messages`)

---

## Enforcement

| Mechanism | Scope |
|-----------|-------|
| Schema (`schema.py`) | Field types and optionality enforce `None` for missing provider data |
| Adapters (`adapters.py`) | `extract_provider_usage_safe` returns `None` for untrustworthy zeros |
| Harness (`harness.py`) | `provider_tokens_saved` gated on both sides having provider data |
| Reporters (`reporters.py`) | **Must** label measurement basis in headers and output (this contract) |
| Tests (`test_evidence_harness.py`) | Focused tests for each prohibition above |

---

## Versioning

This contract is v1.0. Any relaxation requires:
1. Architecture decision recorded in `.ai/DECISIONS.md`
2. Explicit user approval
3. Coordinated test and reporter updates
4. Migration path for existing evidence artifacts