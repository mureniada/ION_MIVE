# ION E2.2 — Minimal Content Engine Contract v1

**Date:** 2026-09-03
**Type:** Implemented contract record
**Status:** BOUND TO THE IMPLEMENTATION CREATED UNDER E2.2
**Scope:** Deterministic derived-record BUILD only. This document states what the
E2.2 code actually does. It authorizes nothing further and describes no later
layer.

Every constant, field name, signature and literal below was read out of the final
implementation, not composed for this document.

---

## 1. What the Content Engine is, and is not

```
IT BUILDS A DERIVED RECORD SET.
IT DOES NOT EMBED, WRITE, INDEX, VERIFY OR ACTIVATE.
```

```
CONTENT ENGINE = THIN ORCHESTRATOR OVER EXISTING SUBSTRATE
DISPOSITION    = REUSE + NEW MINIMAL BOUNDARY
```

Approved and implemented flow:

```
CANONICAL CONTENT PACK + SOURCE ROOT + SOURCE BINDINGS
        -> RESOLVE
        -> RAW-BYTE VERIFY
        -> READ
        -> CHUNK
        -> EVIDENCE FINGERPRINT
        -> MANDATORY SOURCE PROVENANCE
        -> CANONICAL PROVENANCE MATERIALIZATION
        -> CONTENT BUILD RESULT
        -> STOP BEFORE EMBEDDING / QDRANT
```

Boundaries kept:

```
CONTENT PACK      != DIRECTORY
CONTENT PACK      != QDRANT
SOURCE IDENTITY   != SOURCE ORIGIN
PHYSICAL PATH     != SOURCE IDENTITY
SOURCE ROOT       != CONTENT PACK IDENTITY
PACK IDENTITY     != INDEX IDENTITY
BUILD             != VERIFY != ACTIVATE
```

---

## 2. Input authority

```
ContentPack.sources = CANONICAL DECLARED SOURCE INVENTORY
SOURCE BINDINGS     = RUNTIME PHYSICAL RESOLUTION ONLY
SOURCE ROOT         = RUNTIME PHYSICAL ROOT ONLY
```

Neither `docs/CORPUS_REGISTER.md` nor `local_materials/registry.json` is Content
Engine authority; neither is read, parsed, or depended on. Directory enumeration
is not authority and no code path in this package performs it.

---

## 3. Source binding contract

```
source_bindings:  source_id -> relative POSIX source path
physical path:    source_root / relative_source_path
```

Example: `alpha -> research/alpha.pdf`, under a `source_root` supplied to the
build. Neither the root nor the resulting absolute path enters the Content Pack,
its canonical fingerprint, any record, any evidence fingerprint, or the build
result.

Fail-closed rules, all implemented and proved:

```
exact source-id key-set match       required
missing binding                     rejected
unexpected binding                  rejected
duplicate physical binding          rejected   (two ids -> one resolved file)
missing source root                 rejected
invalid source root (not a dir)     rejected
missing source file                 rejected
non-file (e.g. a directory)         rejected
absolute path                       rejected
backslash path                      rejected
drive-letter or scheme form         rejected
"." segment                         rejected
".." traversal                      rejected
empty / doubled path segment        rejected
source-root escape                  rejected
symlink escape (resolved outside)   rejected
```

Path segments are validated on the literal string split by `/`, not on
`PurePosixPath.parts`, because the latter silently collapses `.` and doubled
separators. A path that would need normalizing is refused, never normalized.
Escape is re-checked after resolution against the resolved root, which is what
makes symlink escape fail.

---

## 4. Source identity and byte verification

```
SOURCE ID       = DECLARED ContentPack source_id
SOURCE VERSION  = DECLARED ContentPack source_version
SOURCE SHA256   = DECLARED ContentPack source_sha256
MEASURED HASH   = SHA256 OF COMPLETE RAW SOURCE FILE BYTES
```

A source resolves only when `MEASURED SHA256 == DECLARED source_sha256`. On any
mismatch the whole build fails: there is no partially verified inventory and no
partial result.

No text normalization participates in source-byte identity — the file is read in
binary and digested. `retrieval.ingest._slug(path.stem)` is **not** Content
Engine authority and is never called.

Verified sources are returned in the Content Pack's own canonical order
(lexicographic by `source_id`, closed by E2.1). The binding mapping's iteration
order affects nothing.

`VerifiedSource` fields, as implemented:

```
source_id
source_version
source_sha256
relative_source_path
path                  (runtime only; enters no record and no result)
```

---

## 5. Source origin

```
source_origin = "corpus-file://" + <relative-posix-source-path>
```

The URI is constructed by the Content Engine. The caller supplies only the
relative POSIX path and can never inject a prebuilt origin — a value containing
`:` is refused as a scheme or drive letter before it reaches provenance.

```
source_origin != source_id
```

An absolute machine path enters none of: Content Pack identity, evidence
fingerprint, provenance origin, or the ContentBuildResult identity surface. The
same pack, the same relative layout and the same bytes therefore produce
identical provenance and identical fingerprints under any root, on any machine.

The frozen `retrieval.source_provenance` contract independently re-validates the
URI form of every origin the engine builds.

---

## 6. Title rule

```
record["title"] = declared source_id
```

`title` is inside the frozen seven-field evidence-fingerprint projection, and
Content Pack v0.1 has no independent display-title field. A filename- or
basename-derived title would therefore make evidence identity depend on what a
file happened to be called.

```
TECHNICAL TITLE != FUTURE HUMAN DISPLAY TITLE
```

No Content Pack reopening is authorized by this contract.

---

## 7. Provenance time

```
provenance_created_at = EXPLICIT REQUIRED BUILD INPUT
```

Required keyword parameter with **no default**. No clock read, no generated
timestamp: no `datetime.now`, `utcnow`, `time.time`, UUID or random surrogate
exists anywhere in the package. The value is supplied by the caller and taken
verbatim; the frozen provenance contract validates its RFC3339-UTC form (`Z` or
`+00:00` only).

Because the status is therefore always `KNOWN`, canonical provenance is
materialized for every record, with no optional branch.

```
PROVENANCE CREATED AT != SOURCE CREATION TIME
PROVENANCE CREATED AT != PACK VERSION TIME
PROVENANCE CREATED AT != ACTIVATION TIME
```

It is the provenance-materialization time of this Content Engine build. Every
successful record binds the same exact supplied value, and `ContentBuildResult`
refuses construction if any record's provenance disagrees with the bound value.

Provenance is MANDATORY inside the Content Engine, not an optional flag: no
parameter exists that could turn it off, so the legacy production omission
cannot be reproduced through this boundary.

---

## 8. Implemented constants

Read verbatim from `backend/app/modules/content_engine/models.py` and
`engine.py`:

```
CONTENT_ENGINE_CONTRACT_ID      = "ION_CONTENT_ENGINE_V0_1"
CONTENT_ENGINE_CONTRACT_VERSION = "0.1"
CONTENT_ENGINE_VERSION          = "0.1"
SUPPORTED_CONTRACT_VERSIONS     = ("0.1",)
DEFAULT_CHUNK_CHARS             = 1200
DEFAULT_OVERLAP                 = 200
```

Implemented signatures:

```
resolve_and_verify(pack, bindings, *, source_root) -> tuple[VerifiedSource, ...]

build_content(pack, bindings, *, source_root, provenance_created_at,
              collector=None, collected_at=None, collected_at_status="UNKNOWN",
              chunk_chars=1200, overlap=200) -> ContentBuildResult
```

Errors are module-local: `ContentEngineError(ValueError)`. No transport stage is
introduced and nothing is mapped onto the core error taxonomy.

---

## 9. Derived record — closed key set

Every record carries exactly these fourteen keys, no more and no fewer:

```
document_id
source_id
source_version
title
content
page
chunk_id
checksum
ingestion_version
evidence_fingerprint
evidence_fingerprint_algorithm
evidence_fingerprint_profile_id
ion_source_provenance
ion_canonical_provenance
```

`document_id` and `chunk_id` follow the repository's existing chunk-id
semantics, built from the DECLARED source id:

```
chunk_id = f"{source_id}::p{page_tag}::c{ordinal}"      page_tag = "all" when page is None
```

`checksum` equals the verified declared `source_sha256`. The closed key set is
what makes a build-, index-, embedding- or activation-shaped field impossible to
introduce into a record without failing construction.

---

## 10. ContentBuildResult

Exact implemented field set:

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

`pack_id`, `pack_version` and `pack_canonical_fingerprint` are carried verbatim
from the input pack and are never recomputed. `record_count`, `source_count` and
`source_ids` are derived conveniences exposed as properties, not identity fields.

```
CONTENT BUILD RESULT != INDEX IDENTITY
CONTENT BUILD RESULT != ACTIVATION RECEIPT
```

Explicitly absent, with no field to carry them: `build_id`, `build_fingerprint`,
`derived_set_fingerprint`, `index_id`, `index_fingerprint`, Qdrant collection
identity, embedding identity, embedding model identity, activation state,
activation timestamp, verification state, rollback identity, and `source_root`.
The prohibition is enforced against both the result field set and the record key
set, not merely asserted here.

---

## 11. Existing substrate reused

```
retrieval.ingest._read_pages                        PRIVATE REUSE SEAM /
                                                    NO OWNERSHIP TRANSFER
retrieval.chunker.chunk_text                        REUSED
retrieval.evidence_fingerprint                      REUSED
retrieval.source_provenance                         REUSED
retrieval.canonical_provenance_materializer         REUSED
```

No existing retrieval or local-layer module was modified. `_read_pages` was
reused rather than copied because a second TXT/PDF reader could silently drift
from the one the existing corpus was ingested with; its private-name status is an
accepted bounded v0.1 seam and transfers no ownership.

`retrieval.ingest.build_records` is **not** the Content Engine and remains
outside this orchestration boundary: it owns directory enumeration and derives
`source_id` from the filename, which conflicts with the closed E2.1 rule that
`source_id` is a declared logical identity.

---

## 12. Zero-chunk law

```
DECLARED SOURCE PRODUCING ZERO CHUNKS = FAIL CLOSED
```

A source declared in the canonical Content Pack may not silently disappear from
successful derived output.

---

## 13. Qdrant / embedding boundary

```
E2.2 QDRANT WRITE   = NONE
E2.2 EMBEDDING      = NONE
E2.2 INDEX IDENTITY = NONE

QDRANT = DERIVED RETRIEVAL REPRESENTATION
QDRANT != CONTENT AUTHORITY
```

The engine stops at the deterministic derived record set. Existing Qdrant write
and embedding behaviour remains downstream and untouched. E2.3 owns the next
boundary.

---

## 14. Determinism contract

For identical ContentPack, source-root-relative bindings, physical source bytes,
`chunk_chars`, `overlap`, `provenance_created_at` and implementation constants,
the semantic `ContentBuildResult` is deterministic.

Also bound:

- binding-map insertion order does not change output;
- a machine `source_root` change alone, with identical relative structure and
  identical bytes, alters neither the provenance origin nor any evidence
  fingerprint;
- no clock, no UUID, no randomness anywhere in the package.

No claim is made that two builds under different explicit
`provenance_created_at` values produce identical provenance objects — they do
not, and that is the point of binding the value.

---

## 15. What this contract does not establish

- No pack-to-derived-index identity, and no build or derived-set fingerprint.
  E2.3 owns that boundary.
- No verify / activate / rollback lifecycle. E3 owns that.
- No persistence format, JSON schema, CLI, emitter, registry adapter or
  directory scanner.
- No modification to the frozen provenance, fingerprint, chunker or ingestion
  contracts, all of which were reused unchanged.
- No Cassette, Content Pack reopening, or display-title field.
