"""TokenOpt optimizer - standalone, embeddable prompt-optimization SDK.

Public API
----------
- :class:`PromptOptimizer`: the optimization orchestration entry point.
- :class:`OptimizerConfig`: tuning knobs for optimization behavior.
- :class:`SemanticCompressorV2`: deterministic compression engine.
- :class:`Message`: framework-agnostic chat message.
- :class:`FidelityScore`: result of a fidelity check.
- :class:`DegradedFidelityValidator`: fails-open validator (default backend).
- :class:`CacheBackend` / :class:`FidelityValidator`: pluggable protocols.

Usage
-----
.. code-block:: python

    from tokenopt_optimizer import PromptOptimizer, OptimizerConfig, Message

    async def example():
        opt = PromptOptimizer(config=OptimizerConfig(enable_headroom=False))
        result = await opt.optimize([
            Message(role="user", content="Please basically explain it to us"),
        ])
        print(result["optimized_prompt"])
"""

from .compressor import SemanticCompressorV2
from .fidelity import (
    DegradedFidelityValidator,
    FidelityScore,
    FidelityValidator,
)
from .messages import Message
from .optimizer import CacheBackend, OptimizerConfig, PromptOptimizer

__all__ = [
    "CacheBackend",
    "DegradedFidelityValidator",
    "FidelityScore",
    "FidelityValidator",
    "Message",
    "OptimizerConfig",
    "PromptOptimizer",
    "SemanticCompressorV2",
]

__version__ = "0.1.0"
