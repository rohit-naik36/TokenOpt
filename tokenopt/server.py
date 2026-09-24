"""FastAPI OpenAI-compatible gateway for TokenOpt Prototype v0.1.

This gateway accepts standard OpenAI chat completion payloads, routes them
through the canonical TokenOpt optimization pipeline (CP1-CP7), and returns
the provider response enriched with optimization telemetry in HTTP response headers.
"""

from __future__ import annotations

import time
import uuid
from typing import Any

from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from tokenopt import __version__
from tokenopt.config import TokenOptConfig, get_prototype_config
from tokenopt.factory import create_client


class ChatMessage(BaseModel):
    """OpenAI chat message schema."""

    role: str = Field(..., description="Role of the message author (system, user, assistant).")
    content: str | list[Any] = Field(..., description="Contents of the message.")
    name: str | None = Field(default=None, description="Optional name for participant.")

    model_config = {"extra": "allow"}


class ChatCompletionRequest(BaseModel):
    """OpenAI chat completion request schema."""

    model: str = Field(default="llama3.1", description="Target model name.")
    messages: list[ChatMessage] = Field(..., description="List of chat messages.")
    temperature: float | None = Field(default=None, description="Sampling temperature.")
    max_tokens: int | None = Field(default=None, description="Maximum tokens to generate.")
    top_p: float | None = Field(default=None, description="Nucleus sampling parameter.")
    stream: bool = Field(
        default=False, description="Streaming mode (unsupported in v0.1 prototype)."
    )

    model_config = {"extra": "allow"}


def create_app(config: TokenOptConfig | None = None) -> FastAPI:
    """Create and configure the TokenOpt FastAPI gateway application."""
    base_config = config or get_prototype_config()

    app = FastAPI(
        title="TokenOpt Optimization Gateway",
        description="Preservation-aware LLM token optimization gateway (Prototype v0.1)",
        version=__version__,
    )

    @app.get("/health")
    async def health_check() -> dict[str, str]:
        """Health and readiness probe."""
        return {
            "status": "healthy",
            "service": "tokenopt",
            "version": __version__,
        }

    @app.get("/v1/models")
    async def list_models() -> dict[str, Any]:
        """List supported models for OpenAI API compatibility."""
        return {
            "object": "list",
            "data": [
                {"id": "llama3.1", "object": "model", "owned_by": "ollama"},
                {"id": "gpt-4o", "object": "model", "owned_by": "openai"},
                {"id": "gpt-4o-mini", "object": "model", "owned_by": "openai"},
                {"id": "claude-3-5-sonnet", "object": "model", "owned_by": "anthropic"},
            ],
        }

    @app.post("/v1/chat/completions")
    async def chat_completions(req: ChatCompletionRequest) -> Response:
        """Execute OpenAI-compatible chat completion through TokenOpt pipeline."""
        if not req.messages:
            raise HTTPException(status_code=400, detail="Messages list cannot be empty.")

        # Convert pydantic models to standard dicts
        messages_dict = [m.model_dump(exclude_none=True) for m in req.messages]

        # Extra generation kwargs
        extra_kwargs: dict[str, Any] = {}
        if req.temperature is not None:
            extra_kwargs["temperature"] = req.temperature
        if req.max_tokens is not None:
            extra_kwargs["max_tokens"] = req.max_tokens
        if req.top_p is not None:
            extra_kwargs["top_p"] = req.top_p

        # Instantiate client with prototype-safe configuration
        try:
            client = create_client(model=req.model, config=base_config)
        except Exception as exc:
            raise HTTPException(
                status_code=400, detail=f"Failed to initialize provider client: {exc}"
            ) from exc

        # Execute through canonical pipeline and call provider
        try:
            response = client.chat.completions.create(
                messages=messages_dict,
                model=req.model,
                **extra_kwargs,
            )
        except Exception as exc:
            raise HTTPException(
                status_code=502, detail=f"LLM provider error: {exc}"
            ) from exc

        # Extract metrics recorded for this request
        recent = client.metrics_collector.get_recent(1)
        metrics = recent[0] if recent else None

        # Extract response text and usage
        content = client._extract_response_content(response)
        usage = client._extract_usage(response)

        # Standard OpenAI response structure
        finish_reason = "stop"
        if hasattr(response, "choices") and response.choices:
            choice = response.choices[0]
            finish_reason = getattr(choice, "finish_reason", "stop") or "stop"

        resp_body: dict[str, Any] = {
            "id": getattr(response, "id", f"chatcmpl-{uuid.uuid4().hex[:12]}"),
            "object": "chat.completion",
            "created": getattr(response, "created", int(time.time())),
            "model": metrics.model if metrics and metrics.model else req.model,
            "choices": [
                {
                    "index": 0,
                    "message": {
                        "role": "assistant",
                        "content": content,
                    },
                    "finish_reason": finish_reason,
                }
            ],
            "usage": {
                "prompt_tokens": usage.get(
                    "prompt_tokens", metrics.optimized_tokens if metrics else 0
                ),
                "completion_tokens": usage.get("completion_tokens", 0),
                "total_tokens": usage.get(
                    "total_tokens",
                    usage.get("prompt_tokens", 0) + usage.get("completion_tokens", 0),
                ),
            },
        }

        # Build telemetry headers
        headers: dict[str, str] = {}
        if metrics:
            headers["x-tokenopt-original-tokens"] = str(metrics.original_tokens)
            headers["x-tokenopt-optimized-tokens"] = str(metrics.optimized_tokens)
            headers["x-tokenopt-tokens-saved"] = str(metrics.tokens_saved)
            headers["x-tokenopt-reduction-pct"] = f"{metrics.reduction_percentage:.2f}"
            headers["x-tokenopt-pipeline-latency-ms"] = f"{metrics.pipeline_latency_ms:.2f}"
            headers["x-tokenopt-validation-decision"] = (
                metrics.validation_decision if metrics.validation_decision else "accept"
            )
            headers["x-tokenopt-rollback-applied"] = str(metrics.rollback_applied).lower()
            headers["x-tokenopt-model"] = metrics.model if metrics.model else req.model

        return JSONResponse(content=resp_body, headers=headers)

    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    uvicorn.run("tokenopt.server:app", host="0.0.0.0", port=8000, reload=False)
