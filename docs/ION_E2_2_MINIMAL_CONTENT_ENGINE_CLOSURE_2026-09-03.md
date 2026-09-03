# ION E2.2 — Minimal Content Engine — Closure Receipt

**Date:** 2026-09-03
**Type:** Bounded-phase closure receipt
**Phase:** E2.2 — Minimal Content Engine (Content Pack -> derived record set)
**Contract:** `docs/ION_E2_2_MINIMAL_CONTENT_ENGINE_CONTRACT_v1.md`

This receipt records measured facts and operator decisions. It authorizes
nothing, closes no other issue, and rewrites no historical project-control
record.

---

## 1. Starting state

```
WORKTREE ROOT = .../ION_MIVE_CLEANROOM_PACK_v1/.claude/worktrees/e2-worktree-preflight-f4c803
BRANCH        = claude/e2-worktree-preflight-f4c803
STARTING HEAD = a640dfa810b00044e472980bb8602ded0b2a0c6c   ("E2.1: bind durable closure")
LOCAL REF     = e2-1-canonical-content-pack-20260903 -> a640dfa...

STATE AT START:  TRACKED DIFF = NONE   STAGED = NONE   UNTRACKED = NONE
```

Ancestry at the time of this phase:

```
7cf6ba5 (E1 closure) -> 1aad954 (E2.1 implementation) -> a640dfa (E2.1 closure)
```

---

## 2. E2.2 file set — six files, all newly created

```
backend/app/modules/content_engine/__init__.py
backend/app/modules/content_engine/models.py
backend/app/modules/content_engine/resolver.py
backend/app/modules/content_engine/engine.py
backend/tests/test_content_engine_resolver_v0_1.py
backend/tests/test_content_engine_build_v0_1.py
```

No other production or test file was created, modified, moved or deleted. Exact
byte counts and SHA-256 digests for these six, together with this receipt and the
contract document, are recorded in the E2.2D final report.

---

## 3. Architecture and reuse ruling

```
CONTENT ENGINE = THIN ORCHESTRATOR OVER EXISTING SUBSTRATE
DISPOSITION    = REUSE + NEW MINIMAL BOUNDARY   (Option C)
```

`retrieval.ingest.build_records` was NOT used as the Content Engine and remains
outside the orchestration boundary: it owns directory enumeration and mints
`source_id` from the filename via `_slug(path.stem)`, which conflicts with the
closed E2.1 rule that `source_id` is a declared logical identity. Routing through
it would have required modifying protected `retrieval/ingest.py`; no such
modification was made or needed.

Reused, unmodified:

```
retrieval.ingest._read_pages                   PRIVATE REUSE SEAM / NO OWNERSHIP TRANSFER
retrieval.chunker.chunk_text                   REUSED
retrieval.evidence_fingerprint                 REUSED
retrieval.source_provenance                    REUSED
retrieval.canonical_provenance_materializer    REUSED
```

The `_read_pages` seam was confirmed before use by direct inspection: importing
`retrieval.ingest` has no runtime side effect (module-level names are imports,
`INGESTION_VERSION`, and functions; `pypdf` stays lazy), the helper takes only a
`Path`, and it neither derives nor overrides `source_id`. Reused rather than
duplicated so that a second TXT/PDF reader could not silently drift from the one
the existing corpus was ingested with.

---

## 4. Source binding contract

```
source_bindings:  source_id -> relative POSIX source path
physical path:    source_root / relative_source_path
```

Fail-closed rules implemented and proved: exact key-set match; missing binding;
unexpected binding; duplicate physical binding; missing source root; invalid
source root; missing source file; non-file; absolute path; backslash path;
drive/scheme form; `.` segment; `..` traversal; empty or doubled segment;
source-root escape; symlink escape where the resolved path leaves the root.

Path segments are validated on the literal string split by `/`, not on
`PurePosixPath.parts` — the latter silently collapses `.` and doubled
separators, which would have admitted `./research/x.txt` and `research//x.txt`
as if written cleanly. A path needing normalization is refused, never normalized.

```
SOURCE ID      = DECLARED ContentPack source_id
SOURCE VERSION = DECLARED ContentPack source_version
SOURCE SHA256  = DECLARED ContentPack source_sha256
MEASURED HASH  = SHA256 OF COMPLETE RAW SOURCE FILE BYTES
```

Successful resolution requires `MEASURED == DECLARED`; no text normalization
participates. `_slug(path.stem)` is not Content Engine authority and is never
called.

---

## 5. Source-origin correction (E2.2C Correction 1)

The pre-correction rule `source_origin = corpus-file://<source_id>` was REJECTED
by the operator on the ground that `SOURCE IDENTITY != SOURCE ORIGIN`. The
implemented rule is now:

```
source_origin = "corpus-file://" + <relative-posix-source-path>
```

The URI is constructed by the engine; the caller supplies only a relative POSIX
path and cannot inject a prebuilt origin (a value containing `:` is refused
before reaching provenance). No absolute machine path enters Content Pack
identity, evidence fingerprint, provenance origin, or the ContentBuildResult
identity surface.

```
SOURCE ORIGIN != SOURCE IDENTITY
SOURCE ROOT   != CONTENT PACK IDENTITY
PHYSICAL PATH != SOURCE IDENTITY
```

Title rule bound alongside it: `record["title"] = declared source_id`, because
`title` sits inside the frozen fingerprint projection and Content Pack v0.1 has
no display-title field. Recorded as a deterministic technical title, not a human
display title. No Content Pack reopening was authorized or performed.

---

## 6. Explicit provenance time (E2.2C Correction 2)

```
provenance_created_at = EXPLICIT REQUIRED BUILD INPUT
```

Required keyword parameter with no default; supplied by the caller and taken
verbatim. No clock is read anywhere in the package — no `datetime.now`,
`utcnow`, `time.time`, UUID or random surrogate exists in it, and that absence is
asserted structurally by test. The frozen provenance contract validates the
RFC3339-UTC form (`Z` or `+00:00` only).

```
PROVENANCE CREATED AT != SOURCE CREATION TIME
PROVENANCE CREATED AT != PACK VERSION TIME
PROVENANCE CREATED AT != ACTIVATION TIME
```

It is this build's provenance-materialization time. Every successful record binds
the same supplied value, and `ContentBuildResult` refuses construction when any
record's provenance disagrees with the bound value. Provenance is mandatory
inside the engine — no parameter can turn it off — which closes the legacy
production omission by construction for this boundary.

---

## 7. ContentBuildResult — exact implemented fields

```
content_engine_contract_version
content_engine_version
pack_id
pack_version
pack_canonical_fingerprint
chunk_chars
overlap
provenance_created_at
records
```

Constants read from the final implementation:

```
CONTENT_ENGINE_CONTRACT_ID      = "ION_CONTENT_ENGINE_V0_1"
CONTENT_ENGINE_CONTRACT_VERSION = "0.1"
CONTENT_ENGINE_VERSION          = "0.1"
SUPPORTED_CONTRACT_VERSIONS     = ("0.1",)
DEFAULT_CHUNK_CHARS             = 1200
DEFAULT_OVERLAP                 = 200
```

Records carry a closed fourteen-key set (`RECORD_KEYS`), so no build-, index-,
embedding- or activation-shaped field can enter one. Zero-chunk law: a declared
source producing no chunk fails closed rather than disappearing from the output.

```
CONTENT BUILD RESULT != INDEX IDENTITY
CONTENT BUILD RESULT != ACTIVATION RECEIPT
```

---

## 8. Verification record

```
TARGETED E2.2 TESTS           = 47 PASS / 0 FAIL
STDLIB-RUNNER STYLE           = 47 RUN  / 0 FAIL
BOUNDED REGRESSION BASELINE   = 1219 PASS / 33 FAIL / 7 SKIP
BOUNDED REGRESSION POST-E2.2C = 1266 PASS / 33 FAIL / 7 SKIP
DELTA                         = +47 PASS / +/-0 FAIL / +/-0 SKIP
FAILURE SET DELTA             = NONE
NEW E2.2 REGRESSION           = NOT SUPPORTED
PROTECTED SURFACE CHANGE      = NONE
```

Commands, run from `backend/` with `ION_REPO_ROOT` set identically in baseline
and post-change runs:

```
python -m pytest tests/test_content_engine_resolver_v0_1.py \
                 tests/test_content_engine_build_v0_1.py -q --tb=short

python -m pytest -q --tb=no \
  --ignore=tests/test_production_canonical_materialization_wiring_v0_1.py
```

Failure-set identity was established by name, not by count: both `FAILED` line
sets were sorted and compared, and the comparison returned no differences.

Proof coverage: twelve resolver proofs, twenty-two build proofs, and the fourteen
additional correction proofs (source id versus origin distinctness; origin from
the relative path; absolute path and prebuilt URI both rejected; `..` traversal;
root escape; Windows drive/backslash forms; machine-root independence of origin
and fingerprint; declared id in every record; explicit required timestamp; no
clock; exact timestamp binding; deterministic repeat; and the absence of any
index or activation identity).

---

## 9. Preserved qualifications — recorded, not repaired

```
Q1 = OVERLAY-DEPENDENT COLLECTION BLOCKER
     tests/test_production_canonical_materialization_wiring_v0_1.py imports
     app.modules.retrieval.source_provenance_manifest, absent from this worktree
     PRE-EXISTING / NON-E2.2 / REPAIR NOT AUTHORIZED

Q2 = 33 CRLF BYTE-IDENTITY FAILURES
     core.autocrlf=true with .gitattributes pinning eol=lf only for
     /.gitattributes, /backend/t4/** and /rfc8785.txt
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

## 10. Protected surfaces

```
TRACKED DIFF = NONE
STAGED       = NONE
```

A tracked diff of NONE is the proof of non-mutation for every protected surface:

```
backend/app/modules/content_pack/*          UNCHANGED
backend/app/modules/retrieval/*             UNCHANGED
backend/app/modules/local_layer/*           UNCHANGED
backend/app/modules/evidence_provenance/*   UNCHANGED
backend/t4/*                                UNCHANGED
backend/app/ingest_cli.py                   UNCHANGED
Core.ask() / Core ports                     UNCHANGED
Session / TurnRecord / Adaptive Dialogue    UNCHANGED
GovernedEvidenceSet                         UNCHANGED
ModelContext / ModelGateway                 UNCHANGED
Execution Profile                           UNCHANGED
Qdrant semantics                            UNCHANGED
schemas/*                                   UNCHANGED

PROTECTED SURFACE CHANGE REQUIRED = NONE
CONTENT PACK MUTATION             = NONE
```

Every reuse was a read-only import.

---

## 11. Boundary

```
E2.2 QDRANT WRITE   = NONE
E2.2 EMBEDDING      = NONE
E2.2 INDEX IDENTITY = NONE

E2.3 = NOT STARTED / NOT AUTHORIZED
E3   = BLOCKED
```

E2.3 was not entered: no pack-to-derived-index identity, build fingerprint or
activation surface was designed, implemented, stubbed or reserved. The closed
`RECORD_KEYS` set and the closed result field set leave nowhere for one to
appear.

---

## 12. Repository movement

```
FILES MODIFIED (tracked)  = NONE
FILES CREATED (untracked) = EIGHT (six implementation/test + two documents)
STAGED                    = NONE
COMMIT                    = NONE
PUSH                      = NONE
BRANCH MOVEMENT           = NONE
HEAD                      = a640dfa810b00044e472980bb8602ded0b2a0c6c (unchanged)
```

---

## 13. Status

```
E2.2 IMPLEMENTATION = PASS
E2.2 VERIFICATION   = PASS
E2.2                = READY FOR EXACT COMMIT AUTHORIZATION
```
