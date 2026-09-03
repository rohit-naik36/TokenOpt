# Architecture Knowledge Base — TokenOpt

> **Purpose.** The permanent architectural memory of TokenOpt: why the system
> is designed this way, how its components interact, which contracts must
> never be broken, and how contributors can safely extend it.
>
> **Audience.** Future maintainers, AI coding agents, contributors, and
> future Software Factory orchestration systems.
>
> **Scope.** Architecture and intent — not implementation detail. Where
> implementation specifics are cited, they are pointers into the code, not
> substitutes for reading it.
>
> **Status.** M14 milestone (2026-08-01). Documentation-only; no runtime
> code changed. Cross-checked against the committed implementation.

## Index

| Doc | Answers |
|-----|---------|
| [01 — System Overview](01_SYSTEM_OVERVIEW.md) | Why TokenOpt exists; its architectural, fail-open, optimization, and routing philosophies |
| [02 — Request Lifecycle](02_REQUEST_LIFECYCLE.md) | The complete flow of one call: caller → pipeline → provider → response → metrics → caller |
| [03 — Pipeline](03_PIPELINE.md) | Execution order, stage responsibilities, interactions, fail-open behavior, context lifecycle |
| [04 — Provider Layer](04_PROVIDER_LAYER.md) | The provider abstraction, the three providers, and the response-normalization contract |
| [05 — Configuration](05_CONFIGURATION.md) | Configuration hierarchy, defaults, overrides, validation, extension strategy |
| [06 — Metrics](06_METRICS.md) | Metrics ownership, propagation, `routing_reason`, `routing_precedence`, latency, cost, observability philosophy |
| [07 — Architectural Contracts](07_ARCHITECTURAL_CONTRACTS.md) | The guarantees that must never be broken, and why each exists |
| [08 — Extension Guide](08_EXTENSION_GUIDE.md) | How to safely add providers, pipeline stages, metrics, configuration, and optimization stages |
| [09 — Internal Assessment](09_INTERNAL_ASSESSMENT.md) | Software Factory perspective: reusable components, strengths, limitations, future opportunities, ADB-11..13 |

## How to read the KB

- **New to the system**: 01 → 02 → 03 → 04, then 07 (the contracts).
- **Contributing**: 08 first, then 07, then the topical docs for the area
  you touch.
- **Changing behavior**: read 07 before anything else. If a change touches
  a documented contract, it requires an architecture decision (approval
  gate per `AGENTS.md`).
- **AI agents / orchestration systems**: 07 and 09 are the normative
  sources; 01-06 are explanatory.

## Related sources

- `.ai/ARCHITECTURE.md` — compact architecture reference (kept in sync).
- `.ai/DECISIONS.md` — Decisions 1–25, the decision record behind the
  contracts.
- `.ai/ROUTING_PRECEDENCE_REVIEW.md` — review behind Decision 24.
- `.ai/M13_ARCHITECTURE_REVIEW.md` — M13 hotspot/assessment/debt report
  and the ADB-01..10 backlog.
- `README.md` — user-facing entry point.
