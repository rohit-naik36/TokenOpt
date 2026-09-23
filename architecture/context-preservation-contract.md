# TokenOpt Context Preservation Contract

**Document Version:** 1.1.0 (v0 Baseline Specification & Architecture Contract)  
**Status:** Approved Architecture Design Document  
**Baseline Git Commit:** `0e021f8` (`test: add compression fidelity baseline`)  
**Target Repository:** `TokenOpt` (`tokenopt/`)  

---

## 1. Executive Summary & Purpose

TokenOpt is transitioning from an open-loop heuristic prompt pre-processor to an optimization architecture governed by explicit, enforceable contracts.

In the v0 evaluation baseline (`evaluation/results/baseline.json`), the deterministic `CompressorStage` was benchmarked across a 12-case corpus spanning 1,050 original tokens. The empirical results demonstrated:
- **Aggregate Token Reduction:** 21.81% (229 tokens saved; 1,050 $\to$ 821 tokens on this specific corpus).
- **Fidelity Pass Rate:** 58.33% (7 of 12 cases passed; 5 of 12 cases failed).
- **Determinism:** 100% (12 of 12 cases produced byte-for-byte identical output across repeated runs).
- **Core Failure Mode:** Blind token-limit slicing (`truncate_to_tokens`) applied as a per-message ceiling caused catastrophic truncation damage to code syntax, JSON structures, Markdown tables, retrieved citations, and terminal diagnostic alerts.

The purpose of this **Context Preservation Contract** is to define what prompt optimization is permitted to alter, condense, or prune **before** designing the next optimization engine:
1. Define **preservation classes** and **transformation eligibility** across prompt content.
2. Establish a **strict preservation hierarchy** where token reduction can never override structural, lexical, or semantic integrity.
3. Formulate the **rules of engagement for message roles, structured syntax, and retrieved context**.
4. Define the precise boundary between **deterministic verification** and **semantic validation**.

This contract defines the constraints that any future optimization engine—including Compression Intelligence—must satisfy.

---

## 2. Current Implementation Status vs. Target Architecture

To prevent design intent from being mistaken for operational capabilities, the contract explicitly separates current production state from target architecture:

### Current Implementation Status (Commit `0e021f8`)
The current codebase (`tokenopt/pipeline/compressor.py`, `tokenopt/pipeline/base.py`, `tokenopt/utils/token_counter.py`) provides:
- **Deterministic heuristic compression:** Stateless regex whitespace normalization and conversational filler removal.
- **Per-message token ceiling:** Global target tokens applied as a blind per-message truncation ceiling.
- **Deterministic output:** Repeatable string-processing pipeline without external non-deterministic calls.
- **Basic fidelity evaluation:** 12-case benchmark verifying exact marker presence, role matching, AST syntax, JSON decode, and Markdown table closure.

The current implementation does **NOT** yet provide:
- Preservation classification (no P0/P1/P2/P3 awareness).
- Global budget allocation (no message- or span-level budget awareness).
- Protected-span tracking (cannot detect or pin critical entity spans).
- Role-aware transformation policy (treats system, user, and assistant strings uniformly).
- Structure-aware compression (no grammar-safe code, JSON, or table handlers).
- Semantic validation (evaluator only verifies exact substring containment and basic syntax).
- Closed-loop validation or automatic rollback (corrupted output is returned if no Python exception is thrown).

### Target Architecture
This contract establishes the formal specification for future optimization stages. Optimization stages will be required to classify input context, allocate global token budgets across eligible compressible spans, validate transformations against deterministic validators, and roll back upon validation failure.

---

## 3. Epistemological Standard & Quality Bar

Every rule and claim in this document is governed by one of four evidential standards:

1. **GUARANTEED BY CONTRACT:** A normative, binding architectural requirement that all compliant optimization stages must satisfy.
2. **OBSERVED IN CURRENT IMPLEMENTATION:** The actual behavior of the existing Python codebase (`tokenopt/`) as of commit `0e021f8`.
3. **SUPPORTED BY EVALUATION:** Empirically measured and reproducible via the 12-case benchmark harness (`evaluation/`).
4. **NOT YET ESTABLISHED:** Hypothesized capabilities, semantic preservation claims, or quality goals for which no automated verification currently exists in the repository.

---

## 4. The Preservation Hierarchy

Prompt content is organized into four distinct **preservation classes**. The hierarchy is strictly monotonic:

$$\mathbf{P0} \succ \mathbf{P1} \succ \mathbf{P2} \succ \mathbf{P3}$$

**Core Governing Law:**  
Token savings must **never** override a higher preservation class. An optimization that saves tokens while corrupting a P1 invariant or violating a P0 protection is a **failed optimization** and must be rejected.

```
+-------------------------------------------------------------------------+
| P0 — AUTHORITY / PROTOCOL PROTECTED                                     |
| Message roles, sequence ordering, system guardrails, tool schemas.     |
| Protected against generic lossy optimization. No structural change.     |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| P1 — INFORMATION PROTECTED                                              |
| Concrete invariants: lexical (IDs, keys), semantic (values), structural.|
| Must survive with exact referential, value, and syntactic integrity.   |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| P2 — MEANING-PRESERVING COMPRESSIBLE                                    |
| Verbose explanations, repetitive context, descriptive narrative.        |
| Eligible for meaning-preserving transformation at syntactic boundaries. |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| P3 — SAFELY REMOVABLE                                                   |
| Conversational pleasantries, filler phrases, formatting noise.         |
| Eligible for safe pruning outside structured literals and code.         |
+-------------------------------------------------------------------------+
```

### Contextual Units vs. Isolated Tokens

**Preservation classes apply to meaningful contextual spans and structural units, NOT to isolated words or tokens.**

An individual string or token cannot be classified in isolation from its structural context:
- The word `"please"` is **P3 (safely removable)** in ordinary conversational prose (`"Please tell me the status"`).
- The exact same string `"please"` is **P1 (information protected)** if it appears inside a code string literal (`assert response == "please"`).
- It is **P1 (information protected)** if it appears inside an exact user requirement (`"Query must match 'please'"`).
- It is **P0 (authority protected)** if it appears inside a negative system instruction (`"Rule: Do NOT include 'please' in output"`).

Therefore, classification must inspect the enclosing role, syntactic structure, and semantic boundaries before determining transformation eligibility.

---

## 5. P0 — AUTHORITY / PROTOCOL PROTECTED

P0 protects authority, protocol semantics, and foundational guardrails where generic optimization must not alter meaning or structure.

### Definition & Scope
- **No lossy or structural transformation** may be applied to P0 content.
- **Lossless normalization** (such as standardizing message dictionary container formatting or collapsing whitespace) is permitted only when explicitly validated.
- Protection applies to generic lossy optimization. It does not mean content can never be processed; rather, generic compressors must treat P0 elements as non-degradable authority boundaries.

### Candidate Analysis

| P0 Candidate | 1. Why Protection Is Required | 2. Repository & Evaluation Evidence | 3. Current Implementation Status | 4. Contract Requirement |
|---|---|---|---|---|
| **Message Role** (`system`, `developer`, `user`, `assistant`, `tool`) | Dictates LLM attention, authority boundary, instruction hierarchy, and provider API schema validation. | `test_heuristic_preserves_message_structure` verifies `[m["role"] for m in result.messages] == ["system", "user"]`. `runner.py` enforces `role_preservation_passed`. | **Satisfied**: `CompressorStage` preserves role keys via `{**msg}` unpacking. | **GUARANTEED BY CONTRACT**: Optimization stages must never alter, map, or omit a message `role`. |
| **Message Ordering** (Sequence index $0 \dots N$) | Multi-turn dialog context, few-shot conditioning, and reasoning chains depend strictly on temporal sequence order. | `CompressorStage` processes sequentially. `runner.py` verifies marker index. `ContextSummarizerStage` condenses history. | **Satisfied in CompressorStage**; **Violated in ContextSummarizerStage** (which drops intermediate history into a single synthetic turn). | **GUARANTEED BY CONTRACT**: Optimization stages must never reorder messages in a conversation. |
| **System & Developer Instructions** | Establish safety guardrails, operational policies, negative constraints, and output formatting contracts. Lossy truncation risks jailbreaks or silent contract failure. | In `case_02_instruction_heavy`, directives survived only because message was under token limit. In `test_compressor.py`, filler regex stripped words from system prompt. In `case_11`, tail alert was truncated. | **VIOLATED**: `CompressorStage` subjects system messages to identical regex filler deletion and per-message token-limit truncation as user messages. | **GUARANTEED BY CONTRACT**: System and developer instructions are P0 Protected against generic lossy transformation and blind truncation. |
| **Tool Definitions & Structured Tool Payloads** (`tools`, `tool_calls`, `tool_call_id`) | Provider APIs (OpenAI, Anthropic) enforce strict JSON Schema validation. Slicing tool schemas or serialized arguments causes immediate 400 Bad Request API errors. | `CompressorStage` ignores non-string content (`if not isinstance(content, str): continue`), but stringified JSON in `role: tool` messages is exposed to blind truncation. | **VIOLATED**: `role: tool` messages with string content are exposed to `truncate_to_tokens`. `tool_calls` metadata is unpacked but not schema-validated. | **GUARANTEED BY CONTRACT**: Tool definitions, tool call identifiers, and tool payload arguments are strictly P0 Protected against lossy alteration. |
| **Protected Message Metadata** (`name`, headers, custom keys) | Identifies multi-agent personae, user identities, or routing targets. | `test_heuristic_preserves_message_structure` verifies `"name": "alice"` survives dict unpacking. | **Satisfied**: `{**msg}` preserves metadata keys. | **GUARANTEED BY CONTRACT**: Message metadata keys must not be stripped or modified without explicit caller directive. |
| **Explicit Protected Content** (`<nocopy>`, tags, pinned spans) | Upstream callers must have authoritative power to mark specific prompt spans as non-optimizable. | No mechanism exists in `tokenopt/pipeline/compressor.py` or `tokenopt/config.py`. | **NOT ESTABLISHED**: The current implementation has zero awareness of caller-pinned spans. | **GUARANTEED BY CONTRACT**: When an explicit protection boundary is declared, the demarcated content is strictly P0 Protected. |

---

## 6. P1 — INFORMATION PROTECTED

P1 content comprises concrete factual entities, operational constraints, and syntactic structures whose meaning and referential integrity must survive.

### Invariant Triad: Lexical, Semantic, and Structural Invariants

Not every P1 item requires byte-for-byte lexical preservation. The contract separates preservation requirements into three distinct invariant types:

```
+-----------------------------------------------------------------------------+
|                          THE P1 INVARIANT TRIAD                             |
|                                                                             |
|  A. LEXICAL INVARIANTS       B. SEMANTIC INVARIANTS   C. STRUCTURAL         |
|  ---------------------       ----------------------      INVARIANTS         |
|  Exact string literal        Exact value & meaning    --------------------  |
|  must be preserved:          must be preserved:       Formal grammar/layout |
|  - Error codes               - Numeric thresholds     must remain valid:    |
|  - Identifiers               - Dates & milestones     - JSON structure      |
|  - JSON keys                 - Requirements           - Python code syntax  |
|  - Protocol tokens           - Negative constraints   - Markdown tables     |
|  - Exact search terms        - Configuration values   - Tool payload schema |
+-----------------------------------------------------------------------------+
```

### Invariant Mapping Matrix

| Category | Invariant Type | What Must Survive | Is Exact Lexical Required? | Baseline Evidence (`baseline.json`) | What Current Evaluator Can Verify |
|---|---|---|---|---|---|
| **Error Codes & Hex Signatures** | **Lexical** | Exact alphanumeric string (e.g. `KERN-ERR-0x89AB`). | **Yes**: Alteration destroys log lookup and automated diagnosis. | `case_11_truncation_risk` failed; `KERN-ERR-0x89AB` truncated away by 44.35% cut. | Exact substring containment in designated message role. |
| **Identifiers & Resource Names** | **Lexical** | Exact string literal of entity (e.g. `project Apollo`, `prod-db-replica-02`, `MW-88`). | **Yes**: Identifiers are discrete symbols, not semantic concepts. | `case_03_system_user` passed all 5 IDs. `case_07_json` truncated cluster endpoint. | Exact substring containment in designated message role. |
| **JSON Keys** | **Lexical** | Exact key names (e.g. `"cluster_id"`, `"node_count"`). | **Yes**: Downstream code deserializes to concrete field names. | `case_07_json` preserved early keys, but truncated later keys. | Exact substring containment + `json.loads` check. |
| **URLs & Endpoints** | **Lexical / Canonical** | Protocol, hostname, port, and query path (e.g. `https://dr.internal.net/v1`, `port 8443`). | **Lexical or Canonical**: Canonical normalization (e.g. trailing slash) allowed; path truncation prohibited. | `case_01` preserved `port 8443`. `case_07` truncated endpoint mid-string. | Exact substring containment in designated message role. |
| **Numeric Constraints & Limits** | **Semantic + Value** | Numerical scalar and associated unit/dimension (e.g. `5 sections`, `150 words`, `99.99%`). | **No, but Value Must Match**: Paraphrasing structure allowed, but numerical quantity must remain exact. | `case_04_numeric_constraints` passed (`5 sections`, `150 words`). `case_08` truncated SLA numbers. | Exact substring containment in designated message role. Evaluator does NOT verify semantic equivalence. |
| **Dates & Temporal Bounds** | **Semantic** | Exact temporal anchor and milestone tag (e.g. `2026-01-15`, `Q4 2025`). | **Semantic; Lexical where protocol requires**: ISO-8601 preferred for APIs; natural language allowed if meaning is identical. | `case_05_date_constraints` passed (`Phase-2`, `2026-01-15` preserved). | Exact substring containment. Evaluator does NOT verify semantic date equivalence. |
| **JSON Values** | **Semantic + Type** | Typed values (integers, booleans, strings). | **Semantic + Type**: Formatting whitespace may change; scalar types and values must not. | `case_07_json` truncated boolean and string values. | `json.loads()` verifies syntax, not schema equivalence. |
| **Programming Code** | **Structural + Semantic** | Syntactically valid code that preserves logic and interface. | **Structural + Semantic**: Whitespace minification allowed; AST syntax and execution semantics must survive. | `case_06_code` failed; `ast.parse` raised `IndentationError` on `if amount <=`. | `ast.parse()` verifies syntax ONLY. Does NOT establish semantic equivalence. |
| **Markdown Tables** | **Structural** | Complete table with matching column counts and closed rows. | **Structural**: Alignment spacing may be normalized; row termination and column layout must survive. | `case_08_markdown_table` failed; truncated mid-cell at `| EU`. | Table parser verifies column counts and row termination. |
| **Negative Constraints** | **Semantic** | Restriction modal and restricted action (e.g. "Do not include...", "Never deploy without..."). | **Semantic**: Phrasing may be condensed, but negative polarity must remain unambiguous. | `case_09` system message had "Base answers only on...", which survived. | Exact substring containment. |
| **RAG Citations** | **Lexical + Structural** | Citation identifiers bound to retrieved facts (e.g. `[DOC-401]`). | **Lexical for ID; Structural for chunk**: Identifier must remain attached to factual passage. | `case_09_rag_context` failed; citations survived, but factual text was truncated. | Exact substring containment in designated turn. |

> [!IMPORTANT]
> **Current Evaluator Boundary:**  
> The current evaluation framework (`evaluation/runner.py`) uses exact substring markers and basic parser calls (`ast.parse()`, `json.loads()`). It **does not prove semantic preservation**. Stating that an invariant is "semantic" defines a contract goal for future validation layers, not an existing verified capability.

---

## 7. P2 — MEANING-PRESERVING COMPRESSIBLE

P2 comprises natural language prose, narrative explanations, and conversational verbosity that carry conceptual meaning but contain redundant tokens.

### Conditions for Transformation Eligibility
Content is eligible for P2 compression **only** when all of the following conditions are satisfied:
1. **Unit of Transformation:** Transformation must operate on **meaningful syntactic units** (complete sentences, independent clauses, full paragraphs).
2. **Pre-Transformation Scan:** Candidate text must be scanned for embedded P0 invariants and P1 entities (dates, numbers, IDs, URLs, negative rules). Any embedded P1 entity must be preserved according to its invariant type.
3. **Deterministic Validator Gate:** The transformed text must pass all applicable deterministic structural and entity validators before acceptance.

### Compression vs. Truncation

```
+-----------------------------------------------------------------------------+
|              CRITICAL DISTINCTION: COMPRESSION VS. TRUNCATION               |
|                                                                             |
|  COMPRESSION                              TRUNCATION                        |
|  -----------                              ----------                        |
|  - Meaning-preserving transformation       - Discards content unilaterally   |
|  - Removes linguistic redundancy          - Inherently lossy                |
|  - Rewrites or condenses prose            - Slices across grammar bounds    |
|  - Preserves facts, entities, structures  - Drops terminal instructions     |
|  - Requires validation before acceptance  - Must obey strict protection     |
|                                             rules; cannot be equated        |
|                                             with compression                |
+-----------------------------------------------------------------------------+
```

The current `CompressorStage` implementation treats token truncation as compression:
```python
# tokenopt/pipeline/compressor.py, line 88
content = truncate_to_tokens(content, target_tokens, ctx.model)
```
This conflation is the direct cause of all 5 baseline fidelity failures (`case_06` through `case_09`, and `case_11`). Under this contract, **compression and truncation are strictly decoupled**. Generic optimization stages may perform compression; they may not perform blind truncation.

---

## 8. P3 — SAFELY REMOVABLE

P3 comprises token sequences that carry zero factual, logical, or directive weight in the conversational context.

### Permissible Scope
- Conversational pleasantries (`"Hello!"`, `"Good morning"`).
- Filler politeness (`"please"`, `"kindly"`, `"would you please"`).
- Conversational hedging (`"I think"`, `"I believe"`, `"in my opinion"`).
- Structural whitespace noise (consecutive newlines $\ge 3$, excessive spaces).

### Operating Rules
1. **Context-Dependent Eligibility:** P3 pruning is permitted **only** outside code fences, outside string literals, outside negative instructions, and outside quoted user terms.
2. **Clean Boundary Collapsing:** Pruning a filler word must cleanly collapse surrounding whitespace without leaving double spaces or detached punctuation marks.
3. **Turn Non-Destruction:** Pruning must not delete an entire turn unless the turn consisted 100% of pleasantries and removing it does not violate provider message-sequence rules.

---

## 9. Role & Transformation Architecture

Message role alone does **not** determine whether content is compressible. The architecture separates **authority defaults** from **transformation eligibility**:

```
+-------------------------------------------------------------------------+
| ROLE                                                                    |
| Determines authority and default protection posture:                   |
| - system/developer: strong protection defaults                          |
| - user: mixed intent; candidate for entity extraction & filler pruning  |
| - assistant: historical context; candidate for summarization            |
| - tool: API payload; strict structural protection defaults              |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| STRUCTURE                                                               |
| Identifies formal grammars: code blocks, JSON, Markdown tables, prose.  |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| ENTITY / CONSTRAINT                                                     |
| Identifies concrete P1 invariants (dates, numbers, IDs, URLs, negations).|
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| PRESERVATION CLASS                                                      |
| Classifies spans into P0, P1, P2, or P3 based on context.                |
+-------------------------------------------------------------------------+
                                    |
                                    v
+-------------------------------------------------------------------------+
| TRANSFORMATION ELIGIBILITY                                              |
| Determines what operations (prune, condense, minify) are allowed.       |
+-------------------------------------------------------------------------+
```

### Role Policy Summary
- **`system` & `developer`:** Authority defaults = P0 Protected. Content classification may identify verbose background explanations (P2) only if explicitly authorized, but generic lossy truncation is strictly forbidden.
- **`user`:** Authority defaults = Open. Content classification identifies P1 constraints (must survive), P2 prose (compressible), and P3 filler (removable).
- **`assistant`:** Authority defaults = Contextual. Older multi-turn history may be summarized into a single compact turn, provided recent turns ($k \ge 2$) remain intact.
- **`tool`:** Authority defaults = P0/P1 Structural. Serialized JSON or XML payloads require strict syntactic and schema protection.

---

## 10. Structured Content Policy

Structured content contains formal grammars. Naive token truncation invariably causes syntax corruption.

### 1. Python & Programming Code (`code`)
- **Syntactic Invariant:** Code blocks must maintain **100% Syntactic Validity**. Any transformation must parse cleanly via `ast.parse()`.
- **Semantic Intent Invariant:** Function signatures, control flow, exceptions, and return expressions must be preserved.
- **Precise Evaluation Boundary:** `ast.parse()` establishes **syntactic validity only**. It does **NOT** establish semantic equivalence. Proving that transformed code retains identical execution semantics requires additional validation (e.g. execution tests or AST semantic comparison) beyond the current evaluation harness.

### 2. JSON Payloads (`json`)
- **Structural Invariant:** JSON objects and arrays must maintain **100% Syntactic Validity** via `json.loads()`.
- **Lexical & Semantic Invariants:** JSON keys are lexical invariants. JSON values and scalar types are semantic invariants.
- **Permissible Transformation:** Whitespace minification (removing non-semantic spacing outside string literals) is permitted as meaning-preserving compression.

### 3. Markdown Tables (`markdown_table`)
- **Structural Invariant:** Tables must maintain **100% Structural Consistency**:
  - Every row must begin and terminate with a pipe delimiter (`|`).
  - Column counts across header, delimiter row, and all data rows must be identical.
  - The delimiter row (`|:---|:---:|`) must remain intact.
- **Prohibition:** Truncating a table mid-row (as occurred in `case_08_markdown_table` at `| EU`) is strictly prohibited.

---

## 11. RAG & Retrieved Context Policy

Evidence from `case_09_rag_context` and `tokenopt/pipeline/rag_optimizer.py` establishes the operational requirements for retrieved context:

1. **Atomic Chunk Boundaries:** Retrieved documents must be managed as **atomic chunks**, never sliced mid-sentence or mid-chunk.
2. **Identifier-Content Binding:** Citation identifiers (`[DOC-xxx]`, `[Source: ...]`) must remain strictly bound to their content. Retaining an identifier while truncating its factual payload is a contract violation.
3. **Chunk Filtering vs. Slicing:** An optimization stage may discard an entire chunk if it is scored as non-relevant (`similarity < threshold`), but must **never** truncate a relevant chunk into an incomplete fragment.
4. **P1 Entity Quarantine:** Retrieved passages containing contact information, SLA limits, API endpoints, or compliance constraints must be treated as P1 Protected.

---

## 12. Token Budget Allocation Model

### The Current Flaw
`CompressorStage` calculates:
$$\text{target\_tokens} = \text{int}(\text{original\_token\_count} \times \text{compression\_ratio})$$
It then applies `target_tokens` as an individual per-message truncation ceiling. This causes single-message prompts or long user messages to be unilaterally cut by 50% regardless of overall prompt size or content compressibility.

### Target Conceptual Budget Model
The future architecture must treat the compression target as a **global prompt budget**:

```
GLOBAL TARGET BUDGET
        ↓
reserve protected content (P0 authority + P1 invariants)
        ↓
allocate remaining budget across eligible P2/P3 content
        ↓
apply meaning-preserving transformations
        ↓
validate against deterministic validators
        ↓
accept / retry / rollback
```

### Incompressible Floor as a Conceptual Constraint
The sum of protected content forms an **incompressible floor**:
- If a prompt consists predominantly of P0 instructions, P1 code, or non-redundant data (such as `case_12_minimal_compression`), the available budget for safe reduction is near zero.
- The engine must **never** force reduction beyond the incompressible floor. If a requested 50% ratio cannot be satisfied safely, the engine must perform only the safe reduction or pass through the original prompt.
- The precise budget allocation algorithm is an implementation concern for the next architecture phase.

---

## 13. Closed-Loop Validation & Rollback Protocol

The contract replaces subjective quality judgments with a precise, deterministic validation rule:

### Precise Architectural Requirement
**Transformations are accepted ONLY when all applicable deterministic preservation and structural validators pass.**

```
Candidate Transformed Prompt
             │
             ▼
+------------------------------------------+
| APPLICABLE DETERMINISTIC VALIDATORS      |
| 1. Role & Order: unchanged sequence      |
| 2. P1 Lexical: exact marker presence     |
| 3. Code: ast.parse() syntax validity     |
| 4. JSON: json.loads() syntax validity    |
| 5. Table: row/pipe/column consistency    |
| 6. Determinism: identical on repeat      |
+------------------------------------------+
             │
      Pass all checks?
      ┌──────┴──────┐
     YES            NO
      │              │
      ▼              ▼
   ACCEPT          REJECT
(Emit output)   (ROLLBACK to original)
```

### Deterministic Acceptance Criteria
- **JSON:** Must parse via `json.loads()` without error; schema validation where schema is known.
- **Python / Code:** Must parse via `ast.parse()` without `SyntaxError` or `IndentationError`.
- **Markdown Tables:** Must pass structural parsing (closed rows, consistent column count).
- **Required Entities:** All extracted P1 lexical markers must be present in their designated roles.
- **Role Invariants:** Message count and roles must match the contract rules.

### Rollback Action
If any applicable validator fails:
- **Decision:** `REJECT`.
- **Action:** Immediately discard the candidate transformation and roll back to the original unmodified representation (`OptimizationContext.original_messages`).
- **Telemetry:** Record the specific failure reason in `ctx.metrics` for observability.

---

## 14. Current Implementation Gap Analysis

| Contract Requirement | Current Implementation (`CompressorStage`) | Status | Repository Evidence |
|---|---|:---:|---|
| **Role Immutability** | Preserves `role` string via `{**msg}` dict unpacking. | **Satisfied** | `test_heuristic_preserves_message_structure` |
| **Message Order Immutability** | Processes and appends messages in list order. | **Satisfied** | `runner.py`, `cases.py` |
| **System Instruction Protection** | Subject to filler regex deletion and token-limit truncation. | **Violated** | Filler stripped in tests; truncated if length $> T_{\text{target}}$ |
| **Developer Instruction Protection** | No concept of `developer` role exists in pipeline. | **Not Established** | Absent from `tokenopt/` |
| **Tool Payload Protection** | Non-string content passed through; stringified JSON in messages truncated. | **Partially Satisfied** | Non-string check in line 61; string payloads truncated |
| **Message Metadata Preservation** | `{**msg}` preserves metadata keys. | **Satisfied** | `name: "alice"` preserved in tests |
| **Numeric Value Preservation** | No entity protection; truncated if past token limit. | **Violated** | SLA numbers dropped in `case_08`, `case_09` |
| **Date / Timestamp Preservation** | No entity protection; survives only if prompt is short. | **Partially Satisfied** | `case_05` passed (short prompt); long dates truncated |
| **Identifier Preservation** | No entity protection; truncated if past token limit. | **Violated** | Node panic ID dropped in `case_11`; endpoint in `case_07` |
| **Error Code Preservation** | No entity protection; truncated if past token limit. | **Violated** | `KERN-ERR-0x89AB` dropped in `case_11` |
| **URL / Endpoint Preservation** | No entity protection; truncated mid-string. | **Violated** | `case_07` failover endpoint truncated mid-URL |
| **SLA Threshold Preservation** | No entity protection; truncated if past token limit. | **Violated** | `case_08` EU SLA breach truncated |
| **Negative Constraint Preservation** | No protection; words in negative rules can be stripped. | **Violated** | Filler regex runs over negative instructions |
| **Python Syntax Integrity** | Code truncated mid-statement; indentation corrupted. | **Violated** | `case_06_code` failed `ast.parse` (`IndentationError`) |
| **JSON Syntax Integrity** | Payloads sliced mid-string; unclosed braces. | **Violated** | `case_07_json` failed `json.loads` (`JSONDecodeError`) |
| **Markdown Table Integrity** | Rows sliced mid-cell; unterminated pipe characters. | **Violated** | `case_08_markdown_table` failed column/row check |
| **RAG Chunk Boundary Integrity** | Truncates RAG context mid-chunk, dropping facts. | **Violated** | `case_09_rag_context` sliced at `[DOC-403]: Incident` |
| **Global Budget Allocation** | Global target applied as per-message truncation ceiling. | **Violated** | Single-message prompts cut to 50% regardless of size |
| **Closed-Loop Rollback** | Pipeline rolls back on uncaught exception; no rollback on bad fidelity. | **Partially Satisfied** | Corrupted text returned when no exception is thrown |
| **Semantic Equivalence Verification** | Evaluator only checks substring markers and syntax. | **Not Established** | No semantic evaluator in repository |

---

## 15. Evaluation Corpus Mapping & Coverage Gaps

### Benchmark Corpus Summary (Commit `0e021f8`)
The 12-case evaluation corpus established:
- **Total original tokens:** 1,050
- **Total optimized tokens:** 821
- **Tokens saved:** 229 (21.81% aggregate reduction)
- **Fidelity pass rate:** 58.33% (7 passed, 5 failed)
- **Determinism:** 100% (12/12)

> [!WARNING]
> **Corpus Limitation Notice:**  
> The 21.81% reduction and 58.33% pass rate are **strictly empirical measurements of this specific 12-case corpus**. They cannot be generalized as a broader production claim.

### Case Mapping to Contract Invariants

| # | Case ID | Category | Preservation Concerns | Applicable Classes | Baseline Result | Reason for Baseline Result |
|---|---|---|---|---|:---:|---|
| 1 | `case_01` | `simple_conversation` | Microservice IDs, gRPC, JWT, port 8443; pleasantries. | P1 Lexical (IDs)<br>P3 Removable (filler) | **PASS** | Short messages; filler removed without hitting token ceiling. |
| 2 | `case_02` | `instruction_heavy` | Level-4, 3 bullet points, `[EXEC-SUMMARY]` tag. | P0 Authority (system)<br>P1 Lexical/Semantic | **PASS** | System message length was under per-message ceiling. |
| 3 | `case_03` | `system_user` | Postgres 16, replica cluster ID, table, index, MW-88. | P0 Authority<br>P1 Lexical (IDs) | **PASS** | Short messages; preserved within message length. |
| 4 | `case_04` | `numeric_constraints` | Section count (5), word count (150 words), Q4 2025. | P1 Semantic + Value | **PASS** | Numbers survived filler removal in short user turn. |
| 5 | `case_05` | `date_constraints` | Milestone Phase-2, ISO date 2026-01-15. | P1 Semantic (date) | **PASS** | Date survived in short user turn. |
| 6 | `case_06` | `code` | Python class, retry constant, method, exception. | P1 Structural (AST)<br>P1 Semantic (code) | **FAIL** | Truncated at token 39 (`if amount <=`); failed `ast.parse()`. |
| 7 | `case_07` | `json` | Cluster ID, node count, instance type, failover URL. | P1 Structural (JSON)<br>P1 Lexical (keys) | **FAIL** | Truncated at token 52; unclosed quote; failed `json.loads()`. |
| 8 | `case_08` | `markdown_table` | SLA targets, availability %, breach status, table pipes. | P1 Structural (table)<br>P1 Lexical (values) | **FAIL** | Truncated at token 71 (`\| EU`); failed row closure check. |
| 9 | `case_09` | `rag_context` | Citation IDs (`[DOC-xxx]`), mTLS endpoint, SLA contact. | P1 Structural (chunks)<br>P1 Lexical (contact) | **FAIL** | Truncated at token 85; dropped DOC-403 answer text. |
| 10 | `case_10` | `repetitive_context` | Auth token, strict validation boolean; excess newlines. | P1 Lexical (token)<br>P3 Removable (newlines) | **PASS** | Newlines collapsed; core tokens preserved. |
| 11 | `case_11` | `truncation_risk` | Telemetry log; terminal fatal panic alert, hex error. | P1 Lexical (alert, hex)<br>P2 Compressible | **FAIL** | Truncated at token 64; terminal alert dropped completely. |
| 12 | `case_12` | `minimal_compression` | Non-redundant SQL query. | P1 Structural/Lexical | **PASS** | Incompressible; 0% reduction; query unmodified. |

### Critical Gaps in Evaluation Coverage
The 12-case corpus leaves critical enterprise patterns unbenchmarked:
1. **Tool Calling Payloads:** Zero cases test `role: "tool"` or `tool_calls` schemas.
2. **Developer Role:** Zero cases evaluate `role: "developer"` prompt authority.
3. **Multimodal Content:** Zero cases test multi-part content (image URLs, attachments).
4. **Large Context Windows (>2,000 tokens):** All corpus cases are small ($\le 129$ tokens). Documents at 8k–64k scale are unrepresented.
5. **XML / HTML Structured Context:** No cases evaluate XML tags or HTML documents.
6. **Streaming Ingestion:** No cases evaluate streaming token delivery.

---

## 16. Non-Goals

To maintain clear scope, this document explicitly does **NOT** define:
1. **Specific Compressor Implementation:** Does not specify algorithms, tokenizers, or data structures.
2. **Compression Intelligence Engine Design:** Does not design model architecture, classifiers, or routing logic.
3. **LLM-as-a-Judge Formulations:** Does not define prompt templates or scoring rubrics for LLM judges.
4. **Target Compression Percentages:** Does not mandate a universal reduction target (e.g. 50%).
5. **Model Selection & Cost Optimization:** Does not address model routing or token pricing.
6. **Latency & Throughput SLA Targets:** Does not set millisecond execution limits for pipeline stages.
7. **Provider-Specific Wire Protocols:** Does not specify HTTP payload formatting for OpenAI or Anthropic proxies.

---

## 17. Implications for the Next Optimization Architecture

The next prompt optimization architecture must implement a closed-loop pipeline satisfying the contract constraints:

```
INPUT CONTEXT (Messages, Roles, Metadata)
                  │
                  ▼
+--------------------------------------------------+
| 1. ANALYZER                                      |
|    - Inspect message roles & authority           |
|    - Detect structured boundaries (code, JSON,   |
|      tables, tool payloads)                      |
|    - Extract P1 entities (dates, numbers, IDs)   |
+--------------------------------------------------+
                  │
                  ▼
+--------------------------------------------------+
| 2. PRESERVATION MAP                              |
|    - Assign P0/P1/P2/P3 preservation classes     |
|    - Mark transformation eligibility per span    |
|    - Calculate incompressible floor              |
+--------------------------------------------------+
                  │
                  ▼
+--------------------------------------------------+
| 3. CANDIDATE PLANNER                             |
|    - Allocate global target budget               |
|    - Target P3 removable & P2 compressible spans |
|    - Protect P0 and P1 budgets unconditionally   |
+--------------------------------------------------+
                  │
                  ▼
+--------------------------------------------------+
| 4. TRANSFORMATION                                |
|    - Safe P3 pruning (outside code & literals)   |
|    - Meaning-preserving P2 condensation         |
|    - Lossless minification of JSON/whitespace    |
+--------------------------------------------------+
                  │
                  ▼
+--------------------------------------------------+
| 5. VALIDATOR                                     |
|    - Run applicable deterministic checks:        |
|      * Role & sequence ordering check            |
|      * P1 lexical entity preservation check      |
|      * ast.parse() for code blocks               |
|      * json.loads() for JSON blocks              |
|      * Table structure & column count check      |
+--------------------------------------------------+
                  │
          Validation outcome?
          ┌───────┴───────┐
       PASS              FAIL
          │                 │
          ▼                 ▼
+-------------------+   +--------------------------+
| 6. ACCEPT         |   | 7. ROLLBACK              |
| Emit optimized    |   | Restore original         |
| context to caller |   | context checkpoint       |
+-------------------+   +--------------------------+
```

### Component Responsibilities:
1. **Analyzer:** Inspects incoming messages to identify roles, structured content boundaries, and critical entities before any transformation begins.
2. **Preservation Map:** Annotates contextual spans with preservation classes (P0, P1, P2, P3) and defines transformation eligibility.
3. **Candidate Planner:** Allocates the global token budget across eligible compressible spans while holding P0 and P1 spans invariant.
4. **Transformation:** Applies meaning-preserving compression or safe pruning. Blind truncation is eliminated.
5. **Validator:** Executes all applicable deterministic syntactic and entity checks on the candidate output.
6. **Accept / Rollback:** Emits accepted outputs or automatically rolls back to the uncompressed input if any validator fails.
