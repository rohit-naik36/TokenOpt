# TokenOpt v2.0 - Production image
# Uses a BuildKit multi-context build so the SDK stays in its own, separate repo:
#   docker build --build-context tokenopt_sdk=../../tokenopt-optimizer -t tokenopt:latest .
# The optional ML/infra dependencies (sentence-transformers, asyncpg, redis,
# aiokafka, headroom) degrade gracefully when absent, so only the core runtime
# packages are installed by default.

FROM python:3.11-slim AS builder

WORKDIR /build
COPY requirements.txt .
# Core packages are installed --no-deps for the runtime stage below.
RUN pip install --no-cache-dir \
        "fastapi>=0.110.0,<1.0.0" \
        "uvicorn[standard]>=0.24.0,<1.0.0" \
        "pydantic>=2.0.0,<3.0.0" \
        "httpx>=0.24.0,<1.0.0" \
        "PyJWT>=2.8.0,<3.0.0" \
        "numpy>=1.24.0,<3.0.0" \
        "openai>=1.30.0,<2.0.0"

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HOST=0.0.0.0 \
    PORT=8000

WORKDIR /app

# Copy the installed core packages from the builder stage
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source (flat layout)
COPY tokenopt_proxy_v2.py provider_client_v2.py persistence_layer_v2.py fidelity_validator_v2.py ./

# Copy the tokenopt_optimizer SDK from its own build context (separate repo)
COPY --from=tokenopt_sdk tokenopt_optimizer/ ./tokenopt_optimizer/

# Non-root runtime user
RUN useradd --create-home --uid 10001 appuser
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8000/health', timeout=5).status==200 else 1)" || exit 1

CMD ["sh", "-c", "uvicorn tokenopt_proxy_v2:app --host ${HOST} --port ${PORT} --workers 1"]
