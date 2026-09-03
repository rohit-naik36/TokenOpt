# TokenOpt

[![CI](https://github.com/rohit-naik36/TokenOpt/actions/workflows/ci.yml/badge.svg)](https://github.com/rohit-naik36/TokenOpt/actions/workflows/ci.yml)

TokenOpt is an enterprise AI token optimization platform and client SDK. It reduces LLM prompt size, latency, and cost through transparent compression, semantic caching, model routing, and quality-fidelity validation.

---

## Monorepo Architecture

This repository consolidates the TokenOpt product ecosystem into a unified monorepo:

| Folder | Component | Description |
| ------ | --------- | ----------- |
| [`tokenopt-proxy/`](tokenopt-proxy/) | **HTTP Enterprise Proxy** | Production FastAPI service (`v2.0`) with async embeddings, circuit breaker provider router, PostgreSQL audit trail, Redis cache, and Kafka event streamer. See [Proxy README](tokenopt-proxy/README.md). |
| [`tokenopt-optimizer/`](tokenopt-optimizer/) | **Optimizer Engine** | Standalone, embeddable `tokenopt_optimizer` engine with response fidelity validation, batch optimization, TTL LRU cache, and tokenizers. See [Optimizer README](tokenopt-optimizer/README.md). |
| [`tokenopt-sdk/`](tokenopt-sdk/) | **Client SDK (`v0.1.0`)** | Drop-in `tokenopt` client SDK for OpenAI, Anthropic, and local models (Ollama/vLLM/llama.cpp). See [SDK README](tokenopt-sdk/README.md). |

```
.
├── tokenopt-proxy/        # FastAPI HTTP Proxy service, Dockerfile, Terraform, & docs
├── tokenopt-optimizer/    # Standalone Python optimizer engine
└── tokenopt-sdk/          # Published client SDK (v0.1.0 snapshot) + .ai/ specs
```

---

## Quick Start — Proxy & Enterprise Platform

### Running the Proxy (Local)

```bash
cd tokenopt-proxy
pip install -r requirements.txt
set JWT_SECRET="demo-secret-key-for-presentation-only"
uvicorn tokenopt_proxy_v2:app --host 0.0.0.0 --port 8000
```

### Running the Demo Script

```bash
cd tokenopt-proxy
set JWT_SECRET="demo-secret-key-for-presentation-only"
python demo.py --no-llm
```

### Docker Build

```bash
cd tokenopt-proxy
docker build --build-context tokenopt_sdk=../tokenopt-optimizer -t tokenopt-proxy:latest .
```

---

## Quick Start — TokenOpt Client SDK (`v0.1.0`)

The SDK provides drop-in replacement wrappers for OpenAI and Anthropic clients:

```python
from tokenopt import OpenAI

# Drop-in replacement for standard OpenAI client
client = OpenAI()

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Explain quantum computing in simple terms..."}],
)
print(response.choices[0].message.content)
print("Metrics:", client.get_metrics_summary())
```

---

## Testing & Quality Assurance

Run the test suite for any component:

```bash
# Test the HTTP Proxy & Hardening Suite (82 tests)
cd tokenopt-proxy && python -m pytest tests/ -v

# Test the Standalone Optimizer Engine
cd tokenopt-optimizer && python -m pytest tests/ -v

# Test the Client SDK
cd tokenopt-sdk && python -m pytest tests/ -v
```

---

## License

[MIT](LICENSE)
