"""Preservation-aware transformation stage for TokenOpt.

This module implements the Preservation-Aware Transformation Stage as specified
in Checkpoint 7 of the TokenOpt context preservation architecture.

Architectural invariants:
    1. "The transformer executes only the transformation decisions produced by
       the Candidate Planner. It does not independently decide what is safe to
       transform."
    2. "Transformation eligibility is strictly limited to:
       CandidateDecision == COMPRESS and preservation_class == P2_COMPRESSIBLE
       and structural_type == PROSE."
    3. "P0, P1, and structured content (Python, JSON, Markdown tables, tool payloads)
       are completely protected and pass through untouched."
    4. "Unsafe BPE truncation (truncate_to_tokens) is completely eliminated."
    5. "Local preflight assertions verify invariant retention before output emission.
       Ambiguous or failing units fall back to original content without retries."
"""

from __future__ import annotations

import re
import time
from typing import Any

from tokenopt.config import TokenOptConfig
from tokenopt.pipeline.base import OptimizationContext, PipelineStage
from tokenopt.pipeline.planner import (
    CandidatePlan,
    CandidatePlanner,
    CandidateType,
)
from tokenopt.pipeline.preservation import (
    PreservationClass,
    StructuralType,
)
from tokenopt.utils.token_counter import count_message_tokens

# =============================================================================
# Catalogs and Regex Patterns
# =============================================================================

CERTIFIED_INLINE_FILLER_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\b(?:as a matter of fact|at the end of the day)\b\s*", re.IGNORECASE),
    re.compile(r"\b(?:could you|would you)\b\s*", re.IGNORECASE),
    re.compile(r"\b(?:basically|essentially|fundamentally)\b\s*", re.IGNORECASE),
    re.compile(r"\b(?:please|kindly)\b\s*", re.IGNORECASE),
)

DIRECTIVE_KEYWORDS_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:must|shall|required|ensure|verify|do not|never|always|"
    r"select|return|restrict|enforce|before|after|only|except|critical|alert)\b",
    re.IGNORECASE,
)

CERTIFIED_REDUNDANT_SENTENCE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"^(?:please\s+)?(?:kindly\s+)?(?:let me know if you need (?:any|further) "
        r"(?:help|assistance)|hope this helps|thank you(?:\s+very much)?|"
        r"thanks|best regards|have a (?:great|good) day)[.!]?$",
        re.IGNORECASE,
    ),
    re.compile(
        r"^(?:understood|acknowledged|confirmed|noted|i will do that)[.!]?$",
        re.IGNORECASE,
    ),
)


# =============================================================================
# Helper Functions for CP7 Prose Transformation
# =============================================================================

def _has_embedded_structured_content(text: str) -> bool:
    """Detect if prose message contains embedded code fences or markdown table structure."""
    if "```" in text:
        return True
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    table_lines = [line for line in lines if line.startswith("|") and line.endswith("|")]
    if len(table_lines) >= 2:
        for line in table_lines[1:2]:
            cells = line[1:-1].split("|")
            if cells and all(re.match(r"^:?-+:?$", c.strip()) for c in cells):
                return True
    return False


def _find_protected_spans(text: str, invariants: list[str]) -> list[tuple[int, int]]:
    """Identify character spans where sentence boundary splitting is prohibited."""
    spans: list[tuple[int, int]] = []

    # 1. Exact Invariant Markers
    for inv in invariants:
        if not inv:
            continue
        start = 0
        while True:
            idx = text.find(inv, start)
            if idx == -1:
                break
            spans.append((idx, idx + len(inv)))
            start = idx + len(inv)

    # 2. URLs / URIs (https:// or http://) - exclude trailing sentence punctuation
    for m in re.finditer(r"https?://[^\s)]+", text):
        url = m.group(0).rstrip(".,;:!?")
        spans.append((m.start(), m.start() + len(url)))

    # 3. Email addresses and technical identifiers (domain cannot end with punctuation)
    for m in re.finditer(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)+", text):
        spans.append((m.start(), m.end()))

    # 4. Decimals and percentages (e.g., 22.4%, 1.2 Gbps, 3.14159)
    for m in re.finditer(r"\b\d+\.\d+(?:%|[a-zA-Z]+)?\b", text):
        spans.append((m.start(), m.end()))

    # 5. Version identifiers (e.g., v4.2, 16.0.1, 1.2.0)
    for m in re.finditer(r"\bv?\d+(?:\.\d+)+(?:-[a-zA-Z0-9]+)?\b", text):
        spans.append((m.start(), m.end()))

    # 6. Technical abbreviations (e.g., e.g., i.e., etc., vs., etc.)
    for m in re.finditer(
        r"\b(?:e\.g\.|i\.e\.|etc\.|vs\.|fig\.|ref\.|approx\.|dept\.)\b",
        text,
        re.IGNORECASE,
    ):
        spans.append((m.start(), m.end()))

    # 7. File paths and API endpoints (e.g., /v2/telemetry, /api/v1)
    for m in re.finditer(r"(?:/[a-zA-Z0-9_.-]+)+/?", text):
        spans.append((m.start(), m.end()))

    # 8. Domain names / FQDNs
    for m in re.finditer(r"\b[a-zA-Z0-9_-]+\.[a-zA-Z]{2,}(?:/[^\s]*)?\b", text):
        spans.append((m.start(), m.end()))

    return spans


def _normalize_whitespace(text: str, invariants: list[str]) -> str:
    """Conservatively collapse excessive whitespace runs if safe for invariants."""
    for inv in invariants:
        if re.search(r"\n{3,}|[ \t]{2,}", inv):
            return text

    normalized = re.sub(r"\n{3,}", "\n\n", text)
    normalized = re.sub(r"[ \t]{2,}", " ", normalized)
    return normalized


def _strip_inline_filler(text: str, invariants: list[str]) -> str:
    """Remove certified inline conversational filler words where safe."""
    for pattern in CERTIFIED_INLINE_FILLER_PATTERNS:
        protected_spans = _find_protected_spans(text, invariants)
        matches = list(pattern.finditer(text))
        for m in reversed(matches):
            m_start, m_end = m.start(), m.end()
            overlaps = any(
                not (m_end <= p_start or m_start >= p_end)
                for p_start, p_end in protected_spans
            )
            if not overlaps:
                candidate = text[:m_start] + text[m_end:]
                if candidate.strip() and all(inv in candidate for inv in invariants):
                    text = candidate

    text = re.sub(r"[ \t]{2,}", " ", text)
    return text


def _split_sentences(text: str, invariants: list[str]) -> list[tuple[str, str]]:
    """Conservative two-phase sentence boundary scanner returning (sentence, delimiter) pairs."""
    protected_spans = _find_protected_spans(text, invariants)

    boundary_pattern = re.compile(
        r"([.!?])([\s\n]+)(?=[A-Z0-9\"'\[])|(\n{2,})(?=[A-Z0-9\"'\[])"
    )

    split_points: list[tuple[int, int]] = []

    for m in boundary_pattern.finditer(text):
        if m.group(1):
            punc_idx = m.start(1)
            is_protected = any(
                p_start <= punc_idx < p_end
                for p_start, p_end in protected_spans
            )
            if not is_protected:
                split_points.append((m.end(1), m.end()))
        elif m.group(3):
            break_idx = m.start(3)
            is_protected = any(
                p_start <= break_idx < p_end
                for p_start, p_end in protected_spans
            )
            if not is_protected:
                split_points.append((break_idx, m.end()))

    if not split_points:
        return [(text, "")]

    sentences: list[tuple[str, str]] = []
    prev_idx = 0
    for split_start, split_end in split_points:
        sent = text[prev_idx:split_start]
        delim = text[split_start:split_end]
        sentences.append((sent, delim))
        prev_idx = split_end

    if prev_idx < len(text):
        sentences.append((text[prev_idx:], ""))

    return sentences


def _prune_sentences(
    sentence_pairs: list[tuple[str, str]],
    invariants: list[str],
) -> tuple[list[tuple[str, str]], int]:
    """Prune exact duplicate sentences and certified redundant filler sentences."""
    kept: list[tuple[str, str]] = []
    seen_exact: set[str] = set()
    pruned_count = 0

    for sent, delim in sentence_pairs:
        s_clean = sent.strip()
        if not s_clean:
            continue

        # 1. Exact duplicate sentence detection
        if s_clean in seen_exact:
            has_inv = any(inv in sent for inv in invariants)
            if not has_inv:
                pruned_count += 1
                continue
        seen_exact.add(s_clean)

        # 2. Invariant check: if sentence contains invariant, strictly preserve
        if any(inv in sent for inv in invariants):
            kept.append((sent, delim))
            continue

        # 3. Directive keyword check: if sentence contains directive, strictly preserve
        if DIRECTIVE_KEYWORDS_PATTERN.search(sent):
            kept.append((sent, delim))
            continue

        # 4. Certified redundant filler sentence check
        if any(p.match(s_clean) for p in CERTIFIED_REDUNDANT_SENTENCE_PATTERNS):
            pruned_count += 1
            continue

        # 5. Ambiguity default: strictly preserve
        kept.append((sent, delim))

    return kept, pruned_count


# =============================================================================
# TransformerStage Implementation
# =============================================================================

class TransformerStage(PipelineStage):
    """Apply CandidatePlan transformation decisions to the message list.

    This stage enforces the preservation contract by executing only the
    transformations authorized by the CandidatePlanner. It does not
    independently decide what is safe to transform.

    Transformation rules (applied per message index):
        P0 / P1 → always protected → pass through unchanged
        P2 COMPRESS candidate (PROSE) → execute deterministic prose transformation
        P2 non-PROSE / protected → pass through unchanged
        P3 REMOVE candidate → omit from output
        P3 protected → pass through unchanged
        Unknown / no plan entry → fail-safe → pass through unchanged
    """

    name = "transformer"

    def __init__(self, config: TokenOptConfig | None = None) -> None:
        super().__init__(config)
        self.config: TokenOptConfig = config or TokenOptConfig()
        self._planner = CandidatePlanner(config=self.config)

    def process(self, ctx: OptimizationContext) -> OptimizationContext:
        """Execute CandidatePlan decisions against the message list."""
        t0 = time.perf_counter()

        if ctx.preservation_map is None:
            ctx.metrics["transformer_skipped"] = "no_preservation_map"
            ctx.metadata["surviving_indices"] = list(range(len(ctx.messages)))
            ctx.metrics["transformer_latency_ms"] = (time.perf_counter() - t0) * 1000
            return ctx

        plan: CandidatePlan = self._planner.plan(ctx.preservation_map)

        transformed: list[dict[str, Any]] = []
        surviving_indices: list[int] = []

        compress_count = 0
        remove_count = 0
        protected_count = 0

        p2_prose_evaluated = 0
        p2_prose_transformed = 0
        p2_prose_unchanged = 0
        sentences_pruned = 0
        transform_fallbacks = 0

        for idx, msg in enumerate(ctx.messages):
            candidate = plan.get_candidate_for_message(idx)

            if candidate is None:
                # No plan entry: protected by fail-safe.
                transformed.append(msg)
                surviving_indices.append(idx)
                protected_count += 1
                continue

            if candidate.candidate_type == CandidateType.REMOVE:
                # Omit the message — do not append it to output.
                remove_count += 1

            elif candidate.candidate_type == CandidateType.COMPRESS:
                # Strictly enforce eligibility: P2_COMPRESSIBLE and PROSE
                if (
                    candidate.preservation_class == PreservationClass.P2_COMPRESSIBLE
                    and candidate.unit.structural_type == StructuralType.PROSE
                ):
                    p2_prose_evaluated += 1

                    # Collect expected invariants for this unit
                    invariants = [inv.marker for inv in candidate.unit.invariants]
                    if ctx.preservation_map:
                        for inv in ctx.preservation_map.invariants:
                            if inv.message_index == idx and inv.marker not in invariants:
                                invariants.append(inv.marker)

                    transformed_msg, was_modified, pruned_count, fallback_occurred = (
                        self._transform_prose_message(msg, invariants)
                    )

                    sentences_pruned += pruned_count
                    if fallback_occurred:
                        transform_fallbacks += 1

                    if was_modified:
                        p2_prose_transformed += 1
                        compress_count += 1
                    else:
                        p2_prose_unchanged += 1
                        compress_count += 1  # Planned compress executed

                    transformed.append(transformed_msg)
                    surviving_indices.append(idx)
                else:
                    # P0, P1, or structured content: strictly protected
                    transformed.append(msg)
                    surviving_indices.append(idx)
                    protected_count += 1

            else:
                # Defensive fallback for any unknown future CandidateType
                transformed.append(msg)
                surviving_indices.append(idx)
                protected_count += 1

        ctx.messages = transformed
        ctx.metadata["surviving_indices"] = surviving_indices

        # Record metrics
        t1 = time.perf_counter()
        ctx.metrics["transformer_applied"] = True
        ctx.metrics["compression_applied"] = True
        ctx.metrics["transformer_compress_count"] = compress_count
        ctx.metrics["transformer_remove_count"] = remove_count
        ctx.metrics["transformer_protected_count"] = protected_count
        ctx.metrics["transformer_plan_candidates"] = len(plan.candidates)
        ctx.metrics["transformer_plan_protected"] = len(plan.protected_units)

        ctx.metrics["p2_prose_messages_evaluated"] = p2_prose_evaluated
        ctx.metrics["p2_prose_messages_transformed"] = p2_prose_transformed
        ctx.metrics["p2_prose_messages_unchanged"] = p2_prose_unchanged
        ctx.metrics["sentences_pruned_count"] = sentences_pruned
        ctx.metrics["transform_fallback_count"] = transform_fallbacks
        ctx.metrics["transformer_latency_ms"] = (t1 - t0) * 1000

        # Calculate attempted tokens saved
        final_tokens = count_message_tokens(ctx.messages, ctx.model)
        ctx.metrics["attempted_tokens_saved"] = max(
            0, ctx.original_token_count - final_tokens
        )

        return ctx

    def _transform_prose_message(
        self,
        msg: dict[str, Any],
        expected_invariants: list[str],
    ) -> tuple[dict[str, Any], bool, int, bool]:
        """Apply deterministic CP7 prose transformation to a single message.

        Returns:
            (result_msg, was_modified, sentences_pruned, fallback_occurred)
        """
        content = msg.get("content", "")
        if not isinstance(content, str) or not content.strip():
            return msg, False, 0, False

        # Structural content protection: embedded code fences or tables
        if _has_embedded_structured_content(content):
            return msg, False, 0, False

        # Verify that all expected invariants exist in the original content
        for marker in expected_invariants:
            if marker not in content:
                return msg, False, 0, True

        # 1. Whitespace normalization
        normalized = _normalize_whitespace(content, expected_invariants)

        # 2. Inline filler stripping
        filler_stripped = _strip_inline_filler(normalized, expected_invariants)

        # 3. Sentence segmentation and pruning
        sentence_pairs = _split_sentences(filler_stripped, expected_invariants)
        kept_pairs, pruned_count = _prune_sentences(sentence_pairs, expected_invariants)

        if not kept_pairs:
            candidate_content = filler_stripped.strip() or content.strip()
            pruned_count = 0
        else:
            candidate_content = "".join(sent + delim for sent, delim in kept_pairs).strip()

        # 4. Local preflight assertion
        if not self._local_preflight(content, candidate_content, expected_invariants):
            return msg, False, 0, True

        was_modified = candidate_content != content
        if was_modified:
            return {**msg, "content": candidate_content}, True, pruned_count, False
        return msg, False, 0, False

    def _local_preflight(
        self,
        original_content: str,
        candidate_content: str,
        expected_invariants: list[str],
    ) -> bool:
        """Verify transformation integrity preconditions locally before emission."""
        if original_content.strip() and not candidate_content.strip():
            return False
        for marker in expected_invariants:
            if marker not in candidate_content:
                return False
        return True

    @property
    def planner(self) -> CandidatePlanner:
        """Expose the internal planner for introspection in tests."""
        return self._planner
