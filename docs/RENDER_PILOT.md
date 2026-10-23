# Render deployment pilot (isolated)

Branch `render-pilot-20261023`, cut from `origin/staging-snapshot-b2c89b1-20261006`
at `a7fd178`. A pilot only: nothing here changes Railway, `main`, production, or
governed content. No deployment has been made from this branch.

## Render service settings

| Setting | Value |
|---|---|
| Service type | Web Service, runtime Docker |
| Repository / branch | `mureniada/ION_MIVE` / `render-pilot-20261023` |
| Dockerfile Path | `backend/Dockerfile` |
| Docker Build Context Directory | `.` (repository root; the Dockerfile copies `backend/`, `schemas/` and `docker-compose.yml`) |
| Docker Command | leave empty: the Dockerfile `CMD` runs `uvicorn app.main:app --host 0.0.0.0 --port 8000` |
| Port | `8000`, with the `PORT` environment variable set to `8000` so Render routes to it (Render's default `PORT` is 10000) |
| Health Check Path | `/health` |
| Auto-Deploy | off for the pilot |

## Environment variables (names only)

Required:

- `ION_PILOT_API_TOKEN`: the bearer token, at least 32 characters. Generate a
  new one for this pilot; never reuse a Railway value.
- `PORT`
- `EXECUTION_PROFILE`: the only resolvable profile is `STANDARD_GEMINI`
- `GEMINI_API_KEY`, `GEMINI_MODEL`
- `VECTOR_STORE_URL`, `VECTOR_STORE_API_KEY`, `VECTOR_COLLECTION`
- `EMBEDDING_BACKEND`, `EMBEDDING_MODEL`: must match the embedding model the
  collection was built with (the code defaults are `local` and
  `sentence-transformers/all-MiniLM-L6-v2`)

Optional, VOE behaviour (set only to mirror an approved staging configuration):
`VOE_PROFILE_ENABLED`, `VOE_PROFILE_BUNDLE_DIR` (the image holds the pinned
bundle at `/app/app/modules/voe_profile/assets`), `VOE_COMPOSER_THINKING_BUDGET`,
`ENTITY_LEXICAL_ENABLED`, `ENTITY_LEXICAL_MAX`, `EMBEDDING_NUM_THREADS`,
`DEFAULT_TOP_K`, `CONTEXT_CHAR_BUDGET`.

Must stay unset: `DEBUG`. Not needed under `STANDARD_GEMINI`: `OPENAI_API_KEY`,
`OPENAI_MODEL`.

## What the pilot branch changes

- Every route except `/health` (`/ask`, `/ask/stream`, `/pilot/sessions`,
  `/pilot/sessions/{id}/turn`, `/pilot/sessions/{id}/close`) requires
  `Authorization: Bearer <ION_PILOT_API_TOKEN>` (`backend/app/api/auth.py`).
  - Token unset, empty or shorter than 32 characters: `503 not_ready` for every
    gated request. Nothing gets through.
  - Missing, malformed or wrong token: `401 unauthorized` with
    `WWW-Authenticate: Bearer`.
  - The check runs before request validation, readiness checks and Core
    construction. It compares SHA-256 digests with `hmac.compare_digest`. No
    payload or log line contains either token.
- `/ask/stream` checks `DEBUG` first. With `DEBUG` unset it returns 404 to
  every caller, with or without a token. With `DEBUG` on it still requires the token.
- `/docs`, `/redoc` and `/openapi.json` are not mounted (404).

## What `/health` proves

`GET /health` returns `{"status": "ok"}` from the process with no other work. It
loads no settings and builds no Core. It checks no provider key, vector store,
VOE bundle or API token. A passing health check means only that uvicorn is up
and serving the app. It does not show that the service can answer.
Readiness is checked per request by `require_ready` in
`backend/app/config_check.py`, which returns `503 not_ready` on `/ask` and on
pilot turns.

## Known limits (not changed on this branch)

- FastAPI parses the request body before the handler runs. A body that is
  not JSON gets `422` before the token check, even when no token is
  configured. No settings, Core or provider work is reached.
- With `EXECUTION_PROFILE` unset or unknown, an authenticated `/ask` or pilot
  turn fails at Core construction (`_get_core()`, outside the readiness
  `try`). It returns a plain-text `500`, not `503 not_ready`. This
  behaviour comes from the base commit.
- `local-embed` installs `sentence-transformers`, which pulls the default
  CUDA build of PyTorch: several GB of wheels. Builds are slow and the image
  is large. Memory use with `EMBEDDING_BACKEND=local` was not measured here.
  A 512 MB instance is unlikely to be enough (estimate).

## Smoke check after a deploy (operator)

1. `GET /health` returns 200.
2. `POST /ask` with no `Authorization` header returns 401.
3. `GET /ask/stream?question=x` and `GET /docs` both return 404.
4. `POST /ask` with the token and `{"question": " "}` returns 400. This shows
   the token is accepted, without spending a provider call.
