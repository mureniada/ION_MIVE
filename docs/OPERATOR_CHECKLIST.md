# Operator Checklist

Reflects the operator's locked decisions of **2026-07-13**. This supersedes the earlier draft (which had deferred Docker/FastAPI — now locked in). Two parts: locked decisions (binding on Claude Code) and outstanding operator actions.

## Part 1 — Locked decisions (binding)

1. **Runtime providers** — OpenAI API + Google Gemini API, both required. Keys configured locally by operator as `OPENAI_API_KEY`, `GEMINI_API_KEY`. Never request/print/commit values. Verify only: variables exist, one minimal authenticated request works, billing active. **No live call before the operator confirms both keys are configured.**
2. **Budget** — total initial dev + live-testing ceiling **USD 10**; max live spend without extra approval **USD 1**. Start with mocks + deterministic tests; first live test = **one** question; before any larger batch report chosen models, #provider calls, estimated max cost, purpose. No repeated uncontrolled calls.
3. **Docker** — part of the intended architecture and the reproducible runtime/orchestration layer. But implement in dependency order: **the MIVE core must be independently testable before full-stack Docker integration is declared complete.**
4. **Git** — initialized before implementation; clean baseline commit of specs/handover/schemas/corpus register/architecture docs; no secrets, no vector index, no runtime cache; baseline hash reported.
5. **Corpus** — all 9 files in `corpus/source/` approved and in scope (9 files, 0 duplicate checksums, 3 TXT + 6 PDF, all text-extractable, no OCR). Private research material; no public exposure/redistribution of raw text; excerpts only for traceability.
6. **Representative questions** — 20-question set locked (Part 3). Question 1 is the first controlled live end-to-end test. Questions 2–20 reserved; not run live without separate approval.
7. **Vector store** — **Qdrant** only, unless the audit finds a concrete technical blocker. No second/parallel store for v0.1. Behind a provider-independent retrieval interface. Report deployment mode, collection naming, embedding dimension, payload contract, rebuild procedure, persistence volume before implementation.
8. **Models** — research current Gemini/OpenAI models from official docs; propose economical dev pair (A) + optional quality pair (B); no deprecated names; no first live call until operator approves Pair A + estimated cost; names/prices are configuration, not logic.
9. **Service architecture** — Corpus → Qdrant retrieval → Context Pack → Gemini IVE + OpenAI IVE → MIVE → deterministic renderer → FastAPI → REST/SSE → separated frontend → Docker Compose → later cloud. FastAPI is the service boundary; SSE emits meaningful stage states; the intelligence core stays independently testable.
10. **Documents** — maintain `RESEARCH_LOG.md`, `OPERATOR_CHECKLIST.md`, `ARCHITECTURE_DECISIONS.md`, `CORPUS_REGISTER.md`, `MODEL_AND_PRICING_REGISTER.md`, `PHASE_PLAN.md`. Research log distinguishes verified fact / operator decision / architectural assumption / deferred decision.

## Part 2 — Operator action items (outstanding)

- [ ] **Configure `OPENAI_API_KEY`** (billing enabled) in local `.env`.
- [ ] **Configure `GEMINI_API_KEY`** (billing enabled) in local `.env`.
- [ ] **Confirm both keys are set** so Claude Code may run the single minimal auth check (no reasoning call) and later the first live question.
- [ ] **Verify Docker on the host** (operator-side; not reachable from the build environment): Docker Desktop installed, Docker Engine running, `docker compose version` works.
- [ ] **Approve the economical model pair (A)** and its ~$0.02 first-question estimate before the first live call.
- [ ] **Confirm where Claude Code will run** (handoff environment) with read/write access to this repo.

## Part 3 — Locked validation questions

1. What is money?  ← **first controlled live end-to-end test**
2. What are the primary functions of money?
3. Is money fundamentally a commodity, credit, or a social institution?
4. How did money historically emerge?
5. What is the Credit Theory of Money?
6. What gives money its value?
7. What is the relationship between money and debt?
8. What is the difference between money and currency?
9. How does inflation affect the function of money?
10. What makes a monetary system trustworthy?
11. What is hard money?
12. How do gold and Bitcoin compare as monetary assets?
13. What is the role of central banks in money creation?
14. How does commercial bank credit create money?
15. Can money exist without government?
16. How does monetary scarcity influence economic behaviour?
17. What are the strongest disagreements among the corpus authors about money?
18. Which claims about money are supported by several independent corpus sources?
19. Which important questions about money remain unresolved in the corpus?
20. Based only on the corpus, what is the most defensible definition of money?

Questions 2–20 are reserved for later acceptance, quality, latency, and cost evaluation and must not be run live without separate approval.

## Never
- Never commit `.env`, API keys, or generated vector data.
- Never enable `DEBUG` in a user-facing deployment.
- Never run uncontrolled live API batches or exceed the USD 1 live ceiling without approval.
