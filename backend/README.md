# ION MIVE Backend

Core orchestrator + modules behind interface contracts (docs/14). Import-safe:
importing any module needs no secrets and opens no connections; provider SDKs,
the Qdrant client, and the local embedder are lazy-imported in factories.

## Milestone status
- **M1–M6: complete, mocked/deterministic tests green (37/37).** Core `ask()` is
  independently testable with no live API calls (ADR-006).
- M7 (first live call) — NOT started; awaiting operator go + key confirmation.
- M8 (REST/SSE), M9 (frontend), M10 (Compose full-stack) — later.

## Layout
```
app/core/        orchestrator, ports, models, config, errors, clock  (no SDKs)
app/modules/     retrieval/ context_pack/ gemini_ive/ openai_ive/ mive/ renderer/ telemetry/
app/validation/  jsonschema validation against ../schemas (source of truth)
app/container.py composition root (production wiring, lazy)
app/cli.py       terminal entry (live path; gated by config_check)
tests/           mocked + synthetic tests (no network)
```

## Run the tests
No pytest required for the bundled runner (stdlib + numpy + jsonschema):
```
cd backend
python run_tests.py
```
Or, in an environment with dev deps: `pip install -e ".[dev,api,local-embed]" && pytest`.

## Design rules honored
- Gemini & OpenAI run independently on the identical Context Pack; neither sees
  the other's output before MIVE.
- A single-provider failure raises a precise provider-stage error — never a success.
- Provider output is normalized then validated against the canonical JSON Schemas;
  no fabricated repair.
- Unknown model pricing returns `null`; pricing table is isolated and dated.
- Qdrant is the only product vector store; the in-memory index is a test double.

## Not yet executed here (needs real deps / Docker)
- Real Qdrant ingestion + local embeddings (M2 runtime) — code complete; run on
  Docker where `qdrant-client` and `sentence-transformers` are installed.
- Live provider calls (M7) — after operator approval + key confirmation.
