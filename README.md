# TokenOpt Monorepo

This repository consolidates the three TokenOpt products into a single monorepo:

| Folder | Product | Description |
| ------ | ------- | ----------- |
| [`tokenopt-sdk/`](tokenopt-sdk/) | **Published SDK** | Drop-in `tokenopt` client SDK (OpenAI / Anthropic / local) — snapshot of the released `v0.1.0`. See its [README](tokenopt-sdk/README.md). |
| [`tokenopt-optimizer/`](tokenopt-optimizer/) | **Optimizer engine** | Standalone, embeddable `tokenopt_optimizer` engine with response fidelity, batch optimization, TTL LRU cache, tokenizer. See its [README](tokenopt-optimizer/README.md). |
| [`tokenopt-proxy/`](tokenopt-proxy/) | **HTTP service** | v2 FastAPI proxy that wraps the optimizer SDK and exposes it over HTTP. See its [README](tokenopt-proxy/README.md). |

## Layout

```
.
├── tokenopt-sdk/          published tokenopt client SDK (v0.1.0 snapshot)
├── tokenopt-optimizer/    embeddable optimizer engine (Python package)
└── tokenopt-proxy/        FastAPI HTTP service (depends on ../tokenopt-optimizer)
```

- The optimizer engine is a sibling of the proxy and is installed via a relative
  editable path (`-e ../tokenopt-optimizer`, see `tokenopt-proxy/requirements.txt`).
- The proxy Docker build uses a multi-context build
  (`--build-context tokenopt_sdk=../tokenopt-optimizer`, see `tokenopt-proxy/Dockerfile`).

## Development

Run tests for each subproject from its own folder:

```bash
cd tokenopt-optimizer && pytest
cd tokenopt-proxy      && pytest   # after: pip install -r requirements.txt
```

The published SDK (`tokenopt-sdk/`) is a copy of the `v0.1.0` release. The
original `main` branch history, the `v0.1.0` tag, and the open PRs on
`origin/main` remain untouched; `tokenopt-sdk/` is provided for reference.
