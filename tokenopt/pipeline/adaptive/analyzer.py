"""Segment analysis for adaptive compression."""

from __future__ import annotations

import re

from tokenopt.pipeline.adaptive.contracts import CompressionProfile
from tokenopt.utils.token_counter import count_tokens

FILLER_WORDS_REGEX = re.compile(
    r'\b(?:please|kindly|would you|could you|I think|I believe|basically)\b',
    re.IGNORECASE
)


class Analyzer:
    """Analyzes text segments to generate a CompressionProfile."""

    def analyze(
        self,
        text: str,
        role: str,
        segment_id: str,
        is_last_user_query: bool = False,
        model: str = "gpt-4o",
    ) -> CompressionProfile:
        token_count = count_tokens(text, model)

        signals = {}
        flags = []

        # 1. Structural Data Signal
        # JSON, XML-like tags, simple tables
        if re.search(r'[\{\}\[\]\<\>]', text) or re.search(r'\|.*\|.*\|', text):
            signals["structural_data"] = 1.0
            flags.append("CONTAINS_STRUCTURED_DATA")
        else:
            signals["structural_data"] = 0.0

        # 2. Code Block Signal
        if "```" in text:
            signals["code_block"] = 1.0
            flags.append("CONTAINS_CODE")
        else:
            signals["code_block"] = 0.0

        # 3. Positional Signal
        if role == "system":
            signals["positional"] = 1.0
            flags.append("IS_SYSTEM_PROMPT")
        elif is_last_user_query:
            signals["positional"] = 1.0
            flags.append("IS_LAST_USER_QUERY")
        else:
            signals["positional"] = 0.0

        # 4. Whitespace Signal
        total_chars = max(len(text), 1)
        whitespace_chars = sum(1 for c in text if c.isspace())
        signals["whitespace_ratio"] = whitespace_chars / total_chars

        # 5. Conversational Filler Signal
        fillers = len(FILLER_WORDS_REGEX.findall(text))
        signals["conversational_fillers"] = min(fillers / max(token_count, 1) * 10, 1.0)

        # Risk Score (MAX of high-risk signals)
        risk_score = max(signals["structural_data"], signals["code_block"], signals["positional"])

        # Compressibility Score
        compressibility = min(
            (signals["whitespace_ratio"] * 0.5)
            + (signals["conversational_fillers"] * 0.5)
            + (1.0 - risk_score),
            1.0,
        )

        return CompressionProfile(
            segment_id=segment_id,
            role=role,
            token_count=token_count,
            risk_score=float(risk_score),
            compressibility=float(compressibility),
            signals=signals,
            preservation_flags=flags,
        )
