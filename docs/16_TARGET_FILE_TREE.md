# Target File Tree

This is the **target monorepo structure** Claude Code must produce. Exact filenames inside modules are the implementer's to choose; the top-level shape (monorepo, `frontend/` + `backend/`, core + modules, Docker) is mandatory. If research suggests a better internal layout, refine it and record why in the research log — do not change the mandated boundaries.

The existing `docs/`, `schemas/`, and `corpus/` from this clean-room pack are kept and sit alongside the new `backend/` and `frontend/`.

```
ION_MIVE/
├── README.md
├── CLAUDE.md
├── .env.example
├── .gitignore
├── docker-compose.yml              # backend + frontend + vector store
│
├── docs/                           # this clean-room pack (specs & contracts)
├── schemas/                        # context_pack / ive_report / mive_result JSON schemas
├── corpus/
│   └── source/                     # operator-approved source documents
│
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml              # single reproducible Python environment
│   ├── app/
│   │   ├── main.py                 # API bootstrap, DI wiring, DEBUG handling
│   │   ├── api/                    # REST + DEBUG-only SSE routes (thin)
│   │   │   ├── routes_ask.py
│   │   │   ├── routes_health.py
│   │   │   └── sse.py              # progress stream, DEBUG-gated
│   │   ├── core/                   # the orchestrator hub
│   │   │   ├── orchestrator.py     # core.ask(question, top_k) pipeline
│   │   │   ├── ports.py            # interface contracts (RetrievalPort, IVEPort, MIVEPort, ...)
│   │   │   ├── models.py           # provider/transport-independent domain models
│   │   │   └── config.py           # settings incl. DEBUG (no secrets at import time)
│   │   ├── modules/                # adapters implementing the ports
│   │   │   ├── retrieval/          # corpus ingestion + semantic retrieval + vector client
│   │   │   ├── context_pack/       # canonical Context Pack builder
│   │   │   ├── gemini_ive/         # Gemini adapter (google-genai) -> canonical IVE
│   │   │   ├── openai_ive/         # OpenAI adapter (Responses API) -> canonical IVE
│   │   │   ├── mive/               # comparison logic (testable with synthetic reports)
│   │   │   ├── renderer/           # structured result -> human-readable output
│   │   │   └── telemetry/          # usage, latency, cost; pricing table isolated & dated
│   │   └── validation/             # IVE / Context Pack schema validation
│   └── tests/
│       ├── test_retrieval.py
│       ├── test_context_pack.py
│       ├── test_gemini_normalization.py
│       ├── test_openai_normalization.py
│       ├── test_mive_synthetic.py
│       ├── test_core_ask_mocked.py
│       ├── test_api.py
│       └── test_live_smoke.py       # one controlled live test
│
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── index.html
    ├── src/
    │   ├── main.(tsx|jsx)
    │   ├── api/client.ts            # REST client + optional SSE consumer (DEBUG)
    │   ├── components/              # question input, progress, answer, evidence, metrics
    │   └── views/                   # result view rendering docs/07 sections
    └── tests/
```

## Rules encoded by this tree

- `backend/app/core/` is the only orchestrator. `backend/app/modules/` are adapters behind `core/ports.py`. The API layer (`backend/app/api/`) is thin.
- Provider SDKs appear **only** inside `modules/gemini_ive/` and `modules/openai_ive/`. The vector store client appears **only** inside `modules/retrieval/`.
- The pricing table lives inside `modules/telemetry/`, isolated from runtime logic and dated/versioned (`docs/08`).
- `frontend/` imports nothing from `backend/`; it only calls the REST API.
- One `docker-compose.yml` at the root wires the whole stack.
- Every module ships with tests; MIVE is tested with synthetic IVE reports (no API access required).
