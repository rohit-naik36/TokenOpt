# TokenOpt Deterministic Compression-Fidelity Evaluation Harness

## 1. Purpose

This evaluation harness establishes the permanent v0 deterministic compression-fidelity baseline for TokenOpt's deterministic `CompressorStage`.

The primary goals are to:
1. Measure realistic **token reduction** achieved by deterministic heuristic transformations (whitespace normalization, conversational filler removal, token-limit slicing).
2. Measure **role-aware preservation of critical information** (concrete markers tied strictly to message roles and positions).
3. Detect **structural truncation damage** across code, JSON, and tabular payloads via syntactic validation.
4. Verify **deterministic behavior** (ensuring identical inputs yield byte-for-byte identical optimized messages across repeated runs).

> **Important**: This evaluator establishes a deterministic baseline. It does not establish semantic equivalence. Passing fidelity checks proves only that required markers survived in their designated roles without syntactic breakage; it does not measure downstream reasoning capability.

---

## 2. Why This Is Separate from `tests/`

The codebase contains a fast unit and regression test suite under `tests/` (166 tests) verifying software contracts, pipeline stage wiring, configuration parsing, and error-handling paths.

This `evaluation/` directory serves a distinct benchmark purpose:
- **Evaluation vs. Verification**: `tests/` verifies that code executes without crashing according to unit contracts. `evaluation/` benchmarks output quality and behavioral characteristics of optimization strategies against realistic prompts.
- **Failures as Empirical Findings**: In `tests/`, any failure indicates broken code that must be fixed immediately. In `evaluation/`, fidelity failures (such as truncation damage on single-message code or JSON payloads) are valuable empirical findings documenting the known baseline capabilities and limitations of the current compressor.
- **Benchmark Artifacts**: Evaluation produces persistent performance telemetry and machine-readable benchmark reports (`evaluation/results/baseline.json`) used for tracking progress across versions.

---

## 3. Corpus Categories

The benchmark corpus consists of exactly 12 representative cases across 12 distinct categories:

| # | Category | Description | Primary Characteristic |
|---|---|---|---|
| 1 | `simple_conversation` | Multi-turn deployment consultation | Conversational pleasantry and filler removal across multi-turn context |
| 2 | `instruction_heavy` | Strict formatting rules and security policies | Multi-directive system instructions with negative constraints |
| 3 | `system_user` | Target database persona with user query | System role setup with specific database tables, index names, and maintenance tags |
| 4 | `numeric_constraints` | Financial and latency metrics | Preservation of numeric quantities, transaction counts, and section limits |
| 5 | `date_constraints` | Milestone and launch scheduling | Preservation of contractual ISO dates, milestones, and deadlines |
| 6 | `code` | Python class and error handling | Detection of truncation damage on source code functions and exception handling |
| 7 | `json` | Structured infrastructure config payload | Detection of truncation damage on structured JSON keys, endpoints, and values |
| 8 | `markdown_table` | SLA compliance matrix | Detection of truncation damage on tabular columns, rows, and status indicators |
| 9 | `rag_context` | Retrieved reference documentation | Preservation of citation IDs (`[DOC-xxx]`), API paths, and SLA timeframes |
| 10 | `repetitive_context` | Excessive whitespace and repeated filler | Verification that whitespace collapse (`\n{3,}`) and filler removal leave core tokens intact |
| 11 | `truncation_risk` | Long diagnostic telemetry with critical alert at the end | Deliberate verification of truncation damage when critical facts sit at message tails |
| 12 | `minimal_compression` | Dense, non-redundant SQL statement | Verification that compact, non-compressible content remains uncorrupted (0% reduction) |

---

## 4. Role-Aware Preservation

Previous global marker substring searches searched across all messages indiscriminately. In multi-turn dialogues, this allowed corrupted or truncated user messages to pass if the assistant happened to repeat the user's terms in a subsequent turn.

The hardened evaluation harness associates every preservation expectation with an explicit tuple:
```python
ExpectedMarker(message_index: int, role: str, marker: str)
```

### Validation Rules:
1. **Target Message Presence**: The marker must exist verbatim within `messages[message_index]["content"]`.
2. **Role Fidelity**: The message at `message_index` must have `role == expected_role`.
3. **Surviving in Wrong Role / Wrong Message**: If a marker is missing from its expected message but appears in a different message or role, it is flagged as a `role_mismatch` and fails both `role_preservation_passed` and `marker_preservation_passed`.
4. **Dropped Message**: If compression deletes an entire message so that `message_index >= len(messages)`, both role and marker preservation fail.

---

## 5. Structural Safety Checks

Structured content categories undergo deterministic syntactic checks on the optimized output:

### 1. Python Code (`case_06_code`)
- Code snippets (delimited by markdown code fences or detected via language definitions like `class` or `def`) are parsed with Python's standard `ast.parse()`.
- If an `ast.SyntaxError` or `IndentationError` occurs (e.g. from truncation slicing mid-expression like `if amount <=`), `syntax_valid` is set to `False`, and `python_syntax_invalid` is added to `failure_reasons`.

### 2. JSON Payloads (`case_07_json`)
- JSON payload boundaries (`{...}` or `[...]`) are parsed via `json.loads()`.
- If `json.JSONDecodeError` occurs (e.g. from unclosed quotes, missing braces, or truncated key-value pairs), `syntax_valid` is set to `False`, and `json_invalid` is added to `failure_reasons`.

### 3. Markdown Tables (`case_08_markdown_table`)
- Markdown tables are evaluated using deterministic structural parsing:
  - **Row Termination**: Every table row must begin with `|` and terminate with `|`.
  - **Column Consistency**: All rows (header, separator, data) must contain the exact same column count.
  - **Separator Integrity**: A valid markdown separator row with alignment hyphens and colons (`:---`, `---:`, `:---:`, `---`) must immediately follow the header.
  - **Data Rows**: At least one data row must be present.
- If any row is truncated mid-cell (e.g. `| EU`), column counts mismatch, or the separator is broken, `syntax_valid` is set to `False`, and `markdown_structure_invalid` is added to `failure_reasons`.

### Non-Structured Cases
- For non-structured categories (e.g. `simple_conversation`, `rag_context`, `numeric_constraints`), `syntax_valid` evaluates to `None` (`null` in JSON).

---

## 6. Failure Classifications

The evaluator provides explicit machine-readable failure reason codes:

| Code | Trigger Condition |
|---|---|
| `missing_required_marker` | One or more expected markers were not found in their designated message. |
| `role_mismatch` | An expected marker survived only in a different message or role, or the message role changed. |
| `python_syntax_invalid` | Code in `code` category failed `ast.parse()` validation due to syntax corruption. |
| `json_invalid` | JSON payload in `json` category failed `json.loads()` validation due to unclosed/truncated JSON. |
| `markdown_structure_invalid` | Table in `markdown_table` category failed structural consistency or termination checks. |
| `nondeterministic_output` | Repeated compression of the same input produced differing optimized messages. |

---

## 7. Metrics & Schema

### Case Schema
```json
{
  "case_id": "case_01_simple_conversation",
  "category": "simple_conversation",
  "original_tokens": 98,
  "optimized_tokens": 92,
  "tokens_saved": 6,
  "reduction_pct": 6.12,
  "preserved_markers": [
    {
      "message_index": 0,
      "role": "user",
      "marker": "project Apollo"
    }
  ],
  "missing_markers": [],
  "role_preservation_passed": true,
  "marker_preservation_passed": true,
  "syntax_valid": null,
  "deterministic_passed": true,
  "fidelity_passed": true,
  "failure_reasons": []
}
```

### Aggregate Metrics
- `total_original_tokens`: Total input tokens across all cases.
- `total_optimized_tokens`: Total output tokens across all cases.
- `total_tokens_saved`: Cumulative tokens saved.
- `aggregate_reduction_pct`: Overall reduction percentage across the corpus.
- `cases_total`: Total number of cases evaluated (12).
- `fidelity_passed`: Number of cases passing marker, role, syntax, and determinism checks.
- `fidelity_failed`: Number of cases with any fidelity failure.
- `fidelity_pass_rate`: Percentage of cases passing fidelity (e.g. 58.33%).
- `deterministic_passed`: Number of cases producing identical output across runs (12).
- `deterministic_failed`: Number of nondeterministic cases (0).

---

## 8. Important Notice on Aggregate Reduction

> [!WARNING]
> The **21.81% aggregate reduction** reported by this harness is **specific to this 12-case corpus**.
>
> It must **NOT** be cited or marketed as a general TokenOpt performance claim:
> 1. It reflects a mixed benchmark containing deliberately uncompressible cases (e.g. `minimal_compression` at 0.0%) and intentionally oversized prompts (e.g. `markdown_table` at 44.96%).
> 2. The token savings in several cases (code, JSON, tables, tail alerts) were achieved through destructive truncation that rendered the prompts syntactically or functionally invalid.
> 3. True production reduction will vary based on user prompt length distributions and the compression strategies employed.

---

## 9. How to Run

### Run the Evaluation Harness:
```powershell
.\.venv\Scripts\python.exe evaluation\runner.py
```
Outputs terminal summary and updates `evaluation/results/baseline.json`.

### Run Evaluator Self-Tests:
```powershell
.\.venv\Scripts\python.exe evaluation\test_evaluator.py
```
Validates role-aware checking, structural syntax validators, and error classifications.

### Run Main Test Suite:
```powershell
.\.venv\Scripts\python.exe -m pytest
```
Verifies that all 166 core repository tests remain intact and passing.
