"""Prompt compression for the TokenOpt optimizer SDK.

``SemanticCompressorV2`` implements deterministic, dependency-free compression
(filler removal, connector simplification, whitespace collapse) plus an
optional headroom integration that fails open.
"""

import re
from logging import getLogger
from typing import ClassVar

logger = getLogger("tokenopt.optimizer.compressor")

try:  # pragma: no cover - optional, import-guarded
    from headroom import CompressConfig as HeadroomConfig
    from headroom import compress as headroom_compress

    HEADROOM_AVAILABLE = True
except Exception:  # noqa: BLE001 - optional dependency missing (may raise non-ImportError)
    headroom_compress = None
    HeadroomConfig = None
    HEADROOM_AVAILABLE = False


class SemanticCompressorV2:
    """Enhanced semantic compressor: fillers, connectors, whitespace, and headroom."""

    FILLER_WORDS: ClassVar[set[str]] = {
        "basically", "essentially", "fundamentally", "literally",
        "actually", "really", "quite", "rather", "fairly", "pretty",
        "for the purpose of",
        "it is important to note that",
        "it should be noted that", "please note that", "kindly note",
    }

    def compress(self, text: str) -> tuple:
        """Deterministically compress *text*; returns ``(compressed, techniques)``."""
        techniques = []
        result = text

        count = 0
        for filler in self.FILLER_WORDS:
            pattern = r"\b" + re.escape(filler) + r"\b"
            matches = len(re.findall(pattern, result, re.IGNORECASE))
            if matches > 0:
                result = re.sub(pattern, "", result, flags=re.IGNORECASE)
                count += matches
        if count > 0:
            techniques.append(f"filler_removal:{count}")

        replacements = {
            r"\bin order to\b": "to",
            r"\bdue to the fact that\b": "because",
            r"\bin spite of the fact that\b": "although",
            r"\bin the event that\b": "if",
            r"\bat this point in time\b": "now",
            r"\bon a daily basis\b": "daily",
        }
        for pattern, replacement in replacements.items():
            result = re.sub(pattern, replacement, result, flags=re.IGNORECASE)

        result = re.sub(r"\s+", " ", result).strip()

        if result != text:
            techniques.append("semantic_compression")

        return result, techniques

    def safe_compress(self, text: str) -> str:
        """Very conservative compression: collapse whitespace / excess blank lines."""
        result = re.sub(r" +", " ", text)
        result = re.sub(r"\n{3,}", "\n\n", result)
        return result.strip()

    def compress_with_headroom(
        self,
        text: str,
        optimization_level: str = "standard",
        target_ratio: float = 0.5,
        min_tokens_to_compress: int = 100,
        llm_model: str = "gpt-4o",
    ) -> tuple:
        """Compress using the optional headroom SmartCrusher pipeline (fails open).

        Returns ``(compressed_text, techniques, stats)`` where stats carries the
        real token counts reported by headroom. On any failure returns the
        original text unchanged so the caller's fallback chain (fidelity ->
        safe_compress -> original) takes over.

        ``optimization_level`` tunes aggressiveness: "aggressive" keeps less,
        "conservative" keeps more, "standard" uses the configured ratio.
        """
        if not HEADROOM_AVAILABLE:
            return text, [], {}

        try:
            ratio = target_ratio
            if optimization_level == "aggressive":
                ratio = min(max(ratio * 0.5, 0.1), 0.95)
            elif optimization_level == "conservative":
                ratio = min(max(ratio * 1.5, 0.1), 0.95)

            config = HeadroomConfig(
                compress_user_messages=True,
                compress_system_messages=False,
                protect_recent=0,
                min_tokens_to_compress=max(int(min_tokens_to_compress), 10),
                target_ratio=ratio,
                kompress_model="disabled",
            )
            result = headroom_compress(
                [{"role": "user", "content": text}],
                model=llm_model,
                config=config,
            )

            if not result.messages:
                return text, [], {}

            compressed = result.messages[0].get("content", text)
            if not isinstance(compressed, str) or compressed == text:
                return text, [], {}

            transforms = list(result.transforms_applied or [])
            if result.tokens_saved <= 0:
                return text, [], {}

            techniques = [f"headroom:{t}" for t in transforms] or ["headroom:smart_crusher"]
            stats = {
                "tokens_before": result.tokens_before,
                "tokens_after": result.tokens_after,
                "tokens_saved": result.tokens_saved,
                "compression_ratio": result.compression_ratio,
            }
            return compressed, techniques, stats
        except Exception as e:  # noqa: BLE001 - fallback must never raise
            logger.warning(f"Headroom compression failed, falling back: {e}")
            return text, [], {}
