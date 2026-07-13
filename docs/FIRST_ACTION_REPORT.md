# First-Action Report

> **⚠ SUPERSEDED (2026-07-13).** This report predates the operator's locked decisions of 2026-07-13. Several items here are now out of date:
> - Docker, FastAPI, and the DEBUG-gated SSE / separated frontend are **locked into the architecture** (not "deferred/optional"); ordering is core-first — the MIVE core must be independently testable *before* full-stack Docker integration is declared complete.
> - Vector store is **locked to Qdrant** (not "Claude Code picks the smallest").
> - Budget is set: **USD 10 total / USD 1 live without approval**.
> - The **20 representative questions are provided**; Question 1 is the first live test.
> - The §D "blocking ambiguities" (interim Streamlit, budget, model/vector confirmation) are **resolved** — there is no interim Streamlit; the end-state UI is the containerized frontend.
>
> Current authoritative documents: `docs/OPERATOR_CHECKLIST.md`, `docs/PHASE_PLAN.md`, `docs/ARCHITECTURE_DECISIONS.md`, `docs/MODEL_AND_PRICING_REGISTER.md`, `docs/CORPUS_REGISTER.md`, `docs/RESEARCH_LOG.md`. Retained below for history only.

---

## A. UNDERSTANDING

ION MIVE Lab is a controlled local research product. One public boundary:

```python
ask(question: str, top_k: int = 5) -> Result
```

Pipeline: question → retrieval from the corpus → one canonical Context Pack → **independent** Gemini IVE and OpenAI IVE (neither sees the other) → normalize both into the canonical IVE schema → MIVE comparison → human-readable result with evidence, uncertainty, latency, token use, and estimated cost. Core epistemic invariants hold throughout: intelligence ≠ truth, evidence over confidence, disagreement is information, a one-provider fallback is not a MIVE success.

**Sequencing (reconciled with locked decisions 7 & 8):** the target end-state — frontend/backend split, core+modules, REST, DEBUG-gated SSE, Docker — described in `docs/14`–`docs/17` remains the destination, but it is delivered **after** a working local Python core. v0.1 is a local, in-process `ask()` proven with mocked tests and one controlled live question. No Docker, FastAPI, SSE, or frontend is a prerequisite for Phase 1.

## B. CORPUS INVENTORY

Location: `corpus/source/`. 9 files, **0 duplicates** (all MD5 checksums unique), all text-extractable (**no OCR required**).

| # | File | Type | Size | Pages | Extraction |
|---|------|------|------|-------|-----------|
| 1 | Broken_Money.txt | TXT (UTF-8) | 837 KB | — (~137,785 words) | TEXT-OK |
| 2 | The Value of a Whale.txt | TXT (UTF-8) | 496 KB | — (~76,815 words) | TEXT-OK |
| 3 | Layered Money.txt | TXT (UTF-8) | 201 KB | — (~32,721 words) | TEXT-OK |
| 4 | Rebuild-ELY.pdf | PDF 1.5 | 16.5 MB | 512 | TEXT-OK |
| 5 | DebunkingEconomics.pdf | PDF 1.7 | 5.0 MB | 498 | TEXT-OK |
| 6 | ErgodicInvester.pdf | PDF 1.5 | 4.1 MB | 184 | TEXT-OK |
| 7 | sacred-economics-book-text.pdf | PDF 1.3 | 1.7 MB | 314 | TEXT-OK |
| 8 | Finite-and-Infinite-Games-by-James-Carse.pdf | PDF 1.4 | 7.6 MB | 160 | TEXT-OK (sparse front matter) |
| 9 | Field_Investing.pdf | PDF 1.4 | 1.3 MB | 14 | TEXT-OK |

Totals: 3 TXT + 6 PDF; ~1,682 PDF pages plus ~247k words of TXT. All in scope for first clean ingestion per locked decision #2.

Notes: `Field_Investing.pdf` reports 14 pages via pypdf (the OS `file` header said 8 — pypdf is authoritative). `Finite-and-Infinite-Games` has sparse text on the first pages (front matter) but extracts cleanly overall. These are published, copyrighted books — keep the corpus and any derived index **private**.

## C. PROPOSED MINIMAL ARCHITECTURE (v0.1)

A single local Python package, modules behind interfaces, **in-process**, no web layer:

```
core.ask(question, top_k)
  → retrieval        (ingest corpus, semantic search, evidence metadata)
  → context_pack     (canonical, shared, measurable size)
  → gemini_ive  ┐    (independent)
  → openai_ive  ┘
  → validation       (normalize to canonical IVE schema)
  → mive             (compare; testable with synthetic reports)
  → renderer         (human-readable result)
  → telemetry        (tokens, latency, cost; pricing table isolated + dated)
```

- Ports/adapters so providers and the vector store are swappable and independently testable.
- Public contracts stay provider-independent; SDK detail sealed in the Gemini/OpenAI adapters; vector client sealed in retrieval.
- No secrets loaded at import time; configuration validated before any external call.
- REST/FastAPI, SSE, frontend, and Docker are **deferred** to post-v0.1 and slot on top of this same core without changing it (`docs/14`–`docs/17`).

## D. BLOCKING AMBIGUITIES

1. **Interim UI for v0.1 (needs your call).** Locked decision #8 reintroduces "Streamlit" as a possibility, while `docs/14`–`docs/17` (from your earlier instruction) specify "Docker, not Streamlit" for the end-state. Reconciliation: end-state UI = containerized frontend; the open question is only about v0.1 validation. Options: (a) **no UI for v0.1** — validate via `ask()` + tests only *(recommended, lowest friction)*; (b) a **minimal throwaway Streamlit** purely for eyeballing results during v0.1, discarded when the real frontend is built. Which do you want?
2. **Re-sequence the spec docs?** `docs/09` and `docs/12` currently front-load REST/Docker before acceptance, which now conflicts with decisions 7–8. Recommendation: update them so REST/frontend/Docker come **after** local v0.1, and add a one-line note atop `docs/14`–`docs/17` that they are the post-v0.1 target. Approve this edit?
3. **Budget ceiling (number needed).** Decision #6 requires a conservative ceiling but none is stated. Give a concrete figure (e.g. max dev-phase spend) to gate live batches.
4. **Model pair confirmation.** Claude Code will propose an economical dev pair + a higher-quality pair from official docs (decision #5). Confirm you want to approve the pair before the first live call.
5. **Vector store confirmation.** Claude Code will pick the smallest local-first option and justify it (decision #4). Confirm you want a one-line justification approved before ingestion, or delegate fully.

Non-blocking (explicitly not gating): representative questions (decision #3) — setup, corpus inspection, schema work, and mocked tests proceed without them.

## E. IMPLEMENTATION PHASES (reconciled)

- **Phase 0 — Research.** Complete `docs/RESEARCH_LOG.md`; propose model pairs + vector store. No code.
- **Phase 1 — Foundation.** Git baseline commit (specs + corpus register only); clean Python package; core skeleton + empty module interfaces; `.env.example`; test command. No Docker.
- **Phase 2 — Retrieval.** Ingest corpus → versioned local index; evidence metadata; retrieval tests.
- **Phase 3 — Context Pack.** Canonical builder + schema validation tests.
- **Phase 4 — Gemini IVE.** Adapter + normalization tests (mocked); one controlled live call.
- **Phase 5 — OpenAI IVE.** Adapter + normalization tests (mocked); one controlled live call.
- **Phase 6 — MIVE.** Comparison logic; synthetic-report tests (no API).
- **Phase 7 — Core `ask()`.** Wire the pipeline; mocked integration test; telemetry.
- **Phase 8 — Local acceptance.** Run acceptance criteria (`docs/10`); one controlled live question end-to-end. → **Local Working Product v0.1.**
- **Phase 9+ (post-v0.1, optional).** REST/FastAPI + DEBUG SSE → containerized frontend → Docker Compose → cloud → CRUD.

## F. FIRST-PHASE ACCEPTANCE TEST (Phase 1)

Phase 1 is done when:
- Git repo initialized with a clean baseline commit containing only specifications and the corpus register (no keys, no vector data).
- The package imports with **no secrets and no network calls** at import time.
- The core exposes an `ask(question, top_k=5)` signature (stub) reachable by tests.
- All module interfaces exist as empty contracts (ports) with no provider logic yet.
- `.env.example` present (incl. `DEBUG`); `.gitignore` excludes `.env`, keys, and generated vector data.
- The test command runs and a trivial placeholder test passes.
- Missing runtime configuration fails clearly **before** any external call.

No provider calls, no Docker, no web layer in Phase 1.
