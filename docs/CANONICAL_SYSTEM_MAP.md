# Canonical System Map — ION MIVE

**Date:** 2026-08-05
**Produced by:** Mission R1 (record and reconcile the canonical system map),
following the read-only Mission R0 audit.
**Revised:** 2026-08-05 by Mission R8, to match what Missions R2–R7
established. Corrections are marked in place; superseded statements are
recorded as superseded rather than silently deleted.
**Type:** Factual system map. This document records state; it does not
authorise any change, deployment, or scope expansion.

## How to read this document

Every substantive line carries exactly one marker:

| Marker | Meaning |
|---|---|
| **VERIFIED** | Established by a command executed during R0–R7, with the evidence named on the line. |
| **VERIFIED NEGATIVE** | Established as *not* true, with the evidence named. Stronger than UNKNOWN. |
| **OPERATOR-STATED** | Asserted by the operator. Not verified by any mission. Recorded as provenance, not as proof. |
| **UNKNOWN** | Not established. Must not be treated as true, false, or "probably" either way. |

An **UNKNOWN** must never be upgraded to a fact without new evidence and a
new recorded verification. Where this revision upgrades an earlier UNKNOWN,
the observation that moved it is stated on the same line. Absence of
evidence is recorded as UNKNOWN, not as a negative finding.

**Evidence base.** VERIFIED lines rest on read-only Railway CLI and Railway
public GraphQL **query** calls (`railway list`, `railway status`,
`railway deployment list`, `railway domain list`, `railway logs`
— including `--build`, `--http`, `--dns`, `--network` — and
`railway api <query>`), read-only Git commands (`git rev-parse`,
`git status`, `git show --stat`, `git ls-remote`), read-only repository
reads, and **three individually authorised live `POST /ask` requests**
(R4, R5, R7 — one each). No mutation, deployment, or variable-value read was
performed in any mission. Variable **names** were enumerated once, in R2,
with values filtered out inside the command pipeline.

---

## 1. Canonical system — the four components

### 1.1 Frontend — Streamlit Cloud

- **OPERATOR-STATED** — the frontend is a Streamlit Cloud application at
  `ionmive-jwvwqwat7jukzvvnqvvpkq.streamlit.app`.
- **VERIFIED NEGATIVE (R8 revision) — the deployed Streamlit Cloud app is
  NOT built from this repository's `ui/`.** Evidence: canonical production's
  runtime logs record `GET /ask/stream … 404 Not Found` at
  `2026-08-04T16:07:31.492396089Z` and `2026-08-04T16:46:54.142322822Z`
  with **no `POST /ask` following either one**. This repository's client
  falls back to exactly one `POST /ask` on a 404
  (`ui/client.py:91-98`, documented at `ui/client.py:83-84`), so the
  repository client would have produced that follow-up request. It did not
  appear. This supersedes R1's "**UNKNOWN** whether the deployed app is
  built from that code."
- **VERIFIED** — a Streamlit thin client exists in this repository under
  `ui/`, committed as `11b7056` (2026-07-14); evidence:
  `ION_MIVE_HANDOVER_INDEX.md` section 5 (E1 closure record). This verifies
  the repository content only.
- **VERIFIED** — the repository client reads its backend base URL from a
  single environment variable `BACKEND_URL`, defaulting to
  `http://localhost:8000`; evidence: `ui/client.py:17-18`. It calls three
  endpoints: `GET /health` (`ui/client.py:23`), `GET /ask/stream`
  (`ui/client.py:90`), and `POST /ask` (`ui/client.py:34` and the fallback
  at `ui/client.py:95`).
- **UNKNOWN** — whether the deployed app is currently reachable, which
  backend URL it targets, which commit or branch it serves, and how it is
  configured. No mission has called the Streamlit app.
- **UNKNOWN** — Streamlit Cloud configuration and secrets. These have never
  been inspected by any mission in this workspace and must not be assumed to
  match the repository's `ui/` code or the backend contract. See section 5.

### 1.2 Backend — Railway

- **VERIFIED** — canonical backend is Railway project **`helpful-radiance`**
  (`da1c44f6-13ca-4ea2-bc0e-56bd3f531102`), environment `production`
  (`d0c10118-49e0-4d6a-afef-e0da325df470`), service **`ION_MIVE`**
  (`33fa65be-5b8e-4e0c-8277-ba43e05d7032`); evidence: `railway list --json`.
- **VERIFIED** — source is GitHub repo `mureniada/ION_MIVE`, branch `main`,
  root directory empty (repository root); evidence:
  `railway deployment list --json` deployment metadata and
  `railway api` `serviceInstance.source` → `{"image":null,"repo":"mureniada/ION_MIVE"}`.
- **VERIFIED** — builder **`DOCKERFILE`**, `dockerfilePath` =
  **`backend/Dockerfile`** (no leading slash); evidence:
  `deployment.meta.serviceManifest.build`.
- **VERIFIED (R8 revision) — current active deployment is
  `c6c8596d-e4ae-4291-8fd1-6c30938dfef2`**, status **SUCCESS**, created
  `2026-08-05T18:01:54.626Z`, instance status **RUNNING**,
  `deploymentStopped: false`; evidence: `railway deployment list --json`
  and a `railway api` GraphQL query of
  `activeDeployments { status deploymentStopped instances { status } }`.
  It supersedes `3ea5e708-3652-475c-ad65-4b7924e44254`
  (`2026-08-05T17:34:06.659Z`), which superseded
  `075f0dac-4c0e-425b-a1f9-18154324ef30` (`2026-08-04T14:31:58.235Z`);
  both earlier deployments are now `REMOVED`. The two redeployments were
  triggered by operator credential changes, not by code changes — see
  section 3.
- **VERIFIED** — deployed commit
  **`0da3488e056f018b04abc916b7e8e3a7097c1388`**
  (*docs: repair automation bootstrap state and guardrails*) — the accepted
  baseline, unchanged across all three deployments; evidence:
  `deployment.meta.commitHash`.
- **VERIFIED** — owns the domain **`ionmive-production.up.railway.app`**
  (domain id `eaf29cba-c7ba-48e5-8037-0c8aed2588b8`, type `service`,
  `targetPort` 8000, `syncStatus` ACTIVE, created 2026-07-15T00:02:14Z);
  evidence: `railway domain list --json`, run per service across every
  project in the account. It is the **only** ION_MIVE service in the account
  that owns any domain.
- **VERIFIED (R8 revision)** — the backend serves `POST /ask` correctly over
  that domain, returning HTTP 200 with a complete rendered result; evidence:
  the R7 verification request (section 3). This supersedes R1's "live HTTP
  health is unverified."
- **VERIFIED** — `GET /ask/stream` returns 404 in production because `DEBUG`
  is not set to a truthy value; evidence: the gate at
  `backend/app/main.py:71` combined with `_as_bool` at
  `backend/app/core/config.py:15-18`, and `DEBUG` being absent from the
  service's variable names (R2). The route returned `200 OK` on 2026-07-30
  and 2026-08-03 on earlier deployments, so `DEBUG` was truthy then.
- **VERIFIED** — start command recorded on the equivalent service in the
  linked project is
  `/bin/sh -c "exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"`;
  evidence: `railway status --json` (glorious-compassion). **UNKNOWN** —
  whether `helpful-radiance`'s ION_MIVE service uses the identical start
  command; its start command was not separately read.
- **VERIFIED** — the backend's HTTP path has **no logger, no handler, and no
  traceback emission**. Provider error text travels only in the HTTP
  response body; a failure during a streamed run would log `200 OK` and
  leave no server-side trace. Evidence: a repository-wide search of
  `backend/app/` for `import logging|logger|logging\.|print\(|traceback|exc_info`
  matches only `backend/app/cli.py` and `backend/app/ingest_cli.py`, neither
  of which runs in the web process. This is why the provider 401s recorded
  in section 3 could never be confirmed from logs.

### 1.3 Vector store — Qdrant

**This section was materially wrong before the R8 revision.** It framed the
question as "which of the two Railway Qdrant services holds the corpus." The
premise was false: canonical production uses **neither**.

- **VERIFIED (R8 revision) — production queries an EXTERNAL Qdrant Cloud
  cluster in `europe-west3` on GCP**, at host
  `[REDACTED_SECRET].europe-west3-0.gcp.cloud.qdrant.io`, over TCP port
  **6333**. Evidence: canonical production's DNS logs for the R4 request
  resolve that host at `2026-08-05T16:59:53.931810123Z` (A) and
  `…933796093Z` (AAAA), and the network-flow logs record egress TCP to
  `34.107.67.89:6333` carrying 2 993 bytes at `16:59:54.534626260Z` and
  **11 662 bytes at `17:00:09.290395813Z`** — the vector search itself. The
  same host was resolved again during the R7 run at
  `2026-08-05T17:44:43.618322952Z` and `17:44:56.168025830Z`. The cluster
  identifier is redacted: it is effectively the host portion of a variable
  value and is not reproduced here.
- **VERIFIED (R8 revision) — both Railway Qdrant services appear UNUSED by
  canonical production.** No DNS query and no network flow to
  `qdrant-production-26ee.up.railway.app`,
  `qdrant-production-359b.up.railway.app`, or any Railway-internal Qdrant
  address appears in the logs for either the R4 or the R7 request. Both
  services are nevertheless running and billable — see section 4.
- **SUPERSEDED** — the previous entry read: "**UNKNOWN — WHICH QDRANT HOLDS
  THE 6063-VECTOR NINE-BOOK CORPUS IS NOT ESTABLISHED.** Both instances are
  running and both are reachable in principle." That UNKNOWN rested on a
  wrong premise — the choice was never between those two — and is removed
  rather than answered.
- **VERIFIED** — a Qdrant service exists inside `helpful-radiance`: service
  `Qdrant` (`3a0c3a20-5dda-445f-8e29-13b0b524dce9`), source image
  `qdrant/qdrant`, `numReplicas` 1, latest deployment
  `9109b9c9-67fd-427c-af24-fe7e1a49cc96` **SUCCESS**
  (2026-07-15T01:18:33.178Z), instance **RUNNING**, domain
  `qdrant-production-26ee.up.railway.app` (ACTIVE); evidence:
  `railway api` GraphQL query + `railway domain list --json`.
- **VERIFIED** — a second, separate Qdrant exists in project
  **`devoted-freedom`** (`8827b1c3-780d-43a1-a540-e802ca0e8803`), service
  `Qdrant` (`e81eca6c-4a02-4d71-bc8e-45b639b82863`), source image
  `qdrant/qdrant`, `numReplicas` 1, latest deployment
  `cd19492a-90bf-4c8b-b1fe-1537435d04bc` **SUCCESS**
  (2026-07-15T01:06:43.411Z), instance **RUNNING**, domain
  `qdrant-production-359b.up.railway.app` (ACTIVE); evidence: same commands.
  `devoted-freedom` contains **no** ION_MIVE service.
- **UNKNOWN** — what data, if any, either Railway Qdrant service contains.
  Establishing that would require calling them, which no mission has done.
- **VERIFIED** — the external cluster returns real corpus data: the R7 run
  retrieved 5 chunks totalling `context_characters: 5965` across 5
  documents, all from `sacred_economics_book_text`; evidence: the R7
  response payload's `operational_metrics` and `evidence` arrays.
- **VERIFIED** — the 6063-vector figure originates from the
  clean-environment ingestion record: `chunks created: 6063`;
  `unique chunk_ids: 6063`; `qdrant vectors: 6063`; 9 source files, 0 failed;
  evidence: `ION_MIVE_HANDOVER_INDEX.md` section 7 (criterion A1). That
  record describes a **local, ephemeral** ingestion. **UNKNOWN** — whether
  the external Qdrant Cloud cluster holds exactly that 6063-vector,
  nine-book corpus. Its vector count and collection contents have not been
  read.

**Embedding model — downloaded at runtime, every cold start.**

- **VERIFIED (R8 revision) — in production the embedding model is downloaded
  from Hugging Face on every cold start; there is no persistent embedding
  cache on Railway.** Evidence: DNS and flow logs for both live requests
  show the container resolving and fetching from `huggingface.co`,
  `cas-server.xethub.hf.co`, and `us.aws.cdn.hf.co` *during the request* —
  R4 at `17:00:00`–`17:00:05` (flows of 245 346, 65 571, 31 285 and 8 409
  bytes), R7 at `17:44:48`–`17:44:50` — each accompanied by the runtime log
  line `Warning: You are sending unauthenticated requests to the HF Hub`
  followed by `Loading weights: … 103/103`. The R7 run's
  `retrieval_latency_ms` of 9 905.114 includes that download.
- **VERIFIED (R8 revision)** — consequently the **M8.1 persistent-`hf_cache`
  guarantee is docker-compose-local only** and does **not** hold for the
  Railway deployment. `ION_MIVE_HANDOVER_INDEX.md` sections 2–3 record
  "persistent `hf_cache` reuse showed no Hugging Face downloads on three
  fresh-container runs"; that result was obtained under Docker Compose with
  a mounted cache volume, and must not be read as covering production. The
  production image (`backend/Dockerfile`) bakes in no model and mounts no
  cache volume.

### 1.4 Corpus tooling

- **OPERATOR-STATED** — corpus tooling lives in a separate local folder,
  `Documents\Projects\ION_CORPUS_v3`, outside this repository.
- **UNKNOWN** — its contents, its version, its relationship to the
  6063-vector ingestion, and whether it produced the data now served by the
  external Qdrant Cloud cluster. It has not been read by any mission; it is
  outside this repository's working directory.
- **VERIFIED** — this repository does not track raw corpus source:
  `.gitignore` excludes `corpus/source/` with the note that it is
  private/copyrighted material; evidence: repository `.gitignore`.

---

## 2. Non-canonical deploy targets

**VERIFIED** — the GitHub repository `mureniada/ION_MIVE`, branch `main`, is
connected to **five** separate Railway projects. All five deployed the same
commit `0da3488e…`. Only `helpful-radiance` owns a domain. Evidence:
`railway list --json`, plus per-project `railway deployment list --json` and
`railway domain list --json`.

| Project | Project ID | Service ID | Builder / dockerfilePath | Latest deployment | Commit | Domain |
|---|---|---|---|---|---|---|
| **helpful-radiance** (canonical) | `da1c44f6-…` | `33fa65be-…` | DOCKERFILE / `backend/Dockerfile` | `c6c8596d-…` **SUCCESS**, RUNNING | `0da3488e…` | **`ionmive-production.up.railway.app`** |
| glorious-compassion | `0a1046ba-…` | `1ec222ae-…` | DOCKERFILE / `/backend/Dockerfile` | `aeecc409-…` SUCCESS, RUNNING | `0da3488e…` | none |
| lucid-forgiveness | `f08bdde9-…` | `b19010d5-…` | DOCKERFILE / `/backend/Dockerfile`, rootDirectory `backend` | `0197e6fd-…` FAILED | `0da3488e…` | none |
| ingenious-renewal | `14b51361-…` | `8a83182f-…` | RAILPACK / *(none)* | `84787f77-…` FAILED | `0da3488e…` | none |
| proud-laughter | `e3beb2f8-…` | `22b87be3-…` | RAILPACK / *(none)* | `3f216cf6-…` FAILED | `0da3488e…` | none |

Why each is **not** production:

- **`glorious-compassion`** — **VERIFIED** the backend container is SUCCESS and
  RUNNING on `0da3488e…`, but it owns **no domain**, so nothing external can
  reach it, and the project contains **no Qdrant service**. **VERIFIED** it
  has never received an `/ask` request of any kind — its runtime logs across
  both recent deployments contain only startup lines and `GET /health`.
  **VERIFIED** it is also the project the local CLI is linked to (see
  section 6). **VERIFIED** its history shows it ran on RAILPACK and failed
  every build until a DOCKERFILE builder was configured between
  2026-08-04 10:36 and 11:18 local time.
- **`lucid-forgiveness`** — **VERIFIED** every recent deployment FAILED, most
  recently `0197e6fd-…` on `0da3488e…`. **VERIFIED** it is configured with
  builder DOCKERFILE, `dockerfilePath` `/backend/Dockerfile`, **and**
  `rootDirectory` `backend` — a combination that differs from the working
  canonical configuration. No domain, no Qdrant service. **UNKNOWN** — the
  precise build failure reason; its build logs were not fetched.
- **`ingenious-renewal`** — **VERIFIED** it has **never** produced a successful
  deployment: all six deployments in its history are FAILED, all on builder
  RAILPACK with no `dockerfilePath`. No domain, no Qdrant service.
  **VERIFIED** the failure cause for build
  `7a6cf821-b9d7-476a-8a87-3a2a6cbb00e5` (commit `29c75d5b…`), from its full
  build log: `using build driver railpack-v0.35.0` → `⚠ Script start.sh not
  found` → `✖ Railpack could not determine how to build the app.` →
  `railpack process exited with an error`. This is a **service
  build-configuration** failure, not a source-code failure: the same commit
  built successfully in the projects configured with builder DOCKERFILE.
- **`proud-laughter`** — **VERIFIED** created `2026-08-05T12:34:43.948Z`; its
  single deployment `3f216cf6-34b4-4334-8d2f-9d0637071b6e` FAILED at
  `2026-08-05T12:34:45.619Z` on builder RAILPACK with no `dockerfilePath` —
  the same misconfiguration pattern as `ingenious-renewal`. No domain, no
  Qdrant service, `activeDeployments: []`. **UNKNOWN** — who or what created
  it and why (see section 4).
- **`devoted-freedom`** — **VERIFIED** it is not a repo deploy target at all:
  it contains only the `Qdrant` image service described in section 1.3, with
  no ION_MIVE service and no GitHub source.

---

## 3. RESOLVED — incidents closed with evidence

Each entry records a fault that was diagnosed, repaired by the operator, and
verified. Repairs were credential replacements made by the operator through
the Railway dashboard; **no code change was made, proposed, or authorised**,
and the deployed commit remained `0da3488e…` throughout.

### 3.1 Gemini 401 — RESOLVED 2026-08-05

- **VERIFIED — cause.** The credential supplied via `GEMINI_API_KEY` was not
  a credential type the Generative Language API accepts. Evidence: the
  verbatim error body returned by canonical production on 2026-08-05 to an
  authorised `POST /ask` (Mission R5), HTTP 502,
  `error_stage: "gemini"`:
  `401 UNAUTHENTICATED`, `'reason': 'ACCESS_TOKEN_TYPE_UNSUPPORTED'`,
  `'method': 'google.ai.generativelanguage.v1beta.GenerateContent'`,
  `'service': 'generativelanguage.googleapis.com'`. The API named the fault
  as the **type** of credential presented, not a missing, malformed,
  unauthorised, or unentitled one.
- **VERIFIED — the failing stage, established independently before the body
  was captured.** During the R4 request, retrieval succeeded (11 662 bytes
  returned from the Qdrant Cloud cluster), `generativelanguage.googleapis.com`
  was resolved at `17:00:10.562108784Z` and answered within ~130 ms, and
  `api.openai.com` was **never** resolved or contacted. Because the core runs
  the engines sequentially — Gemini at `backend/app/core/orchestrator.py:108`,
  then OpenAI at `:109`, with `_run_engine` re-raising on first failure at
  `:168-183` — Gemini was the only stage that could abort before OpenAI ran.
- **OPERATOR-STATED — repair.** The operator replaced `GEMINI_API_KEY` on
  `helpful-radiance` / `ION_MIVE` / `production` via the Railway dashboard.
  The value was never seen, handled, or requested by any mission.
- **VERIFIED — repair confirmed** by deployment
  `3ea5e708-3652-475c-ad65-4b7924e44254`
  (SUCCESS, RUNNING, created `2026-08-05T17:34:06.659Z`, commit unchanged).
  The authorised R6 request advanced **past** the Gemini stage and failed at
  `error_stage: "openai"` instead — only reachable if Gemini returned a valid
  report. Corroborated by timing: DNS shows
  `generativelanguage.googleapis.com` at `17:44:57.689383652Z` and
  `api.openai.com` at `17:45:17.514390614Z` — a **~19.8-second real
  generation window**, against the ~130 ms rejection seen before the repair,
  and the first contact with OpenAI recorded in the entire investigation.
- **VERIFIED — this supersedes** the earlier entry "The Gemini 401 error is
  unresolved. **UNKNOWN** cause and current state," and the corresponding
  open-issue note in `CLAUDE.md`.

### 3.2 OpenAI 401 `invalid_api_key` — RESOLVED 2026-08-05

- **VERIFIED — cause.** The credential supplied via `OPENAI_API_KEY` was
  rejected by OpenAI as incorrect. Evidence: the verbatim error body from the
  authorised R6 request, HTTP 502, `error_stage: "openai"`:
  `Error code: 401 - {'error': {'message': 'Incorrect API key provided:
  [REDACTED_SECRET]. …', 'type': 'invalid_request_error', 'code':
  'invalid_api_key', 'param': None}, 'status': 401}`. The rejected key is
  redacted; no value, length, prefix, suffix, or shape is recorded.
- **VERIFIED — this fault was pre-existing and masked, not a regression
  caused by the Gemini repair.** Evidence: R4's network logs prove OpenAI was
  never contacted while Gemini failed first, so the invalid OpenAI key could
  not have surfaced until the Gemini stage began succeeding.
- **OPERATOR-STATED — repair.** The operator replaced `OPENAI_API_KEY` on the
  same service via the Railway dashboard.
- **VERIFIED — repair confirmed** by deployment
  **`c6c8596d-e4ae-4291-8fd1-6c30938dfef2`** (SUCCESS, RUNNING, created
  `2026-08-05T18:01:54.626Z`, commit unchanged): the authorised R7 request
  returned **HTTP 200**.

### 3.3 First successful end-to-end MIVE run in production — 2026-08-05

**VERIFIED** — shape of the R7 success (`request_id
2ef576c61cfd4000a56fe5d13b239209`, `timestamp 2026-08-05T18:05:46.589828+00:00`):

- **All seven contract keys present**, flat, with no envelope: `question`,
  `primary_answer`, `mive_assessment`, `uncertainty`, `evidence`,
  `operational_metrics`, `disclaimer` — matching `docs/15_API_CONTRACT.md`.
- **Both providers reported independently.** `gemini` / `gemini-2.5-pro`:
  1 526 input tokens, 1 609 output tokens, 24 816.943 ms,
  `usage_is_estimated: false`. `openai` / `gpt-5.4-mini`: 1 702 input tokens,
  1 208 output tokens, 13 055.027 ms, `estimated_cost: 0.0067125`,
  `usage_is_estimated: false`.
- **MIVE comparison produced** — `overall_status: "partial_agreement"`, with
  1 agreement, 3 partial agreements, 0 disagreements, 5 unique findings,
  0 weakly-supported claims, each carrying `similarity` and
  `evidence_overlap` chunk IDs.
- **`status: "success"`, `error_stage: null`.** Retrieval 9 905.114 ms,
  comparison 3.191 ms, total 47 801.534 ms; 5 chunks, 5 context documents,
  5 965 context characters.
- **VERIFIED** — the epistemic invariants held on this run: the two engines
  ran independently, neither saw the other's report, both received the same
  Context Pack, disagreement and uncertainty were preserved rather than
  resolved, and the disclaimer ("Intelligence is not truth…") was rendered.
- **This supersedes** the earlier "Live HTTP health is unverified" UNKNOWN.
  It applies to the backend over its Railway domain **only** — not to the
  Streamlit Cloud frontend, which remains unverified and, per section 1.1,
  is not built from this repository's `ui/`.

---

## 4. OPEN — defects and unresolved items

Nothing in this section may be treated as settled.

**Blocking end users**

1. **The deployed frontend cannot reach the working backend.** **VERIFIED** —
   the deployed Streamlit Cloud app calls `GET /ask/stream`, receives 404
   (production has `DEBUG` unset, `backend/app/main.py:71`), and does **not**
   fall back to `POST /ask` (section 1.1). The backend is healthy as of
   section 3.3; the user-facing path is not. Options recorded, none applied:
   redeploy the frontend from this repository's `ui/`; set `DEBUG=true` on
   the backend (an operator decision that deliberately exposes a debug
   surface in production, against invariant A5's intent); or point the
   deployed frontend at `POST /ask` directly.

**Correctness and diagnosability**

2. **`estimated_cost` is `null` for `gemini-2.5-pro`, which nulls
   `total_estimated_cost`.** **VERIFIED** — the R7 payload records
   `estimated_cost: null` for the Gemini provider and
   `total_estimated_cost: null` overall, because
   `backend/app/core/orchestrator.py:127-128` nulls the total when any
   component cost is `None`. OpenAI is priced correctly. The pricing table
   has no entry for this Gemini model, so the product objective's
   "usage/cost metrics" requirement is only half met.
3. **`ui/client.py:96` discards the error body.** **VERIFIED** — the 404
   fallback calls `raise_for_status()` before reading the response, so a
   stage failure reaches the UI as `error_stage: "transport"` with a bare
   exception string (`ui/streamlit_app.py:138-140`), destroying the
   `error_stage` and provider message that made the section 3 diagnoses
   possible.
4. **`docs/15_API_CONTRACT.md:91` SSE documentation drift.** **VERIFIED** —
   the document shows SSE frames as `event: stage`; the implementation emits
   `progress` (`backend/app/api/service.py:83`) and the repository UI listens
   for `progress` (`ui/streamlit_app.py:127`). Code and UI agree; the
   document is stale.
5. **`google-genai` is unpinned and there is no lockfile.** **VERIFIED** —
   `backend/pyproject.toml:17` declares `google-genai>=0.3` with no upper
   bound; the image installs it at build time
   (`backend/Dockerfile:11`); the only tracked dependency files are
   `backend/pyproject.toml` and `ui/requirements.txt`. **UNKNOWN** — the
   version actually installed in the running image. This is the same
   unpinned-provenance weakness recorded for the embedding model in R-001.
6. **Surplus Railway resources pending cleanup.** **VERIFIED** — four
   non-canonical ION_MIVE projects (`glorious-compassion`,
   `lucid-forgiveness`, `ingenious-renewal`, `proud-laughter`) deploy the
   same repository, and **two Qdrant services** (`helpful-radiance`/`Qdrant`,
   `devoted-freedom`/`Qdrant`) run continuously while section 1.3 shows
   production uses neither. All are running or auto-deploying, and therefore
   consuming resources, with no established purpose. No deletion is proposed
   or authorised here — cleanup is an operator decision, and section 1.3's
   UNKNOWN about their contents must be resolved before anything is removed.

**Unresolved questions of fact**

7. **Auto-deploy configuration is inferred, not read.** **UNKNOWN** as
   configuration fact. The inference rests on **VERIFIED** observation: five
   projects recorded deployments of the same commits within ~2 seconds of one
   another (for example `0da3488e…` at `14:31:57.387Z`, `14:31:57.935Z`,
   `14:31:58.235Z`, `14:31:58.816Z`). The service Settings that would confirm
   deploy-on-push were not read.
8. **Streamlit Cloud configuration and secrets have never been inspected.**
   **UNKNOWN** — the app's backend URL setting, its secrets, its deployed
   branch/commit, and whether it points at the canonical backend at all.
9. **The origin of `proud-laughter` is unconfirmed.** **UNKNOWN** who created
   it, by what mechanism, and for what purpose. **VERIFIED** only that it did
   not exist during Mission R0 and was created at `2026-08-05T12:34:43.948Z`
   with an immediately failing RAILPACK deployment.
10. **`lucid-forgiveness`'s build failure reason.** **UNKNOWN** — its build
    logs were never fetched.
11. **Canonicity is derived from state, not from a prior operator decision.**
    **VERIFIED** facts (sole domain ownership, SUCCESS + RUNNING on the
    accepted baseline, and — since R7 — a proven working pipeline) support
    the designation; the designation itself remains an operator decision to
    confirm. **VERIFIED** — no repository document named any Railway project,
    service, or domain before this one; a workspace-wide search during R0
    returned no matches.
12. **Two local commits are unpushed.** **VERIFIED** — `5b36f948…` and
    `bbbefdd1…` exist only locally; `origin/main` is at `0da3488e…`. See
    section 7.

---

## 5. KEY LOCATIONS — where each credential is known to live

Purpose: a future credential rotation must update **every** location below,
or the system will fail in exactly the way section 3 records — one component
succeeding while another presents a stale credential.

**Names only. No value, length, prefix, suffix, or shape is recorded here or
anywhere in this document, and none may ever be added.**

### 5.1 Railway — canonical backend service — VERIFIED

Project `helpful-radiance` (`da1c44f6-…`) / service `ION_MIVE`
(`33fa65be-…`) / environment `production`. **VERIFIED** by a names-only
enumeration in Mission R2, with values filtered out inside the command
pipeline: **20 variables defined.** Those that carry or select credentials
and endpoints:

| Name | Role |
|---|---|
| `GEMINI_API_KEY` | Gemini credential — replaced 2026-08-05 (section 3.1) |
| `OPENAI_API_KEY` | OpenAI credential — replaced 2026-08-05 (section 3.2) |
| `VECTOR_STORE_API_KEY` | Qdrant Cloud credential |
| `VECTOR_STORE_URL` | Qdrant Cloud endpoint (external cluster, section 1.3) |
| `VECTOR_COLLECTION` | Qdrant collection name |
| `GEMINI_MODEL`, `OPENAI_MODEL` | model selectors, not credentials |

- **VERIFIED** — `GOOGLE_API_KEY`, `GOOGLE_APPLICATION_CREDENTIALS`,
  `GOOGLE_GENAI_USE_VERTEXAI`, `GOOGLE_CLOUD_PROJECT`,
  `GOOGLE_CLOUD_LOCATION`, `QDRANT_URL`, `QDRANT_API_KEY`,
  `QDRANT_COLLECTION`, and `DEBUG` are **absent**. The three `QDRANT_*`
  absences are correct, not a defect: this codebase reads
  `VECTOR_STORE_URL`, `VECTOR_STORE_API_KEY`, and `VECTOR_COLLECTION`
  (`backend/app/core/config.py:45-47`).
- **VERIFIED** — the backend never loads provider keys into application
  configuration. `Settings` has no key fields; `backend/app/config_check.py`
  checks presence and header-safety only, and the SDK clients are
  constructed with **no explicit key** (`backend/app/container.py:52-53` →
  `backend/app/modules/gemini_ive/backend.py:23`,
  `backend/app/modules/openai_ive/backend.py:22`), so both providers rely on
  SDK environment discovery. A wrong-type credential passes readiness and
  fails only at the provider call — exactly the section 3.1 failure mode.

### 5.2 Streamlit Cloud — frontend app configuration — OPERATOR-STATED

- **OPERATOR-STATED** — the frontend runs on Streamlit Cloud (section 1.1),
  and its configuration is a distinct place where settings and possibly
  secrets live.
- **VERIFIED** — the *repository* client requires exactly one setting,
  `BACKEND_URL`, and no provider credential (`ui/client.py:17-18`); the UI
  performs no provider, retrieval, or MIVE work.
- **UNKNOWN** — what the **deployed** app's configuration actually contains.
  Since the deployed app is **VERIFIED NEGATIVE** as not being built from
  this repository's `ui/` (section 1.1), its settings must not be assumed to
  match the repository's requirements. It has never been inspected.
- **Rotation note:** if the deployed app holds any provider or vector-store
  credential of its own, it is a rotation target. Whether it does is
  **UNKNOWN** and can only be answered by the operator inspecting the
  Streamlit Cloud app settings.

### 5.3 Local corpus tooling — `ION_CORPUS_v3` `.env` — OPERATOR-STATED

- **OPERATOR-STATED** — a `.env` under
  `Documents\Projects\ION_CORPUS_v3` holds credentials used by the corpus
  tooling, outside this repository.
- **UNKNOWN** — which names it defines. It has never been opened by any
  mission, and must not be: reading a secret file is denied outright by
  `.claude/settings.json` and is never an authorised step.
- **Rotation note:** ingestion writes to the same external Qdrant Cloud
  cluster production reads from (section 1.3), so a Qdrant credential
  rotation that misses this file will break ingestion while production
  continues to work — a silent divergence.

### 5.4 Local repository `.env` — VERIFIED to exist, contents never read

- **VERIFIED** — a `.env` file exists at this repository's root; evidence: a
  directory listing during R0. It is gitignored (`.gitignore` line 1) and
  has never been committed.
- **VERIFIED** — it is unreadable by any mission by design: `.claude/settings.json`
  denies `Read(.env)`, `Read(.env.*)`, `Read(**/secrets/**)`, `Read(**/*.key)`,
  and `Read(**/*.pem)` outright.
- **UNKNOWN** — which names it defines. `.env.example` is tracked and
  indicates the expected shape, but the live file's contents are not known.
- **Rotation note:** this file drives local Docker Compose runs. A rotation
  that updates Railway but not this file leaves local development pointing
  at revoked credentials.

---

## 6. Rule — Railway CLI usage in this workspace

- **VERIFIED** — the Railway CLI is currently linked, for this working
  directory, to **`glorious-compassion`** — which is **not** canonical
  production; evidence: `railway status --json` returns
  `name: glorious-compassion`, `id: 0a1046ba-17fd-4687-b9cd-64863763c611`.
- **Rule:** because of that link, **every** Railway command in this workspace
  must name its target explicitly:

  ```
  --project <PROJECT_ID>  --service <SERVICE_ID>  --environment production
  ```

  A bare `railway logs`, `railway status`, `railway variable list`, or
  `railway domain` silently targets `glorious-compassion` — the wrong
  project — and any conclusion drawn from such output is invalid.
- **Rule:** do **not** run `railway link`, `unlink`, or any project switch to
  work around this. Re-linking changes persistent local state and is an
  operator decision, not an automation step. Explicit flags achieve the same
  result with no state change.
- **Rule:** prefer `--json` output and read-only subcommands
  (`deployment list`, `domain list`, `logs`, `api <query>`). Note that a bare
  `railway domain` **creates** a domain — always use `railway domain list`.
- **Rule:** `railway api` may be used for **queries only**. No mutation
  document may be sent.
- **Rule — variables.** `railway variable list` prints raw values in both
  `--json` and `--kv` form. Variable **values must never be read**. A
  names-only enumeration (as in section 5.1) is permitted **only** when the
  command is built so that values are filtered out inside the pipeline before
  anything reaches stdout; if that cannot be guaranteed, the item is recorded
  as BLOCKED instead. Values must never be printed, hashed, or partially
  masked; where a secret would appear in copied output, replace the value
  with `[REDACTED_SECRET]` and keep the surrounding text.
- **Rule — live requests.** Calling `POST /ask` spends real provider money
  and is not a read-only action. Each live request requires its own explicit
  operator authorisation and is made exactly once, with no retry whatever the
  outcome.
- **Rule — capturing an error body on Windows PowerShell 5.1.**
  `Invoke-WebRequest` throws on a non-2xx response and exposes the body at
  `$_.ErrorDetails.Message`. Reading
  `$_.Exception.Response.GetResponseStream()` returns an already-consumed
  stream and yields nothing — which cost one authorised request in R4.

**Canonical target identifiers, for explicit use:**

```
--project da1c44f6-13ca-4ea2-bc0e-56bd3f531102   # helpful-radiance
--service 33fa65be-5b8e-4e0c-8277-ba43e05d7032   # ION_MIVE (backend)
--service 3a0c3a20-5dda-445f-8e29-13b0b524dce9   # Qdrant (same project, unused by production)
--environment production
```

---

## 7. Git state at the time of this revision

- **VERIFIED** — branch `main`; HEAD
  `bbbefdd1ae01d047c9c8cef24a68d92ea22bcea2` (*docs: record canonical system
  map and verified production target*); working tree clean before this
  revision was written; evidence: `git rev-parse`, `git status --porcelain`.
- **VERIFIED** — `origin` is `https://github.com/mureniada/ION_MIVE.git`, and
  remote `refs/heads/main` is live at
  `0da3488e056f018b04abc916b7e8e3a7097c1388`; evidence: `git ls-remote origin
  refs/heads/main` (non-mutating; no fetch performed).
- **VERIFIED** — local `main` is **2 commits ahead** of `origin/main`:
  `5b36f948…` (*chore: ignore Railway local link metadata*, a single
  `.gitignore` line) and `bbbefdd1…` (this document's first version).
- **VERIFIED** — consequently **every** Railway deployment recorded above
  runs `0da3488e…`, and no deployment anywhere runs local HEAD, which is
  unpushed. The two provider repairs in section 3 changed variables only;
  neither changed code.

---

## 8. What this document does not do

- It does not authorise any deployment, redeployment, repair, re-link,
  variable change, domain change, or deletion — including the surplus
  Railway resources in section 4 item 6.
- It does not resolve any item in section 4, and does not verify the
  Streamlit Cloud frontend beyond the negative finding in section 1.1.
- It does not certify that the external Qdrant Cloud cluster holds the
  6063-vector nine-book corpus; that remains UNKNOWN (section 1.3).
- It does not modify or reinterpret `CLAUDE.md`,
  `ION_MIVE_HANDOVER_INDEX.md`, or either handover document. Section 3.1
  supersedes `CLAUDE.md`'s "Gemini 401 is a separate, open deployment issue"
  as a matter of fact; updating that file is a separate, unauthorised task.
- It does not itself constitute a commit, push, tag, or release. Confirming
  the canonical designation recorded here remains an explicit operator
  decision.
