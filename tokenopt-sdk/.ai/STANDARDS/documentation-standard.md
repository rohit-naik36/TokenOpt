# Documentation Standard

_Standard owner: `.ai/ROLES/technical-writer.md`_
_Related: `.ai/PROJECT_MANIFEST.md` §4, §9_

## Scope

All documentation: code docstrings, `README.md`, `.ai/` memory, changelog.

## Rules

1. **Docstrings** — every module, public class, and public function has a
   docstring. First line: one-sentence summary; body: behavior, params,
   returns, raised errors where relevant.
2. **Update with code** — documentation changes land in the **same commit**
   as the code they describe. A PR that changes behavior without touching docs
   fails review.
3. **README.md** — the user entry point. Covers: install, quick start,
   configuration reference, providers, development, links to `.ai/`.
4. **`.ai/` memory** — always current: `CURRENT_STATE.md` (what exists),
   `NEXT_STEPS.md` (what's next), `SESSION_LOG.md` (what happened),
   `DECISIONS.md` (why — append-only), `ROADMAP.md`, `ARCHITECTURE.md`.
5. **"Last updated" line** — every `.ai/` document carries
   `_Last updated: YYYY-MM-DD_`.
6. **Markdown** — CommonMark; headings `#` `##` `###`; tables for structured
   data; fenced code blocks with language tags.
7. **Append-only assets** — never delete documentation; deprecate by marking
   archived (e.g. `_Archived: YYYY-MM-DD_`).
8. **Changelog** — user-visible changes recorded in `CHANGELOG.md` under the
   next version (see `.ai/STANDARDS/release-standard.md`).
9. **Diagrams** — Mermaid for architecture flows; ASCII only where rendering
   is unavailable.
10. **Language** — professional, concise, imperative where instructing agents.

## Verification

- Diff review checks: docs updated in the same commit as behavior changes.
- `README.md` install/quick-start commands are executed before release (M6/M15).
- `.ai/` freshness is checked at every checkpoint and session close.

## Responsibilities by document

| Document | Updates when | Author |
|----------|--------------|--------|
| `CURRENT_STATE.md` | any completed/in-flight work | agent |
| `SESSION_LOG.md` | every session/milestone | agent |
| `NEXT_STEPS.md` | scope or state changes | agent |
| `DECISIONS.md` | new accepted decision | agent (user approval) |
| `ROADMAP.md` | scope/phasing changes | agent |
| `ARCHITECTURE.md` | structure/flow changes | agent |
| `README.md` | user-facing behavior changes | agent |
