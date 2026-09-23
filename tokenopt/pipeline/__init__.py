"""Pipeline stages for TokenOpt optimization."""

from tokenopt.pipeline.analyzer import AnalyzerStage, ContextAnalyzer
from tokenopt.pipeline.base import OptimizationContext, OptimizationPipeline, PipelineStage
from tokenopt.pipeline.cache import CacheStage
from tokenopt.pipeline.compressor import CompressorStage, ContextSummarizerStage
from tokenopt.pipeline.fewshot import FewShotSelectorStage
from tokenopt.pipeline.preservation import (
    ContextUnit,
    DetectionCertainty,
    EntityCategory,
    InvariantType,
    PreservationClass,
    PreservationMap,
    PreservedInvariant,
    StructuralType,
    TransformationEligibility,
)
from tokenopt.pipeline.rag_optimizer import RAGOptimizerStage
from tokenopt.pipeline.router import RouterStage

__all__ = [
    "OptimizationContext",
    "OptimizationPipeline",
    "PipelineStage",
    "AnalyzerStage",
    "ContextAnalyzer",
    "CompressorStage",
    "ContextSummarizerStage",
    "CacheStage",
    "RouterStage",
    "RAGOptimizerStage",
    "FewShotSelectorStage",
    "PreservationClass",
    "InvariantType",
    "StructuralType",
    "DetectionCertainty",
    "EntityCategory",
    "PreservedInvariant",
    "TransformationEligibility",
    "ContextUnit",
    "PreservationMap",
]
