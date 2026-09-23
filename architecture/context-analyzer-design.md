# Context Analyzer & Preservation Map — Architecture Design Document

**Document Version:** 1.2.0 (Design & Reconnaissance Specification)  
**Status:** Approved for Design Phase (Pre-Implementation)  
**Baseline Git Commit:** `7070c7a` (`docs: define context preservation contract`)  
**Target Repository:** `TokenOpt` (`tokenopt/`)  
**Target File Location:** `architecture/context-analyzer-design.md`  

---

## 1. Objective [CURRENT & TARGET]

The **Context Preservation Contract** ([`architecture/context-preservation-contract.md`](file:///C:/Users/rohit/Projects/TokenOpt/architecture/context-preservation-contract.md)) established the formal invariants governing prompt optimization in TokenOpt. It decoupled meaning-preserving compression from destructive token truncation and mandated the architectural evaluation flow:

$$\text{ROLE} \to \text{STRUCTURE} \to \text{ENTITY / CONSTRAINT} \to \text{PRESERVATION CLASS} \to \text{TRANSFORMATION ELIGIBILITY}$$

The baseline fidelity benchmark (`evaluation/`) demonstrated that blind token-boundary truncation destroys structured syntax and critical invariants (as observed across code, JSON, and telemetry test cases). The objective of this document is to define the exact implementation design for the **Context Analyzer** and its output artifact, the **Preservation Map**.

This design:
1. Reconciles the theoretical contract with the actual codebase (`tokenopt/pipeline/base.py`, `tokenopt/pipeline/compressor.py`, `tokenopt/config.py`, `tokenopt/clients/base.py`).
2. Defines the streamlined data models for `PreservationMap` without premature token-budget fields or runtime overhead.
3. Specifies deterministic structure classification with explicit certainty semantics (`DETECTED`, `NOT_DETECTED`, `AMBIGUOUS`) rather than naive parse-success assumptions.
4. Generalizes entity and constraint classification across abstract categories.
5. Resolves the unit-of-analysis strategy: message-level and structural-block granularity for MVP with `start_char: int | None = None` and `end_char: int | None = None` reserved for future span-level decomposition without implementing span tracking or offset remapping in MVP.
6. Establishes the core distinction: **"Contains protected P1 information" $\neq$ "Entire unit is P1."**
7. Clarifies responsibility boundaries across the Analyzer, Candidate Planner, Transformer, Validator, and Rollback mechanisms.
8. Scopes runtime validation: first runtime implementation focuses exclusively on deterministic checks (markers, syntax, structure, ordering), explicitly designating semantic equivalence checking as future work.
9. Clearly separates `CURRENT` implementation realities from `TARGET` architectural goals.

---

## 2. Current Architecture Findings [CURRENT]

### 2.1 Context Ingestion & Message Representation [CURRENT]
- **Entry Point [CURRENT]:** Caller messages enter the system via `BaseOptimizedClient.chat_completion(messages: list[dict], model: str, ...)` in `tokenopt/clients/base.py`.
- **Pipeline Invocation [CURRENT]:** The client calls `ctx = self.pipeline.run(messages, model, model_explicit=explicit, **kwargs)`.
- **Data Model [CURRENT]:** In `OptimizationPipeline.run()` (`tokenopt/pipeline/base.py`), an `OptimizationContext` instance is instantiated:
  ```python
  ctx = OptimizationContext(
      messages=messages,
      model=model,
      config=self.config,
      model_explicit=model_explicit,
      metadata=metadata,
  )
  ```
- **Post-Init Isolation [CURRENT]:** `OptimizationContext.__post_init__` creates an isolated working copy:
  ```python
  self.messages = deepcopy(self.messages)
  if not self.original_messages:
      self.original_messages = deepcopy(self.messages)
  if not self.original_token_count:
      self.original_token_count = count_message_tokens(self.messages, self.model)
  ```
- **Message Shape [CURRENT]:** Messages are represented exclusively as standard chat completion dictionaries (`dict[str, Any]`), with keys `"role"` (`str`), `"content"` (`str | list`), and optional metadata (`"name"`, `"tool_calls"`, `"tool_call_id"`).

### 2.2 Stage Communication & State Mutation [CURRENT]
- **Stage Execution [CURRENT]:** `OptimizationPipeline` iterates sequentially over a list of `PipelineStage` instances:
  ```python
  for stage in self.stages:
      if not self._should_run_stage(stage):
          continue
      checkpoint_messages = deepcopy(ctx.messages)
      checkpoint_model = ctx.model
      checkpoint_metadata = deepcopy(ctx.metadata)
      try:
          ctx = stage(ctx)
      except Exception as e:
          ctx.messages = checkpoint_messages
          ctx.model = checkpoint_model
          ctx.metadata = checkpoint_metadata
          ctx.metrics[f"{stage.name}_error"] = str(e)
  ```
- **Communication Channels [CURRENT]:** Stages communicate strictly by mutating attributes on `ctx`:
  - `ctx.messages`: Mutated message list.
  - `ctx.model`: Model string (potentially updated by `RouterStage`).
  - `ctx.metadata`: Inter-stage key-value store (e.g. `cache_hit`, `cached_response`, `cache_key`).
  - `ctx.metrics`: Observability dictionary (latencies, token counts, execution flags).

### 2.3 The Checkpoint & Rollback Limitation [CURRENT vs TARGET]
- **Exception-Only Rollback [CURRENT]:** The current checkpoint mechanism in `OptimizationPipeline` rolls back **only upon an uncaught Python exception**.
- **The Silent Failure Problem [CURRENT]:** If a stage executes without an unhandled exception but produces syntactically broken code (as occurred in `case_06_code`), truncated JSON (`case_07_json`), or discarded alert assertions (`case_11_truncation_risk`), the pipeline **accepts the corrupted text and forwards it to the provider API**.
- **Fidelity Gate Requirement [TARGET]:** A `PreservationMap` provides the formal invariant specification needed for **closed-loop fidelity validation**, allowing the pipeline or downstream validator to reject corrupted candidates and roll back to original messages even when no runtime exception was raised.

---

## 3. Responsibility Boundaries Across Optimization Components [TARGET]

To prevent architectural blurring between analysis, planning, transformation, and validation, responsibilities are strictly partitioned across five distinct pipeline components:

### 3.1 Component Responsibility Matrix [TARGET]

| Component | What It DOES | What It DOES NOT Do |
|---|---|---|
| **Analyzer (`AnalyzerStage`)** | • Detects structure with explicit certainty (`DETECTED`, `NOT_DETECTED`, `AMBIGUOUS`).<br>• Extracts entities and constraints into abstract categories.<br>• Assigns preservation classification.<br>• Describes transformation eligibility and required validators.<br>• Attaches immutable `PreservationMap` to context. | • **DOES NOT** enforce the preservation hierarchy.<br>• **DOES NOT** select compression candidates.<br>• **DOES NOT** allocate token budgets or calculate floors.<br>• **DOES NOT** perform transformations or text mutations.<br>• **DOES NOT** validate transformed output or execute rollbacks. |
| **Candidate Planner** | • Interprets the diagnostic `PreservationMap`.<br>• Selects eligible transformation candidates.<br>• Considers global token budget and target reduction. | • Does not scan raw text or extract regex entities directly.<br>• Does not execute text mutations. |
| **Transformer (`CompressorStage`, `ContextSummarizerStage`)** | • Performs the selected transformations (e.g. prunes P3 pleasantries, minifies structural whitespace, condenses P2 prose). | • Does not decide global budget strategy.<br>• Does not validate its own output. |
| **Validator (`ValidatorStage`)** | • Checks the resulting transformed context against the `PreservationMap` using deterministic gates (markers, syntax, structure, ordering). | • Does not perform transformations or rewrite text.<br>• Does not plan optimization strategies. |
| **Rollback (`ClosedLoopRollbackGate`)** | • Restores previous or original message representation when applicable validation checks fail. | • Does not alter validation thresholds or force-accept corrupted output. |

```
=============================================================================
                      CONTEXT ANALYZER BOUNDARIES
=============================================================================
WHAT THE ANALYZER DOES:
  1. Inspects message roles and establishes baseline authority defaults.
  2. Detects formal structural content blocks with explicit certainty
     (DETECTED, NOT_DETECTED, AMBIGUOUS).
  3. Identifies entity and constraint categories (identifiers, error codes,
     endpoints, numeric constraints, dates, negative constraints, configs).
  4. Classifies units into preservation classes (P0, P1, P2, P3).
  5. Determines transformation eligibility using formal contract operations
     (lossless normalization, meaning-preserving compression, removal, truncation).
  6. Registers required validator names for downstream verification.
  7. Attaches the immutable PreservationMap to OptimizationContext.

WHAT THE ANALYZER DOES NOT DO:
  - DOES NOT enforce the preservation hierarchy (delegated to Candidate Planner).
  - DOES NOT select compression candidates (delegated to Candidate Planner).
  - DOES NOT compute or allocate token budgets.
  - DOES NOT alter, reorder, compress, rewrite, or truncate any message.
  - DOES NOT validate transformed output (delegated to Validator).
  - DOES NOT execute rollbacks (delegated to Rollback Gate).
  - DOES NOT call external LLMs, embeddings, or non-deterministic inference.
=============================================================================
```

---

## 4. PreservationMap Data Model [TARGET]

The `PreservationMap` must be concise, strongly typed, serializable, and strictly bounded to diagnostic metadata.

### 4.1 Core Types & Enums [TARGET]

```python
from enum import Enum
from dataclasses import dataclass, field
from typing import Any

class PreservationClass(str, Enum):
    P0_AUTHORITY = "P0"       # Authority & protocol protected (no lossy change)
    P1_INFORMATION = "P1"     # Concrete invariants (lexical, semantic, structural)
    P2_COMPRESSIBLE = "P2"    # Meaning-preserving compressible (prose, explanations)
    P3_REMOVABLE = "P3"       # Safely removable (filler, pleasantries, spacing)

class InvariantType(str, Enum):
    LEXICAL = "lexical"       # Exact string literal must survive
    SEMANTIC = "semantic"     # Exact value / meaning must survive
    STRUCTURAL = "structural" # Grammar / AST syntax must survive

class StructuralType(str, Enum):
    PROSE = "prose"                   # Free-form natural language
    CODE_PYTHON = "code_python"       # Python code block or script
    JSON = "json"                     # JSON object or array
    MARKDOWN_TABLE = "markdown_table" # Tabular Markdown layout
    TOOL_PAYLOAD = "tool_payload"     # Serialized tool call / result

class DetectionCertainty(str, Enum):
    DETECTED = "detected"             # Confirmed structure via grammar/parser
    NOT_DETECTED = "not_detected"     # Confirmed absence of specialized structure
    AMBIGUOUS = "ambiguous"           # Partial syntax, malformed block, or conflict

class EntityCategory(str, Enum):
    IDENTIFIER = "identifier"                       # Resource/system/cluster IDs, citation tags
    ERROR_CODE = "error_code"                       # Hex codes, error tags, exception types
    URL_OR_ENDPOINT = "url_or_endpoint"             # HTTP/HTTPS URLs, endpoints, port specs
    NUMERIC_CONSTRAINT = "numeric_constraint"       # Quantities with units, percentages, counts
    DATETIME_CONSTRAINT = "datetime_constraint"     # ISO dates, quarters, deadlines, timestamps
    NEGATIVE_CONSTRAINT = "negative_constraint"     # Explicit prohibitions ("do not", "never")
    CONFIGURATION_VALUE = "configuration_value"     # Param assignments, environment flags
    SECURITY_COMPLIANCE = "security_compliance"     # Protocols, tokens, auth directives
```

### 4.2 Invariant & Context Unit Specifications [TARGET]

```python
@dataclass(frozen=True)
class PreservedInvariant:
    """A concrete item that must survive optimization intact."""
    category: EntityCategory
    invariant_type: InvariantType
    marker: str                   # Exact substring, token, or identifier
    message_index: int            # Message turn index where invariant originates
    role: str                     # Expected message role
    description: str = ""         # Diagnostic label (e.g. "cluster_id", "timeout")

    def to_dict(self) -> dict[str, Any]:
        return {
            "category": self.category.value,
            "invariant_type": self.invariant_type.value,
            "marker": self.marker,
            "message_index": self.message_index,
            "role": self.role,
            "description": self.description,
        }

@dataclass(frozen=True)
class TransformationEligibility:
    """Defines permitted transformation operations rooted in contract terminology."""
    allow_lossless_normalization: bool = False       # Safe whitespace cleanup, formatting
    allow_meaning_preserving_compression: bool = False # Condensation, rephrasing
    allow_removal: bool = False                      # Safe removal of filler/pleasantries
    allow_truncation: bool = False                   # Token-boundary slicing (Strictly False for P0/P1)
    required_validators: tuple[str, ...] = ()       # Validators required to accept mutations

@dataclass(frozen=True)
class ContextUnit:
    """A structural block or contextual span within a message."""
    message_index: int
    role: str
    structural_type: StructuralType
    detection_certainty: DetectionCertainty
    preservation_class: PreservationClass
    eligibility: TransformationEligibility
    start_char: int | None = None  # Offset in message content (reserved for future spans; None in MVP)
    end_char: int | None = None    # End offset (reserved for future spans; None in MVP)
    invariants: tuple[PreservedInvariant, ...] = ()
```

### 4.3 Root PreservationMap Model [TARGET]

The MVP `PreservationMap` contains only units, invariants, and query helpers. Token budget calculations (such as `incompressible_token_floor`) are deliberately excluded: the analyzer identifies protected content, whereas budget allocation and feasible compression targets belong to the downstream Candidate Planner.

```python
@dataclass(frozen=True)
class PreservationMap:
    """Immutable diagnostic map emitted by the Context Analyzer."""
    units: tuple[ContextUnit, ...] = ()
    invariants: tuple[PreservedInvariant, ...] = ()

    def get_invariants_for_message(self, message_index: int) -> list[PreservedInvariant]:
        return [inv for inv in self.invariants if inv.message_index == message_index]

    def get_units_for_message(self, message_index: int) -> list[ContextUnit]:
        return [u for u in self.units if u.message_index == message_index]

    def to_dict(self) -> dict[str, Any]:
        return {
            "invariants_count": len(self.invariants),
            "units_count": len(self.units),
            "invariants": [inv.to_dict() for inv in self.invariants],
            "units": [
                {
                    "message_index": u.message_index,
                    "role": u.role,
                    "structural_type": u.structural_type.value,
                    "detection_certainty": u.detection_certainty.value,
                    "preservation_class": u.preservation_class.value,
                    "start_char": u.start_char,
                    "end_char": u.end_char,
                    "eligibility": {
                        "allow_lossless_normalization": u.eligibility.allow_lossless_normalization,
                        "allow_meaning_preserving_compression": u.eligibility.allow_meaning_preserving_compression,
                        "allow_removal": u.eligibility.allow_removal,
                        "allow_truncation": u.eligibility.allow_truncation,
                        "required_validators": list(u.eligibility.required_validators),
                    },
                    "invariants_count": len(u.invariants),
                }
                for u in self.units
            ],
        }
```

### 4.4 Data Model Field Evaluation Matrix [TARGET]

| Proposed Field | Producer | Primary Consumer | MVP Justification |
|---|---|---|---|
| `units.message_index` / `role` | Analyzer Stage | Validator, Planner | **MVP Required**: Maps structural classification directly to chat message turns. |
| `units.structural_type` | Analyzer Stage | Compressor, Validator | **MVP Required**: Dispatches grammar-specific handlers (Python AST, JSON, Table). |
| `units.detection_certainty` | Analyzer Stage | Compressor, Validator | **MVP Required**: Flags ambiguous/malformed structures to prevent destructive mishandling. |
| `units.preservation_class` | Analyzer Stage | Candidate Planner | **MVP Required**: Enforces P0/P1/P2/P3 preservation hierarchy. |
| `units.eligibility` | Analyzer Stage | Optimization Stages | **MVP Required**: Defines allowed mutations using formal contract terms. |
| `invariants.category` | Analyzer Stage | Validator, Observability | **MVP Required**: Classifies extracted items into 8 abstract domains. |
| `invariants.marker` | Analyzer Stage | `check_markers()` Validator | **MVP Required**: The concrete string literal that must survive optimization. |
| `invariants.invariant_type` | Analyzer Stage | Validator | **MVP Required**: Dispatches lexical vs. semantic vs. structural validation gates. |
| `units.start_char` / `end_char` | None in MVP (Future Span Segmenter) | Future Span Rewriter | **Future-Facing**: Defined as `int | None = None`. Reserved for future span-level decomposition. In MVP, represents whole messages or structural blocks; offsets are neither populated nor consumed. No offset remapping is required in MVP. |
| *`incompressible_token_floor`* | *N/A (Removed)* | *N/A (Excluded)* | **Excluded from MVP**: Token floor computation requires model-specific tokenizers and candidate planning, which belongs to the Planner, not the Analyzer. |

---

## 5. Granularity Strategy & The Meaning of Message-Level Classification [CURRENT vs TARGET]

### 5.1 The MVP Choice: Message & Structural-Block Units [TARGET - MVP]
In the MVP implementation, `ContextUnit` boundaries operate at the **message level** and **structural-block level** (e.g. a discrete code block, JSON payload, or table).

**Explicit Rules for Character Offsets in MVP:**
1. **MVP represents whole messages or structural blocks:** Units correspond to entire message dictionaries or top-level code/data blocks.
2. **MVP does not populate or consume character offsets:** `start_char` and `end_char` remain `None`.
3. **Reserved for future span-level decomposition:** The schema includes these fields so that future span segmenters can introduce character-level tracking without breaking data model contracts.
4. **No offset remapping in MVP:** Because MVP does not track character offsets, no complex offset-drift remapping engine is required.
5. **No span tracking implemented:** The analyzer does not slice strings into sub-sentence spans in MVP.

### 5.2 The Fundamental Architectural Distinction: "Contains P1" vs "Entire Unit is P1" [TARGET]

A critical design requirement is to avoid over-protecting whole messages:

$$\mathbf{\text{“Contains protected P1 information”}} \neq \mathbf{\text{“Entire unit is P1.”}}$$

A message or block may **contain** P1 invariants without every part of that message being P1 or immutable.

#### Concrete Example:
Consider the following user message:
```text
"Please deploy version 4.2 to staging.
Do not restart during peak hours.
Thanks."
```

This single message contains:
- **P3 filler:** `"Please "`
- **P1 numeric / version constraint:** `"version 4.2"`
- **P1 resource identifier:** `"staging"`
- **P1 negative constraint:** `"Do not restart during peak hours."`
- **P3 closing phrase:** `"Thanks."`

#### MVP Operational Limitation vs. Architectural Reality:
- **MVP Operational Reality:** Because the analyzer operates at message/block granularity, it records the protected invariants (`"version 4.2"`, `"staging"`, `"Do not restart during peak hours."`) within the unit. Transformation eligibility at the whole-unit level is therefore **conservative** (e.g. `allow_removal = False`, `allow_truncation = False`) to prevent naive whole-message pruning or destructive token slicing.
- **Architectural Meaning:** The model **must NOT imply that every character in the unit is P1**. The P3 filler (`"Please "`, `"Thanks."`) remains conceptually compressible or removable, provided that downstream rewriters or future span-level transformers preserve the recorded P1 invariants intact.

### 5.3 Architectural Contract for Future Span-Level Decomposition [TARGET - FUTURE]
While MVP classifies at the message/block boundary without populating offsets, the data model supports future decomposition into sub-message spans:

```
[User Message: 86 characters]
 ├── Span A [chars 0-7]: "Please "
 │    ├── Category: Polite Preamble
 │    ├── Preservation Class: P3_REMOVABLE
 │    └── Eligibility: allow_removal=True, allow_meaning_preserving_compression=False
 │
 ├── Span B [chars 7-38]: "deploy version 4.2 to staging.\n"
 │    ├── Category: Action, Version & Resource Identifiers
 │    ├── Preservation Class: P1_INFORMATION
 │    ├── Invariants: "version 4.2" (CONFIG), "staging" (ID)
 │    └── Eligibility: allow_removal=False, allow_meaning_preserving_compression=False
 │
 ├── Span C [chars 38-78]: "Do not restart during peak hours.\n"
 │    ├── Category: Negative Directive
 │    ├── Preservation Class: P1_INFORMATION
 │    ├── Invariants: "Do not restart during peak hours." (NEGATIVE_CONSTRAINT)
 │    └── Eligibility: allow_removal=False, allow_meaning_preserving_compression=False
 │
 └── Span D [chars 78-85]: "Thanks."
      ├── Category: Polite Closing
      ├── Preservation Class: P3_REMOVABLE
      └── Eligibility: allow_removal=True, allow_meaning_preserving_compression=False
```

In future phases, a span rewriter can independently prune Span A and Span D while keeping Spans B and C immutable.

---

## 6. Structure Classification & Detection Certainty [TARGET]

Structure detection must not rely on simplistic binary assumptions (such as `ast.parse() succeeds == Python code`). The analyzer introduces three explicit certainty states:

```
                  +-----------------------------------+
                  |      Incoming Message Content     |
                  +-----------------------------------+
                                    |
          +-------------------------+-------------------------+
          |                         |                         |
          v                         v                         v
     [DETECTED]                [AMBIGUOUS]             [NOT_DETECTED]
 High-certainty grammar    Conflicting cues or      Confirmed natural
 (fenced code, valid JSON,  malformed structure      language prose
  pipe-delimited table)     (unclosed brace, AST     (no syntax markers)
                            syntax error on code)
          |                         |                         |
          v                         v                         v
   Apply specialized       CONSERVATIVE FALLBACK      Standard prose
   grammar handlers        Treat as P1 protected      compression rules
   (AST/JSON minifier)     Do not alter or mangle
```

### 6.1 Detection Certainty States [TARGET]
1. **`DETECTED`:** High confidence match.
   - Example: Content enclosed in ` ```python ` fences with valid syntax, or a string starting with `{` and ending with `}` that parses via `json.loads()`.
2. **`NOT_DETECTED`:** Confirmed natural language prose with no structural syntax markers.
3. **`AMBIGUOUS`:** Structural cues are present but fail formal grammar validation or exhibit conflicting signals.
   - *Example 1 (Malformed / Partial JSON):* A string begins with `{"cluster_id": "c-12` but lacks a closing brace, failing `json.loads()`. It is **not** prose; it is malformed or truncated JSON. Treating it as prose could cause further corruption. It must be flagged `AMBIGUOUS` and assigned conservative protection.
   - *Example 2 (False Positive AST):* Trivial English phrases like `"deploy"` or `"system status"` parse as valid Python expressions (`ast.Name` or `ast.Expr`). The analyzer must **not** classify bare words as `CODE_PYTHON` simply because `ast.parse()` did not raise a `SyntaxError`. Bare code detection requires Python-specific structural tokens (`def `, `class `, `import `, `return `, assignments) in addition to AST parsing.

### 6.2 Deterministic MVP Grammar Gates [TARGET]

| Structural Type | Pre-Filter / Sentinel Cues | Formal Grammar Gate | Certainty Resolution |
|---|---|---|---|
| **`CODE_PYTHON`** | Markdown fences (`` ```python `` or `` ``` ``), or bare keywords (`def `, `class `, `import `, `from `) | `ast.parse()` trial | **DETECTED:** Fence + valid AST, or bare keyword + valid AST.<br>**AMBIGUOUS:** Fence present, but `ast.parse()` raises `SyntaxError`.<br>**NOT_DETECTED:** No fence, no code keywords. |
| **`JSON`** | Leading `{` or `[`, trailing `}` or `]` after strip | `json.loads()` trial | **DETECTED:** Enclosed in brackets AND `json.loads()` succeeds.<br>**AMBIGUOUS:** Enclosed in brackets, but `json.loads()` raises `JSONDecodeError`.<br>**NOT_DETECTED:** Does not start/end with JSON delimiters. |
| **`MARKDOWN_TABLE`** | $\ge 2$ lines containing `\|` delimiters | Header/separator verification (`\|:?--+.*:?\|`) | **DETECTED:** Header + separator + data rows match column counts.<br>**AMBIGUOUS:** Pipe lines present, but column counts mismatched.<br>**NOT_DETECTED:** No delimiter lines. |
| **`TOOL_PAYLOAD`** | `role == "tool"` or `"tool_calls"` key present | Schema verification | **DETECTED:** Valid tool response dictionary or list.<br>**NOT_DETECTED:** Standard chat message. |
| **`PROSE`** | Default fallback | Natural language heuristic | **DETECTED:** Standard prose with no structural sentinels. |

---

## 7. Entity & Constraint Classification [TARGET]

Within conversational prose and instructions, the analyzer detects concrete invariants across **8 abstract categories**. Concrete regexes are treated as illustrative example patterns for the benchmark corpus, not an exhaustive set.

### 7.1 Abstract Entity Categories & Pattern Examples [TARGET]

| Category | Description | Example Target Patterns (Illustrative) | Invariant Type | MVP Preservation Class |
|---|---|---|:---:|:---:|
| **`IDENTIFIER`** | System, resource, cluster, database, and citation tags | `\[DOC-\d+\]`, `\b(?:cluster\|node\|replica\|service)-[a-z0-9-]+\b`, `MW-\d+`, `prod-db-[a-z0-9-]+` | `LEXICAL` | **P1** |
| **`ERROR_CODE`** | Hexadecimal fault codes, error symbols, exception types | `\b(?:[A-Z0-9_]+-)+(?:ERR\|ERROR\|0x[0-9a-fA-F]+)\b`, `KERN-ERR-0x[0-9a-fA-F]+`, `ValueError` | `LEXICAL` | **P1** |
| **`URL_OR_ENDPOINT`** | Network URIs, REST endpoints, host:port specs | `https?://[^\s"'<>]+`, `\bport\s+\d{2,5}\b`, `/v\d+/[a-zA-Z0-9_/]+` | `LEXICAL` | **P1** |
| **`NUMERIC_CONSTRAINT`** | Quantities bound to units, percentages, rate limits, counts | `\b\d+(?:\.\d+)?\s*(?:sections?\|words?\|tokens?\|%\|percent\|ms\|minutes?\|hours?\|req/min)\b` | `SEMANTIC` | **P1** |
| **`DATETIME_CONSTRAINT`** | ISO calendar dates, quarters, deadlines, timestamps | `\b\d{4}-\d{2}-\d{2}\b`, `\bQ[1-4]\s+\d{4}\b`, `\b\d{2}:\d{2}(?::\d{2})?\s*(?:UTC\|GMT)?\b` | `SEMANTIC` | **P1** |
| **`NEGATIVE_CONSTRAINT`** | Explicit prohibitions and negative operational rules | `\b(?:do not\|never\|must not\|cannot\|without\|prohibit)\b\s+[^.!?\n]+` | `SEMANTIC` | **P1** |
| **`CONFIGURATION_VALUE`** | Parameter assignments, environment flags, settings | `\b[a-z_]+=[a-z0-9_.]+\b`, `enforce_strict_validation=true`, `MAX_RETRIES` | `LEXICAL` | **P1** |
| **`SECURITY_COMPLIANCE`** | Protocols, security policies, auth directives | `JWT tokens`, `gRPC`, `SLA`, `Level-[0-9]`, `[EXEC-SUMMARY]` | `LEXICAL` | **P1** |

---

## 8. Role Policy & Authority Defaults [CURRENT & TARGET]

In accordance with the contract, **message role establishes authority defaults**, while **content classification determines actual transformation eligibility**:

```
+-----------------------------------------------------------------------------------+
| ROLE               AUTHORITY DEFAULT     CONTENT OVERRIDE / TRANSFORMATION RULES |
+-----------------------------------------------------------------------------------+
| system             P0_AUTHORITY          Immune to generic lossy compression.    |
|                    (Default Invariant)   Lossless normalization permitted only if |
|                                          all directives are preserved.           |
+-----------------------------------------------------------------------------------+
| developer          P0_AUTHORITY          Strict authority invariant. Zero lossy   |
|                    (Default Invariant)   mutations permitted under any condition. |
+-----------------------------------------------------------------------------------+
| user               P2_COMPRESSIBLE       Inspected by Structure & Entity scanner: |
|                    (Default Baseline)    - Code, JSON, tables -> P1 Structural    |
|                                          - Identifiers, dates -> P1 Invariant     |
|                                          - Prose explanations  -> P2 Compressible |
|                                          - Polite pleasantries -> P3 Removable    |
+-----------------------------------------------------------------------------------+
| assistant          P2_COMPRESSIBLE       Historical multi-turn context may be     |
|                    (Default Baseline)    condensed, provided recent turns         |
|                                          (k >= 2) and P1 invariants remain intact.|
+-----------------------------------------------------------------------------------+
| tool               P0_AUTHORITY          Structured outputs returned by APIs.     |
|                    (Default Invariant)   JSON schema must remain 100% valid.      |
|                                          Zero token-limit slicing permitted.      |
+-----------------------------------------------------------------------------------+
```

---

## 9. Preservation Class Mapping & Transformation Eligibility [TARGET]

The analyzer outputs unambiguous transformation eligibility flags rooted in contract terms:

| Preservation Class | Lossless Normalization? | Meaning-Preserving Compression? | Removal / Pruning? | Token Truncation? | Required Validators |
|---|:---:|:---:|:---:|:---:|---|
| **`P0_AUTHORITY`** | **Restricted** (Whitespace only) | **No** | **No** | **No** | `role_ordering_validator`, `invariant_validator` |
| **`P1_INFORMATION (Lexical)`** | **No** | **No** | **No** | **No** | `exact_marker_validator` |
| **`P1_INFORMATION (Structural)`**| **Yes** (JSON/AST minify) | **No** | **No** | **No** | `python_syntax_validator`, `json_syntax_validator`, `table_structure_validator` |
| **`P1_INFORMATION (Semantic)`** | **No** | **No** | **No** | **No** | `exact_value_validator` |
| **`P2_COMPRESSIBLE`** | **Yes** | **Yes** (Condensation) | **No** | **No** | `invariant_retention_validator` |
| **`P3_REMOVABLE`** | **Yes** | **Yes** | **Yes** (Pruning) | **No** | `syntax_integrity_validator`, `whitespace_cleaner` |

**Fundamental Architectural Invariant:** `allow_truncation` is **False across all preservation classes**. Blind token-boundary slicing is prohibited across the board.

---

## 10. Validator Requirements & Staged Validation Scope [CURRENT vs TARGET]

### 10.1 Current Offline Validators (`evaluation/`) [CURRENT]
The repository currently contains deterministic baseline validation checks in `evaluation/`:
- `check_markers()`: Checks exact substring containment for expected markers within expected message indices and roles.
- `validate_python_syntax()`: Validates Python syntax using native standard library `ast.parse()`.
- `validate_json_syntax()`: Validates JSON syntax using native standard library `json.loads()`.
- `validate_markdown_table_structure()`: Verifies column count consistency and header pipe closures.
- `evaluate_repeatability()`: Verifies 100% byte-for-byte deterministic output repeatability.

> [!IMPORTANT]
> **Semantic Equivalence Limitation [CURRENT]:** Current evaluation validators verify lexical presence and basic parse syntax; they **do not** establish semantic equivalence or verify that conversational meaning has been preserved without distortion.

### 10.2 First Runtime Validator Implementation (`tokenopt/pipeline/validator.py`) [TARGET - FIRST RUNTIME IMPLEMENTATION]
The first runtime validator implementation must focus strictly on **deterministic checks** that can be reliably executed without external models or non-deterministic inference:
1. **Protected Marker Preservation:** Verifies that all extracted P1 lexical invariant markers survive in the output messages.
2. **Role & Message Ordering:** Enforces that message turns, conversational order, and authority invariants (P0) remain uncorrupted.
3. **Python Syntax Validation:** Uses `ast.parse()` where `CODE_PYTHON` units are present to guarantee syntactically valid code.
4. **JSON Syntax Parsing:** Uses `json.loads()` where `JSON` payload units are present to guarantee syntactic integrity.
5. **Markdown Structural Integrity:** Verifies pipe and header alignment where tables are present.
6. **Invariant-Specific Deterministic Checks:** Uses regex verification to confirm numeric values, dates, and negative prohibitions have not been sliced.

### 10.3 Future Validation Capabilities [TARGET - FUTURE WORK]
> [!NOTE]
> **Semantic Equivalence is Future Work:** Semantic equivalence checking (e.g. NLI evaluation, embedding similarity, or LLM-as-a-judge verification of meaning) is explicitly a TARGET/FUTURE capability. It is **not** part of the first runtime validator implementation. No implementation for semantic equivalence is invented or assumed in the MVP phase.
- **JSON Schema Conformance:** Formal validation of JSON payloads against explicit JSON-Schema / OpenAPI specifications.
- **Semantic Equivalence Validation:** Model-based or NLI-based verification to ensure condensed prose preserves full conversational meaning.

---

## 11. Pipeline Integration Recommendation [CURRENT vs TARGET]

### 11.1 Tradeoff Analysis of Stage Positioning

```
OPTION A: Router -> Analyzer -> Compressor
  Tradeoff: Router operates on raw input before analysis; Analyzer only assists Compressor.
  Weakness: Router cannot use structural classification (e.g. knowing code or JSON is present).

OPTION B: Analyzer -> Router -> Compressor  <-- RECOMMENDED [TARGET]
  Tradeoff: Analyzer runs as the very first pipeline stage.
  Strength: All downstream stages (Router, Candidate Planner, Compressor, Summarizer, Cache)
            have access to the PreservationMap. Router can route based on detected code or JSON!

OPTION C: Integrated into OptimizationContext.__post_init__
  Tradeoff: Analysis occurs synchronously during OptimizationContext instantiation.
  Weakness: Violates single responsibility principle; tightly couples pipeline core
            to regex heuristics; prevents configuring or benchmarking analyzer independently.
```

### 11.2 Target Pipeline Architecture & Responsibility Separation [TARGET]

```
INPUT (messages, model, metadata)
               │
               ▼
      +─────────────────+
      |  AnalyzerStage  |  <── ANALYZER: Inspects context; emits ctx.preservation_map
      +─────────────────+
               │
               ▼
      +─────────────────+
      |   RouterStage   |  <── ROUTER: Selects model using structural/complexity clues
      +─────────────────+
               │
               ▼
      +─────────────────+
      | CandidatePlanner|  <── PLANNER: Interprets map; selects candidates; considers budget
      +─────────────────+
               │
               ▼
      +─────────────────+
      | CompressorStage |  <── TRANSFORMER: Performs selected safe P3 pruning / P2 condensation
      +─────────────────+
               │
               ▼
      +─────────────────+
      | ValidatorStage  |  <── VALIDATOR: Checks output against ctx.preservation_map
      +─────────────────+
               │
         Passes validators?
         ┌──────┴──────┐
        YES            NO
         │              │
         ▼              ▼
      ACCEPT         ROLLBACK: Restores original representation
```

### 11.3 OptimizationContext Modification [TARGET]
In `tokenopt/pipeline/base.py`, add a typed, backward-compatible field to `OptimizationContext`:
```python
@dataclass
class OptimizationContext:
    messages: list[dict[str, Any]]
    model: str
    config: TokenOptConfig
    model_explicit: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    original_messages: list[dict[str, Any]] = field(default_factory=list)
    original_token_count: int = 0
    preservation_map: PreservationMap | None = None  # Non-breaking diagnostic addition
```

---

## 12. Impact on Existing Pipeline Stages [CURRENT vs TARGET]

| Pipeline Stage | Current Behavior [CURRENT] | Target Behavior with PreservationMap [TARGET] |
|---|---|---|
| **`RouterStage`** | Uses naive keyword heuristics (`"code"`, `"function"`) on raw text. | Directly inspects `ctx.preservation_map.units` for `StructuralType.CODE_PYTHON` to route to code-capable models with high precision. |
| **`CompressorStage`** | Truncates messages if token count exceeds budget, destroying code and JSON syntax. | Ceases blind truncation. Checks `unit.eligibility`. Skips P0 and P1 units entirely. Prunes only P3 units. Condenses P2 units only if invariants are preserved. |
| **`ContextSummarizerStage`** | Condenses history older than 3 messages into naive string concatenation (`First query: ... \| Last query: ...`). | Consults `preservation_map` to ensure P0 system prompts and P1 code/entities in historical messages are preserved intact. |
| **`CacheStage`** | Hashes raw message content (`_make_cache_key`). | Preserved without change. Deterministic inputs produce identical preservation maps; cache semantics remain stable. |
| **`RAGOptimizerStage`** | Prunes chunks based on embedding similarity. | Consults `preservation_map` to avoid slicing across `[DOC-xxx]` citation tags or retrieved SLA facts. |
| **`FewShotSelectorStage`** | Appends few-shot examples to message history. | Preserved without change; does not mutate user-turn invariants. |

---

## 13. MVP Scope Boundary [TARGET]

To ensure immediate implementability without over-engineering, the MVP scope is strictly bounded:

### In MVP Scope:
1. `PreservationMap`, `ContextUnit` (`start_char: int | None = None`, `end_char: int | None = None`), `PreservedInvariant`, and `TransformationEligibility` dataclasses.
2. Structure detector with certainty classification (`DETECTED`, `NOT_DETECTED`, `AMBIGUOUS`) for:
   - `CODE_PYTHON` (Markdown fences + bare keyword heuristics).
   - `JSON` (enclosed bracket syntax).
   - `MARKDOWN_TABLE` (pipe-delimited table layouts).
   - `PROSE` (natural language default).
3. Entity detector for 8 abstract categories using deterministic regexes.
4. Message-level and structural-block unit granularity (no span tracking).
5. First runtime validator focused exclusively on deterministic checks (markers, syntax, structure, ordering).
6. `AnalyzerStage` class conforming to `PipelineStage` interface.
7. Configuration flag `enable_analyzer: bool = True` in `TokenOptConfig`.
8. Full unit test suite covering all 12 evaluation corpus cases.

### Out of MVP Scope:
- No machine learning models, sentence transformers, or external LLM calls.
- No semantic equivalence checking in first runtime validator (deferred to future work).
- No token budget allocation or token floor calculation inside the analyzer.
- No sub-sentence character-offset rewriters or span tracking; no offset remapping in MVP.
- No parsers for non-Python programming languages (Java, C++, Rust).
- No modifications to provider proxy protocols or API client classes.

---

## 14. Test Strategy (Mapped to the 12 Evaluation Cases) [CURRENT & TARGET]

The first `AnalyzerStage` implementation will be verified against the 12 benchmark cases from `evaluation/cases.py`:

| Case ID | Input Content Characteristic | Expected Structure & Certainty | Expected Invariants (P0 / P1) | Expected Eligibility (P2 / P3) |
|---|---|:---:|---|---|
| `case_01` | Multi-turn deployment chat | `PROSE` (`DETECTED`) | P1 Lexical: `project Apollo`, `service-auth`, `service-billing`, `gRPC`, `JWT tokens`, `port 8443` | P3 Removable: `"Hello!"`, `"please"`, `"basically"`, `"I think"` |
| `case_02` | Directive-heavy system instructions | `PROSE` (`DETECTED`) | P0 Authority: System rules<br>P1 Lexical: `Level-4`, `3 bullet points`, `[EXEC-SUMMARY]` | P3 Removable: `"Please kindly"`, `"I believe"` in user turn |
| `case_03` | Database cluster query | `PROSE` (`DETECTED`) | P0 Authority: Persona<br>P1 Lexical: `PostgreSQL 16`, `prod-db-replica-02`, `customer_orders`, `idx_orders_customer_id`, `MW-88` | P3 Removable: `"Would you please"` |
| `case_04` | Numeric metrics review | `PROSE` (`DETECTED`) | P1 Semantic: `5 sections`, `150 words`, `Q4 2025` | P3 Removable: `"Please kindly"`, `"approximately"` |
| `case_05` | Milestone date schedule | `PROSE` (`DETECTED`) | P1 Semantic: `Phase-2`, `2026-01-15` | P3 Removable: `"Would you please"` |
| `case_06` | Python class implementation | `CODE_PYTHON` (`DETECTED`) | P1 Structural: Valid Python AST<br>P1 Lexical: `PaymentGatewayClient`, `MAX_RETRIES`, `process_payment`, `ValueError` | `allow_meaning_preserving_compression: False`, `allow_truncation: False` |
| `case_07` | JSON config payload | `JSON` (`DETECTED`) | P1 Structural: Valid JSON<br>P1 Lexical: `"cluster_id"`, `"node_count"`, `"auto_scaling"`, `"failover_endpoint"` | `allow_lossless_normalization: True`, `allow_truncation: False` |
| `case_08` | SLA availability table | `MARKDOWN_TABLE` (`DETECTED`)| P1 Structural: 5 matching columns, intact separator<br>P1 Lexical: `US-East`, `EU-Central`, `Breach`, `99.99%` | `allow_meaning_preserving_compression: False`, `allow_truncation: False` |
| `case_09` | RAG documents & SLA question | `PROSE` (`DETECTED`) | P1 Lexical: `[DOC-401]`, `[DOC-402]`, `[DOC-403]`, `/v2/telemetry`, `50,000 requests per minute`, `security-ops@acme.corp`, `15 minutes` | P2 Compressible: Non-citation prose |
| `case_10` | Repetitive spacing & token | `PROSE` (`DETECTED`) | P1 Lexical: `AUTH-TOKEN-XY99`, `enforce_strict_validation=true` | P3 Removable: Consecutive `\n\n\n\n`, `"Please kindly"` |
| `case_11` | Telemetry log + tail alert | `PROSE` (`DETECTED`) | P1 Lexical: `CRITICAL_ALERT_ASSERTION`, `KERN-ERR-0x89AB` | P2 Compressible: Diagnostic telemetry lines |
| `case_12` | Dense SQL query | `PROSE` (`DETECTED`) | P1 Lexical: `SELECT`, `order_id`, `orders`, `SHIPPED` | `allow_meaning_preserving_compression: False`, `allow_truncation: False` |

---

## 15. Architectural Risks & Mitigation Strategies [TARGET]

### Ranked Risk Matrix

| Rank | Architectural Risk | Description & Severity | Mitigation Strategy |
|:---:|---|---|---|
| **1** | **Character Offsets & Offset Drift** | Recording mutable character offsets causes stage mutations to invalidate subsequent offsets. | **Mitigation:** In MVP, map invariants and units at the **message-level and block-level** with `start_char` and `end_char` remaining `None`. No offset remapping engine needed. |
| **2** | **Structure Under-Classification & Ambiguity** | Malformed code or truncated JSON failing simple parsers and being mishandled as prose. | **Mitigation:** Explicit `DetectionCertainty.AMBIGUOUS` state triggering conservative protection fallback (no lossy mutations). |
| **3** | **Structure Over-Classification** | Trivial words like `"deploy"` or `"status"` parsing as valid Python expressions via `ast.parse()`. | **Mitigation:** Require language-specific structural cues (`def `, `class `, `import `, fences) before invoking AST parser validation. |
| **4** | **Entity Over-Classification** | Ordinary conversational numbers (e.g. "page 2") being locked down as immutable P1 numeric constraints. | **Mitigation:** Require qualifying units, percentages, or keywords for numeric constraint classification (e.g. `150 words`, `99.99%`). |
| **5** | **Execution Overhead** | Running parser trials on large contexts introducing latency. | **Mitigation:** Fast-path sentinel checks: only invoke AST or JSON parsers if sentinel characters (`` ``` ``, `{`, `def `) are present. Execute purely via deterministic Python libraries with zero external network or LLM dependencies. |
| **6** | **Semantic Equivalence Verification Gap** | Baseline evaluation checks only verify lexical presence and basic parse syntax, not semantic equivalence. | **Mitigation:** Explicitly document the limitation and treat semantic equivalence checking as future work; the first runtime validator focuses strictly on deterministic checks. |
| **7** | **Baseline Truncation Damage** | Truncation blindly slicing across structural boundaries and critical invariants. | **Mitigation:** Enforce `allow_truncation = False` across all units in `TransformationEligibility`. |

---

## 16. Implementation Sequence [TARGET]

The implementation of the Context Analyzer should proceed in five distinct, verifiable phases:

```
Phase 1: Data Model (`tokenopt/pipeline/preservation.py`)
  - Define PreservationClass, InvariantType, StructuralType, DetectionCertainty,
    EntityCategory, TransformationEligibility, ContextUnit (start_char/end_char = None),
    PreservationMap.
  - Add preservation_map attribute to OptimizationContext.
  - Zero behavioral changes; 166 existing tests pass.

Phase 2: Analyzer Stage (`tokenopt/pipeline/analyzer.py`)
  - Implement AnalyzerStage with deterministic structure and entity scanners.
  - Unit-test against the 12 evaluation cases in isolation.

Phase 3: Pipeline Integration (`tokenopt/clients/base.py`, `tokenopt/config.py`)
  - Add enable_analyzer config switch (default: True).
  - Insert AnalyzerStage as the first stage in BaseOptimizedClient._build_pipeline().
  - Verify all 166 existing tests pass with AnalyzerStage active.

Phase 4: Router Integration (`tokenopt/pipeline/router.py`)
  - Update RouterStage to inspect ctx.preservation_map for code/JSON structures.
  - Refine routing accuracy based on formal classification.

Phase 5: Closed-Loop Validation & Rollback (`tokenopt/pipeline/validator.py`)
  - Implement ValidatorStage focusing on deterministic gates: marker survival,
    role/message ordering, Python syntax, JSON syntax, table structure.
  - Enable automatic rollback on invariant or structural failure.
  - Document semantic equivalence checking as future work.
```
