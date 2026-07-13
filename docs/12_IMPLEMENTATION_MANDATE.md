# Implementation Mandate for Anthropic

## Task

Build a new implementation from the specifications in this repository.

## Do not inherit

Do not use:
- old ION_PLUS code;
- old ION_CORPUS code;
- Codex-generated module design;
- prior debugging traces;
- previous path or environment workarounds.

## Build independently

You own:
- library choices;
- exact internal module names and packaging details;
- choice of vector database client;
- test framework;
- prompt construction;
- normalization implementation;
- local configuration strategy;
- frontend framework choice.

You do **not** own (these are mandated — see `docs/14_ARCHITECTURE.md`):
- the frontend/backend monorepo split;
- the single backend core with modules behind interface contracts;
- in-process modules for v0.1;
- REST as the frontend↔backend protocol;
- the `DEBUG`-gated SSE progress stream;
- Docker / Docker Compose delivery.

## Mandatory public behavior

The backend core must expose a tested function equivalent to:

```python
ask(question: str, top_k: int = 5) -> Result
```

exposed over an internal REST API (`docs/15_API_CONTRACT.md`). It must execute real Gemini and OpenAI paths independently and produce a canonical MIVE result.

## Delivery sequence

1. Complete the research-first mandate (`docs/17`) and record findings.
2. Read specifications.
3. Propose a minimal architecture consistent with `docs/14`–`docs/16`.
4. Identify ambiguities and ask only essential questions.
5. Create the monorepo skeleton (backend core + module interfaces, frontend, Docker) per `docs/16_TARGET_FILE_TREE.md`.
6. Implement retrieval module and tests.
7. Implement Context Pack and tests.
8. Implement Gemini adapter module and tests.
9. Implement OpenAI adapter module and tests.
10. Implement MIVE comparison module and tests.
11. Implement the core `ask()`.
12. Expose the REST API (+ DEBUG-gated SSE).
13. Execute acceptance tests.
14. Add the containerized frontend only after backend/API PASS.
15. Wire up Docker Compose for the full stack.
16. Stop at v0.1; do not expand.

## Reporting format after each phase

- files changed;
- tests executed;
- exact result;
- known limitations;
- next smallest step;
- token/cost implications when relevant.

## Stop conditions

Stop and report rather than improvising when:
- source corpus is unavailable;
- required model access is unavailable;
- specifications conflict;
- evidence identifiers cannot remain stable;
- acceptance cannot be demonstrated.
