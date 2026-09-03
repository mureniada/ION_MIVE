# ION E2.2 — Durable Closure Binding

**Date:** 2026-09-03
**Type:** Durable closure binding artifact
**Binds:** the already-established, already-verified E2.2 result

This artifact binds facts established in earlier phases. It establishes no new
fact, repairs nothing, claims nothing beyond E2.2, and rewrites no historical
project-control record.

---

## 1. Phase identity

```
PROJECT-CONTROL PHASE = E2.2 — MINIMAL CONTENT ENGINE
E2.2 STATUS           = IMPLEMENTED / VERIFIED / COMMITTED
```

Namespace note: `REPO-HANDOVER:E1` (thin-client compliance, repository-local
historical) and `PROJECT-CONTROL:E1` (Minimal Adaptive Dialogue Runtime Closure,
external) remain distinct and unmodified.

---

## 2. Implementation commit

```
IMPLEMENTATION COMMIT         = 3f7926d07970b28c60ac4f1c071574803ea1deec
IMPLEMENTATION PARENT         = a640dfa810b00044e472980bb8602ded0b2a0c6c
IMPLEMENTATION COMMIT SUBJECT = E2.2: add minimal content engine
IMPLEMENTATION FILE COUNT     = 8
WORKTREE                      = .../.claude/worktrees/e2-worktree-preflight-f4c803
BRANCH                        = claude/e2-worktree-preflight-f4c803
```

The parent is the E2.1 closure commit `a640dfa…` ("E2.1: bind durable closure"),
carried by the local ref `e2-1-canonical-content-pack-20260903`.

Bound committed paths:

```
backend/app/modules/content_engine/__init__.py
backend/app/modules/content_engine/engine.py
backend/app/modules/content_engine/models.py
backend/app/modules/content_engine/resolver.py
backend/tests/test_content_engine_build_v0_1.py
backend/tests/test_content_engine_resolver_v0_1.py
docs/ION_E2_2_MINIMAL_CONTENT_ENGINE_CLOSURE_2026-09-03.md
docs/ION_E2_2_MINIMAL_CONTENT_ENGINE_CONTRACT_v1.md
```

---

## 3. Bound committed blob identities

Carried verbatim from the E2.2E verified result. Not regenerated, not recomputed,
not altered.

| Path | Git blob OID | Bytes | Committed-content SHA-256 |
|---|---|---|---|
| `backend/app/modules/content_engine/__init__.py` | `20971d5b6aef3ef23581231fd172a5d5c56d047b` | 1973 | `1114be996539d6f32965f18a599e2ef3089ea1a44922c202a01cc8cb873be280` |
| `backend/app/modules/content_engine/models.py` | `6a36e04c23beba6ed94032dde5ea2a227ec4c591` | 14000 | `64a48984d80a24b9be012819431c8b5193f70800bfc6826407f101f6bea335d8` |
| `backend/app/modules/content_engine/resolver.py` | `3849ba6285bb9631ef30ea68182e69cf1b3999e0` | 9080 | `444b13a139833fc6cf34d769ec8cd94b8700370b406f7eef97772c380f5e56e3` |
| `backend/app/modules/content_engine/engine.py` | `6e70efa24ecc959f898c4c52708b6a80296d13c6` | 10217 | `9e0ac34158725cdc739f40baafab9b403370895faff3ce3ecbff99c59b749156` |
| `backend/tests/test_content_engine_resolver_v0_1.py` | `2265cdd7947f43eeebe6639b4de790297c5dd7fd` | 18610 | `b176b4c5d8027d709343de5856e4d7bbe9e5291550b048893878462b44936c07` |
| `backend/tests/test_content_engine_build_v0_1.py` | `f89cd75dc26275317727d569fe2d20db7b02a927` | 22523 | `633573a4033ca2104345b94668688ad4f0f50b418b5047043647ee91feacb470` |
| `docs/ION_E2_2_MINIMAL_CONTENT_ENGINE_CONTRACT_v1.md` | `e2db0b732de4fe72ec4abd22c9545f07aba298ab` | 12139 | `ba7ebd55404e37f3843b2282776824e768893492c34284aeba2b5a3f3d209927` |
| `docs/ION_E2_2_MINIMAL_CONTENT_ENGINE_CLOSURE_2026-09-03.md` | `b21d39efe5cb86a257c63370885eb2e4864a1643` | 11361 | `74795346cf3e73a4895a3a10c29c6c0e88d6c683f8d30114e36af1ab4ee705af` |

Committed bytes and committed SHA-256 equalled the pre-commit worktree values for
all eight files; no line-ending conversion occurred on this commit. These blob
identities are the durable content identities.

---

## 4. Bound architecture

```
CONTENT ENGINE        = THIN ORCHESTRATOR OVER EXISTING SUBSTRATE
DISPOSITION           = REUSE + NEW MINIMAL BOUNDARY

INPUT AUTHORITY       = ContentPack.sources
SOURCE ROOT           = RUNTIME ONLY / NOT IDENTITY
SOURCE BINDING        = source_id -> relative POSIX source path
SOURCE IDENTITY       = DECLARED / PRESERVED
SOURCE VERSION        = DECLARED / PRESERVED
SOURCE ORIGIN         = corpus-file://<relative-posix-source-path>
SOURCE BYTE VERIFY    = SHA256 OF COMPLETE RAW SOURCE FILE BYTES
PROVENANCE            = MANDATORY
PROVENANCE_CREATED_AT = EXPLICIT BUILD INPUT / NO CLOCK
CONTENT BUILD RESULT  = VALIDATED

E2.2 OUTPUT           = DETERMINISTIC DERIVED RECORD SET + BUILD METADATA
QDRANT WRITE          = NONE
EMBEDDING             = NONE
INDEX IDENTITY        = NONE
```

Full semantics: `docs/ION_E2_2_MINIMAL_CONTENT_ENGINE_CONTRACT_v1.md`.

---

## 5. Bound architectural laws

```
CONTENT PACK          != DIRECTORY
CONTENT PACK          != QDRANT
CONTENT PACK          != CONTEXT PACK
SOURCE IDENTITY       != SOURCE ORIGIN
PHYSICAL PATH         != SOURCE IDENTITY
SOURCE ROOT           != CONTENT PACK IDENTITY
PACK IDENTITY         != INDEX IDENTITY
CONTENT BUILD RESULT  != INDEX IDENTITY
CONTENT BUILD RESULT  != ACTIVATION RECEIPT
BUILD                 != VERIFY != ACTIVATE
```

---

## 6. Bound reused substrate

```
retrieval.ingest._read_pages                   PRIVATE REUSE SEAM /
                                               NO OWNERSHIP TRANSFER
retrieval.chunker.chunk_text                   REUSED
retrieval.evidence_fingerprint                 REUSED
retrieval.source_provenance                    REUSED
retrieval.canonical_provenance_materializer    REUSED
retrieval.ingest.build_records                 NOT CONTENT ENGINE
```

No existing retrieval or local-layer module was modified. `build_records` remains
outside the orchestration boundary because it owns directory enumeration and
mints `source_id` from the filename, which conflicts with the closed E2.1 rule
that `source_id` is a declared logical identity.

---

## 7. Bound fail-closed source resolution

```
exact binding key-set match          required
missing binding                      rejected
unexpected binding                   rejected
duplicate physical binding           rejected
invalid / missing source root        rejected
missing or non-file source           rejected
absolute path                        rejected
backslash path                       rejected
drive / scheme path                  rejected
"." segment                          rejected
".." traversal                       rejected
empty path segment                   rejected
source-root escape                   rejected
symlink escape (resolved outside)    rejected
raw source SHA-256 mismatch          rejected
zero-chunk declared source           rejected
```

---

## 8. Bound title rule

```
record["title"] = declared source_id

CLASSIFICATION = TECHNICAL DETERMINISTIC TITLE v0.1
NOT            = human display-title authority
```

Reason: Content Pack v0.1 contains no independent title field, and `title` is
part of the existing evidence-fingerprint projection, so a filename- or
basename-derived title would make evidence identity depend on what a file
happened to be called.

---

## 9. Bound temporal semantics

```
provenance_created_at = EXPLICIT REQUIRED BUILD INPUT

absent everywhere in the package:
  datetime.now   utcnow   time.time   UUID   random

PROVENANCE CREATED AT != SOURCE CREATION TIME
PROVENANCE CREATED AT != PACK VERSION TIME
PROVENANCE CREATED AT != ACTIVATION TIME
```

It is the provenance-materialization time of this Content Engine build, supplied
by the caller and taken verbatim. Every successful record binds the same exact
value, and `ContentBuildResult` refuses construction when any record disagrees.

---

## 10. Bound verification

```
TARGETED E2.2 TESTS          = 47 PASS / 0 FAIL
STDLIB-RUNNER STYLE          = 47 RUN  / 0 FAIL
BOUNDED REGRESSION BASELINE  = 1219 PASS / 33 FAIL / 7 SKIP
BOUNDED REGRESSION POST-E2.2 = 1266 PASS / 33 FAIL / 7 SKIP
DELTA                        = +47 PASS / +/-0 FAIL / +/-0 SKIP
FAILURE SET DELTA            = NONE
NEW E2.2 REGRESSION          = NOT SUPPORTED
PROTECTED SURFACE CHANGE     = NONE
```

Failure-set identity was established by name, not by count: both `FAILED` line
sets were sorted and compared, and the comparison returned no differences.

---

## 11. Preserved qualifications — recorded, not repaired

```
Q1 = OVERLAY-DEPENDENT COLLECTION BLOCKER
     PRE-EXISTING / NON-E2.2 / REPAIR NOT AUTHORIZED

Q2 = 33 CRLF BYTE-IDENTITY FAILURES
     PRE-EXISTING / NON-E2.2 / FAILURE SET DELTA = NONE / REPAIR NOT AUTHORIZED

Q3 = ION_REPO_ROOT ENVIRONMENT REQUIREMENT
     REPOSITORY MUTATION = NONE
```

The four pre-existing main-worktree overlay files —
`backend/app/modules/admission/receipts.py`,
`backend/app/modules/retrieval/source_provenance_manifest.py`,
`backend/t4/contract/STATUS.md`, `schemas/ion_evidence_record_v0.1.schema.json` —
remain **NOT ADMITTED / NOT READ / UNTOUCHED / NON-E2.2**.

---

## 12. Protected surfaces

The implementation commit adds files only and modifies none. Unchanged:

```
backend/app/modules/content_pack/*          backend/t4/*
backend/app/modules/retrieval/*             backend/app/ingest_cli.py
backend/app/modules/local_layer/*           Core / Core ports / RetrievalPort
backend/app/modules/evidence_provenance/*   Session / TurnRecord / Adaptive Dialogue
GovernedEvidenceSet                         ModelContext / ModelGateway
Execution Profile                           Qdrant semantics
schemas/*

PROTECTED SURFACE CHANGE REQUIRED = NONE
CONTENT PACK MUTATION             = NONE
```

---

## 13. E2.2 boundary

```
CONTENT PACK IDENTITY          = E2.1 / CLOSED
CONTENT ENGINE                 = E2.2 / IMPLEMENTED
PACK <-> DERIVED INDEX IDENTITY = NOT IMPLEMENTED
QDRANT BUILD BINDING           = NOT IMPLEMENTED
INDEX FINGERPRINT              = NOT IMPLEMENTED
ACTIVATION                     = NOT IMPLEMENTED
ROLLBACK                       = NOT IMPLEMENTED

E2.3 = NOT STARTED / NOT AUTHORIZED
E3   = BLOCKED
```

No claim beyond E2.2 is made by this artifact. The closed `RECORD_KEYS` set and
the closed `ContentBuildResult` field set leave nowhere for an index, embedding
or activation identity to appear.

---

## 14. Binding status

```
PROJECT-CONTROL:E2.2   = CLOSED / DURABLE / LOCALLY REFERENCED
MINIMAL CONTENT ENGINE = CLOSED / VERIFIED / DURABLE
CONTENT PLANE STATE    = E2.1 + E2.2 CLOSED
PUSH                   = NONE
```

The local named ref `e2-2-minimal-content-engine-20260903` points at the commit
that carries this artifact. Ancestry:

```
7cf6ba52557dd92c3f4c96a7edbdfbe9ade4d169   (E1 closure)
  -> 1aad954af565b7a5b4bdb40e65edcc07b87b583a   (E2.1 implementation)
    -> a640dfa810b00044e472980bb8602ded0b2a0c6c   (E2.1 closure)
      -> 3f7926d07970b28c60ac4f1c071574803ea1deec   (E2.2 implementation)
        -> this closure-binding commit
```

No remote operation was performed at any point in E2.1 or E2.2.
