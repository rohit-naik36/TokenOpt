"""Structured logging for TokenOpt."""

from __future__ import annotations

import json
import logging
import sys
from typing import Any

from tokenopt.observability.metrics import RequestMetrics


class StructuredLogger:
    """Structured JSON logger for TokenOpt events."""

    def __init__(self, name: str = "tokenopt", level: int = logging.INFO):
        self.logger = logging.getLogger(name)
        self.logger.setLevel(level)

        if not self.logger.handlers:
            handler = logging.StreamHandler(sys.stdout)
            handler.setFormatter(JsonFormatter())
            self.logger.addHandler(handler)

    def log_request(self, metrics: RequestMetrics) -> None:
        """Log request completion."""
        self.logger.info("request_completed", extra={
            "event": "request_completed",
            "model": metrics.model,
            "original_tokens": metrics.original_tokens,
            "optimized_tokens": metrics.optimized_tokens,
            "output_tokens": metrics.output_tokens,
            "cache_hit": metrics.cache_hit,
            "compression_applied": metrics.compression_applied,
            "compression_attempted": metrics.compression_attempted,
            "compression_effective": metrics.compression_effective,
            "tokens_saved": metrics.tokens_saved,
            "reduction_percentage": metrics.reduction_percentage,
            "summarization_applied": metrics.summarization_applied,
            "routing_applied": metrics.routing_applied,
            "rag_optimization_applied": metrics.rag_optimization_applied,
            "fewshot_applied": metrics.fewshot_applied,
            "latency_ms": metrics.latency_ms,
            "pipeline_latency_ms": metrics.pipeline_latency_ms,
            "model_latency_ms": metrics.model_latency_ms,
            "estimated_cost": metrics.estimated_cost,
            "error": metrics.error,
        })

    def log_optimization(self, stage: str, details: dict[str, Any]) -> None:
        """Log optimization stage execution."""
        self.logger.debug("optimization_stage", extra={
            "event": "optimization_stage",
            "stage": stage,
            **details,
        })

    def log_cache(self, action: str, details: dict[str, Any]) -> None:
        """Log cache operations."""
        self.logger.debug("cache_operation", extra={
            "event": "cache_operation",
            "action": action,
            **details,
        })

    def log_routing(self, from_model: str, to_model: str, reason: str) -> None:
        """Log model routing decision."""
        self.logger.info("model_routing", extra={
            "event": "model_routing",
            "from_model": from_model,
            "to_model": to_model,
            "reason": reason,
        })


class JsonFormatter(logging.Formatter):
    """JSON log formatter."""

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record),
            "level": record.levelname,
            "logger": record.name,
        }

        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in ["name", "msg", "args", "created", "filename", "funcName",
                           "levelname", "levelno", "lineno", "module", "msecs",
                           "message", "name", "pathname", "process", "processName",
                           "relativeCreated", "thread", "threadName", "exc_info",
                           "exc_text", "stack_info"]:
                log_data[key] = value

        if record.exc_info:
            log_data["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_data, default=str)


def get_logger(name: str = "tokenopt") -> StructuredLogger:
    """Get a structured logger instance."""
    return StructuredLogger(name)
