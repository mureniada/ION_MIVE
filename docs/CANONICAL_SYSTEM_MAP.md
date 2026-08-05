# Canonical System Map — ION MIVE

**Date:** 2026-08-05
**Produced by:** Mission R1 (record and reconcile the canonical system map),
following the read-only Mission R0 audit.
**Type:** Factual system map. This document records state; it does not
authorise any change, deployment, or scope expansion.

## How to read this document

Every substantive line carries exactly one marker:

| Marker | Meaning |
|---|---|
| **VERIFIED** | Established by a read-only command executed during R0 or R1, with the evidence named on the line. |
| **OPERATOR-STATED** | Asserted by the operator. Not verified by R0 or R1. Recorded as provenance, not as proof. |
| **UNKNOWN** | Not established. Must not be treated as true, false, or "probably" either way. |

An **UNKNOWN** must never be upgraded to a fact without new evidence and a
new recorded verification. Absence of evidence is recorded as UNKNOWN, not
as a negative finding.

**Evidence base.** All VERIFIED lines rest on read-only Railway CLI and
Railway public GraphQL **query** calls (`railway list`, `railway status`,
`railway deployment list`, `railway domain list`, `railway logs --build`,
`railway api <query>`) and read-only Git commands (`git rev-parse`,
`git status`, `git show --stat`, `git ls-remote`). No mutation, deployment,
variable read, or endpoint call was performed in R0 or R1.

---

## 1. Canonical system — the four components

### 1.1 Frontend — Streamlit Cloud

- **OPERATOR-STATED** — the frontend is a Streamlit Cloud application at
  `ionmive-jwvwqwat7jukzvvnqvvpkq.streamlit.app`.
- **UNKNOWN** — whether that app is currently reachable, which backend URL
  it targets, which commit or branch it serves, and how it is configured.
  Mission R1 was forbidden from calling the Streamlit app, so nothing about
  its live behaviour was observed.
- **UNKNOWN** — Streamlit Cloud configuration and secrets. These have never
  been inspected by any mission in this workspace and must not be assumed to
  match the repository's `ui/` code or the backend contract.
- **VERIFIED** — a Streamlit thin client exists in this repository under
  `ui/`, committed as `11b7056` (2026-07-14); evidence:
  `ION_MIVE_HANDOVER_INDEX.md` section 5 (E1 closure record). This verifies
  the repository content only — **UNKNOWN** whether the deployed Streamlit
  Cloud app is built from that code.

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
- **VERIFIED** — latest deployment `075f0dac-4c0e-425b-a1f9-18154324ef30`,
  status **SUCCESS**, created `2026-08-04T14:31:58.235Z`, instance status
  **RUNNING**, `deploymentStopped: false`; evidence:
  `railway deployment list --json` and a `railway api` GraphQL query of
  `activeDeployments { status deploymentStopped instances { status } }`.
- **VERIFIED** — deployed commit
  **`0da3488e056f018b04abc916b7e8e3a7097c1388`**
  (*docs: repair automation bootstrap state and guardrails*) — the accepted
  baseline; evidence: `deployment.meta.commitHash`.
- **VERIFIED** — owns the domain **`ionmive-production.up.railway.app`**
  (domain id `eaf29cba-c7ba-48e5-8037-0c8aed2588b8`, type `service`,
  `targetPort` 8000, `syncStatus` ACTIVE, created 2026-07-15T00:02:14Z);
  evidence: `railway domain list --json`, run per service across every
  project in the account. It is the **only** ION_MIVE service in the account
  that owns any domain.
- **VERIFIED** — start command recorded on the equivalent service in the
  linked project is
  `/bin/sh -c "exec uvicorn app.main:app --host 0.0.0.0 --port $PORT"`;
  evidence: `railway status --json` (glorious-compassion). **UNKNOWN** —
  whether `helpful-radiance`'s ION_MIVE service uses the identical start
  command; its start command was not separately read.

### 1.3 Vector store — Qdrant

- **VERIFIED** — a Qdrant service exists **inside `helpful-radiance`**:
  service `Qdrant` (`3a0c3a20-5dda-445f-8e29-13b0b524dce9`), source image
  `qdrant/qdrant`, `numReplicas` 1, latest deployment
  `9109b9c9-67fd-427c-af24-fe7e1a49cc96` **SUCCESS**
  (2026-07-15T01:18:33.178Z), instance **RUNNING**, domain
  `qdrant-production-26ee.up.railway.app` (ACTIVE); evidence:
  `railway api` GraphQL query + `railway domain list --json`.
- **VERIFIED** — a **second, separate** Qdrant exists in project
  **`devoted-freedom`** (`8827b1c3-780d-43a1-a540-e802ca0e8803`), service
  `Qdrant` (`e81eca6c-4a02-4d71-bc8e-45b639b82863`), source image
  `qdrant/qdrant`, `numReplicas` 1, latest deployment
  `cd19492a-90bf-4c8b-b1fe-1537435d04bc` **SUCCESS**
  (2026-07-15T01:06:43.411Z), instance **RUNNING**, domain
  `qdrant-production-359b.up.railway.app` (ACTIVE); evidence: same commands.
  `devoted-freedom` contains **no** ION_MIVE service.
- **UNKNOWN — WHICH QDRANT HOLDS THE 6063-VECTOR NINE-BOOK CORPUS IS NOT
  ESTABLISHED.** Both instances are running and both are reachable in
  principle. Determining which one the canonical backend actually uses would
  require reading service variables (forbidden in R0/R1) or calling a
  Qdrant/backend endpoint (forbidden in R0/R1). Neither was done.
- **VERIFIED** — the 6063-vector figure itself originates from the
  clean-environment ingestion record: `chunks created: 6063`;
  `unique chunk_ids: 6063`; `qdrant vectors: 6063`; 9 source files, 0 failed;
  evidence: `ION_MIVE_HANDOVER_INDEX.md` section 7 (criterion A1). That
  record describes a **local, ephemeral** ingestion — **UNKNOWN** whether
  either Railway Qdrant instance contains that same data.

### 1.4 Corpus tooling

- **OPERATOR-STATED** — corpus tooling lives in a separate local folder,
  `Documents\Projects\ION_CORPUS_v3`, outside this repository.
- **UNKNOWN** — its contents, its version, its relationship to the 6063-vector
  ingestion, and whether it produced the data in either Railway Qdrant. It was
  not read by this mission; it is outside this repository's working directory.
- **VERIFIED** — this repository does not track raw corpus source: `.gitignore`
  excludes `corpus/source/` with the note that it is private/copyrighted
  material; evidence: repository `.gitignore`.

---

## 2. Non-canonical deploy targets

**VERIFIED** — the GitHub repository `mureniada/ION_MIVE`, branch `main`, is
connected to **five** separate Railway projects. All five deployed the same
commit `0da3488e…`. Only `helpful-radiance` owns a domain, and only
`helpful-radiance` pairs a successful backend with a Qdrant service in the
same project. Evidence: `railway list --json`, plus per-project
`railway deployment list --json` and `railway domain list --json`.

| Project | Project ID | Service ID | Builder / dockerfilePath | Latest deployment | Commit | Domain |
|---|---|---|---|---|---|---|
| **helpful-radiance** (canonical) | `da1c44f6-…` | `33fa65be-…` | DOCKERFILE / `backend/Dockerfile` | `075f0dac-…` **SUCCESS**, RUNNING | `0da3488e…` | **`ionmive-production.up.railway.app`** |
| glorious-compassion | `0a1046ba-…` | `1ec222ae-…` | DOCKERFILE / `/backend/Dockerfile` | `aeecc409-…` SUCCESS, RUNNING | `0da3488e…` | none |
| lucid-forgiveness | `f08bdde9-…` | `b19010d5-…` | DOCKERFILE / `/backend/Dockerfile`, rootDirectory `backend` | `0197e6fd-…` FAILED | `0da3488e…` | none |
| ingenious-renewal | `14b51361-…` | `8a83182f-…` | RAILPACK / *(none)* | `84787f77-…` FAILED | `0da3488e…` | none |
| proud-laughter | `e3beb2f8-…` | `22b87be3-…` | RAILPACK / *(none)* | `3f216cf6-…` FAILED | `0da3488e…` | none |

Why each is **not** production:

- **`glorious-compassion`** — **VERIFIED** the backend container is SUCCESS and
  RUNNING on `0da3488e…`, but it owns **no domain**, so nothing external can
  reach it, and the project contains **no Qdrant service**. **VERIFIED** it is
  also the project the local CLI is linked to (see section 4). **VERIFIED** its
  history shows it ran on RAILPACK and failed every build until a DOCKERFILE
  builder was configured between 2026-08-04 10:36 and 11:18 local time.
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
  it and why (see section 3).
- **`devoted-freedom`** — **VERIFIED** it is not a repo deploy target at all:
  it contains only the `Qdrant` image service described in section 1.3, with
  no ION_MIVE service and no GitHub source.

---

## 3. UNKNOWN — explicitly unresolved

Nothing in this section may be treated as settled.

1. **Live HTTP health is unverified.** **UNKNOWN** whether
   `ionmive-production.up.railway.app` currently answers `GET /health` with
   HTTP 200, or serves `POST /ask` correctly. R0 and R1 were forbidden from
   calling `/health`, `/ask`, and `/ask/stream`. "RUNNING" is Railway's
   reported container-instance status, **not** a proven HTTP response.
2. **The Gemini 401 error is unresolved.** **UNKNOWN** cause and current
   state. It remains a separate, open deployment issue (per `CLAUDE.md`).
   Investigating it requires reading Variables/credentials, which is
   forbidden; no such read was performed.
3. **Qdrant identity is unresolved.** **UNKNOWN** which of the two running
   Qdrant instances (`helpful-radiance` or `devoted-freedom`) holds the
   6063-vector nine-book corpus, and **UNKNOWN** which one the canonical
   backend is configured to use.
4. **Auto-deploy configuration is inferred, not read.** **UNKNOWN** as
   configuration fact. The inference rests on **VERIFIED** observation: five
   projects recorded deployments of the same commits within ~2 seconds of one
   another (for example `0da3488e…` at `14:31:57.387Z`, `14:31:57.935Z`,
   `14:31:58.235Z`, `14:31:58.816Z`). The service Settings that would confirm
   deploy-on-push were not read.
5. **Streamlit Cloud configuration and secrets have never been inspected.**
   **UNKNOWN** — the app's backend URL setting, its secrets, its deployed
   branch/commit, and whether it points at the canonical backend at all.
6. **The origin of `proud-laughter` is unconfirmed.** **UNKNOWN** who created
   it, by what mechanism, and for what purpose. **VERIFIED** only that it did
   not exist during Mission R0 and was created at `2026-08-05T12:34:43.948Z`
   with an immediately failing RAILPACK deployment.
7. **No repository document previously named any Railway project, service, or
   domain.** **VERIFIED** by a workspace-wide search during R0 for `R0`/`R1`/
   `R2`, "canonical production", and "ionmive-production", which returned no
   matches. This document is the first such record; it reflects observed
   state, **not** a previously recorded operator designation.
8. **Canonicity here is derived from state, not from a prior operator
   decision.** **VERIFIED** facts (sole domain ownership, SUCCESS + RUNNING on
   the accepted baseline, co-located Qdrant) support the designation; the
   designation itself remains an operator decision to confirm.

---

## 4. Rule — Railway CLI usage in this workspace

- **VERIFIED** — the Railway CLI is currently linked, for this working
  directory, to **`glorious-compassion`** — which is **not** canonical
  production; evidence: `railway status --json` returns
  `name: glorious-compassion`, `id: 0a1046ba-17fd-4687-b9cd-64863763c611`.
- **Rule:** because of that link, **every** Railway command in this workspace
  must name its target explicitly:

  ```
  --project <PROJECT_ID>  --service <SERVICE_ID>  --environment production
  ```

  A bare `railway logs`, `railway status`, `railway variables`, or
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
- **Rule:** service Variables must not be read. Secret values must never be
  printed, hashed, or partially masked; where a secret would appear in copied
  output, replace the value with `[REDACTED_SECRET]` and keep the surrounding
  text.

**Canonical target identifiers, for explicit use:**

```
--project da1c44f6-13ca-4ea2-bc0e-56bd3f531102   # helpful-radiance
--service 33fa65be-5b8e-4e0c-8277-ba43e05d7032   # ION_MIVE (backend)
--service 3a0c3a20-5dda-445f-8e29-13b0b524dce9   # Qdrant (same project)
--environment production
```

---

## 5. Git state at the time of writing

- **VERIFIED** — branch `main`; HEAD
  `5b36f948a5eb96c0f4f3f228886b071361f27253` (*chore: ignore Railway local
  link metadata*); working tree clean before this file was created; evidence:
  `git rev-parse`, `git status --porcelain`.
- **VERIFIED** — `origin` is `https://github.com/mureniada/ION_MIVE.git`, and
  remote `refs/heads/main` is live at
  `0da3488e056f018b04abc916b7e8e3a7097c1388`; evidence: `git ls-remote origin
  refs/heads/main` (non-mutating; no fetch performed).
- **VERIFIED** — local `main` is **1 commit ahead** of `origin/main`.
  `0da3488e…` is the direct parent of HEAD, and HEAD's only content change is
  a single `.gitignore` line (`.railway/`); evidence: `git rev-list --count`,
  `git show --stat`.
- **VERIFIED** — consequently **every** Railway deployment recorded above runs
  `0da3488e…`, and no deployment anywhere runs local HEAD `5b36f948…`, which
  is unpushed.

---

## 6. What this document does not do

- It does not authorise any deployment, redeployment, repair, re-link,
  variable change, domain change, or deletion.
- It does not resolve the Gemini 401 issue, the Qdrant identity question, or
  any other item in section 3.
- It does not verify the Streamlit Cloud frontend or any live HTTP behaviour.
- It does not modify or reinterpret `CLAUDE.md`,
  `ION_MIVE_HANDOVER_INDEX.md`, or either handover document.
- It does not itself constitute a commit, push, tag, or release. Confirming
  the canonical designation recorded here remains an explicit operator
  decision.
