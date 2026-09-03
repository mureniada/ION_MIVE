# ION E2.1 — Canonical Generic Content Pack Identity Contract v1

**Date:** 2026-09-03
**Type:** Implemented contract record
**Status:** BOUND TO THE IMPLEMENTATION CREATED UNDER E2.1
**Scope:** Declared content identity only. This document states what the E2.1
code actually does. It authorizes nothing further and describes no future layer.

Every constant, pattern and literal below was read out of the final
implementation files, not composed for this document.

---

## 1. What a Content Pack is, and is not

A `ContentPack` is a **declared content identity** object for one immutable
release.

```
IT IDENTIFIES DECLARED CONTENT.
IT DOES NOT RETRIEVE, INGEST, INDEX OR ACTIVATE IT.
```

Boundaries the implementation keeps:

```
CONTENT PACK        != QDRANT
CONTENT PACK        != CONTEXT PACK
PACK IDENTITY       != INDEX IDENTITY
DIRECTORY CONTENTS  != DECLARED PACK CONTENTS
MEASURED IDENTITY   != UNVERIFIED DECLARATION
```

- **Not Qdrant.** No module in `app/modules/content_pack/` imports, names or
  needs a vector store. Pack identity is computable and verifiable with no
  Qdrant in existence.
- **Not a Context Pack.** A Context Pack is per-question and its id derives from
  the question; a Content Pack is per-release and its identity derives from
  declared source bytes alone.
- **Not an index identity.** No index fingerprint, embedding model, chunk id or
  point id has a field anywhere in this contract.
- **Not directory contents.** The objects accept an explicit inventory and
  cannot discover one. They never scan a directory, read the local material
  registry, open a source file, or invoke ingestion.

---

## 2. Canonical objects

```
SourceEntry =
(
  source_id,
  source_version,
  source_sha256
)

ContentPack =
(
  contract_version,
  pack_id,
  pack_version,
  sources,
  canonical_fingerprint
)
```

Both are frozen, keyword-only dataclasses. The declared field lists above are
exhaustive and are asserted as such by test.

Deliberately absent from `SourceEntry`, with no field to carry them: filesystem
path, filename, title, mtime, collection timestamp, operator or collector name,
byte length, chunk count, embedding model, Qdrant collection or point id,
activation state, retrieval score.

Deliberately absent from `ContentPack`: source directory, registry reference,
created-at timestamp, author, Qdrant collection, index fingerprint, embedding
model, chunk or point lineage, activation or publication state, dialogue or
execution profile binding.

---

## 3. Implemented constants

Read verbatim from the implementation.

`backend/app/modules/content_pack/identity.py`:

```
CANONICALIZATION_PROFILE        = "ION_CONTENT_PACK_CANONICALIZATION_PROFILE_V0_1"
CANONICALIZATION_PROFILE_ID     = "ION_JCS_V0_1"
CANONICALIZATION_IMPLEMENTATION = "t4.jcs.serialize"
FINGERPRINT_ALGORITHM           = "SHA256"
SOURCE_ENTRY_KEYS               = ("source_id", "source_version", "source_sha256")
PAYLOAD_KEYS                    = ("contract_version", "pack_id", "pack_version", "sources")
```

`backend/app/modules/content_pack/models.py`:

```
CONTENT_PACK_CONTRACT_ID     = "ION_CONTENT_PACK_V0_1"
CONTENT_PACK_CONTRACT_VERSION = "0.1"
SUPPORTED_CONTRACT_VERSIONS  = ("0.1",)
SOURCE_ID_PATTERN            = ^[a-z0-9][a-z0-9_]*$
UNGOVERNED_SOURCE_ID         = "unknown"
SOURCE_SHA256_ALGORITHM      = "SHA256"     (bound to FINGERPRINT_ALGORITHM)
SOURCE_SHA256_BASIS          = "COMPLETE_RAW_SOURCE_FILE_BYTES"
source_sha256 accepted shape = ^[0-9a-f]{64}$
```

Errors are module-local: `ContentPackError` (models) and
`ContentPackIdentityError` (identity), both `ValueError` subclasses. Neither
introduces a transport stage and neither is mapped onto the core error taxonomy.

---

## 4. Source inventory authority

```
SOURCE INVENTORY AUTHORITY = EXPLICIT DECLARED INVENTORY
```

The inventory is supplied by the caller. Directory enumeration is **not** pack
authority and no code path in this package can perform it. A Content Pack
therefore cannot silently acquire identity from whatever files happen to exist
in a directory.

Translating an authorized registry or corpus into `SourceEntry` values, and
reconciling declared identity against measured bytes on disk, is an **adapter
boundary that is deliberately absent at v0.1**.

---

## 5. Source identity

```
source_id = DECLARED LOGICAL IDENTITY
```

- Governed alphabet `^[a-z0-9][a-z0-9_]*$`, reused from the repository's
  existing registered-material precedent (`local_layer.registry` material ids).
- **Not** a filename-derived slug, **not** a Qdrant identity, **not** an
  absolute or relative filesystem path.
- The literal `"unknown"` is a non-identity and fails closed.
- Leading or trailing whitespace fails closed; nothing is trimmed or re-cased.

`source_version` is a declared, non-empty string with no surrounding
whitespace, taken verbatim.

---

## 6. Source byte identity

```
source_sha256 = SHA256 OF COMPLETE RAW SOURCE FILE BYTES
ALGORITHM     = SHA256
BASIS         = COMPLETE_RAW_SOURCE_FILE_BYTES
FORM          = 64 lowercase hexadecimal characters
```

No text normalization enters source-byte identity. Therefore:

```
same exact bytes  -> same source_sha256
any byte change   -> different source_sha256
```

Path, mtime, OS, Qdrant collection and ingestion state do not affect
`source_sha256`. The basis reuses the semantics already frozen in
`backend/app/modules/retrieval/source_provenance.py`; that module was read as
precedent and was not modified.

---

## 7. Canonical source ordering

```
canonical source order = LEXICOGRAPHIC BY source_id
```

- `source_id` values must be unique; a duplicate fails closed rather than
  resolving to a last-one-wins winner.
- The input sequence's own order carries no identity: two callers declaring the
  same inventory in different orders measure the same pack.
- The governed `source_id` alphabet is a subset of ASCII, so code-point order,
  UTF-16 code-unit order and byte order coincide on it. The ordering rule cannot
  be read two ways.
- `source_version` and `source_sha256` belong to each entry and do not
  participate in ordering.

---

## 8. Pack identity

```
PACK IDENTITY = ( pack_id, pack_version, canonical_fingerprint )

pack_id               = stable logical pack identity (declared)
pack_version          = operator-declared immutable release version
canonical_fingerprint = measured deterministic identity of the inventory
```

Consequence, enforced by construction and asserted by test: the same
`pack_id` + `pack_version` cannot lawfully stand over two different
fingerprints. Any material source change moves the fingerprint, so the
immutable release identity must move with it rather than silently covering new
content.

---

## 9. Canonical fingerprint

```
canonical_fingerprint = SHA256( canonical_bytes( payload ) )
```

The payload carries **exactly** four fields:

```
contract_version
pack_id
pack_version
sources
```

and each canonical source entry carries **exactly** three:

```
source_id
source_version
source_sha256
```

Sources are placed in lexicographic `source_id` order before serialization.

**Deliberately excluded from the payload**, with nowhere to enter: filesystem
path, mtime, created_at, operator name, Qdrant collection, Qdrant point ids,
chunk ids, embedding model, index identity, activation state. Those belong to
other lifecycle or derived-state layers. Their absence is asserted over the
serialized bytes by test, not left to review.

---

## 10. Canonicalization profile

```
CANONICALIZATION_PROFILE_ID     = "ION_JCS_V0_1"
CANONICALIZATION_IMPLEMENTATION = "t4.jcs.serialize"
```

This is an **internal deterministic-profile identity**. It names the byte rule
this repository commits to, so that a later change of implementation is a
visible profile change rather than a silent drift in identity.

```
EXTERNAL RFC 8785 CONFORMANCE CLAIM = NOT MADE
```

The bound serializer's own conformance surface
(`backend/tests/test_t4_rfc8785_conformance.py`) was executed as an E2.1
precondition and passed; that result is recorded in the closure receipt as a
precondition, not restated here as a standards claim.

Payload property names are fixed ASCII, which is the domain on which the bound
serializer's UTF-16 property-name ordering is unambiguous.

---

## 11. Worked example (measured, not illustrative)

Two sources declared in non-canonical order (`beta` before `alpha`), pack id
`ion_example_pack`, pack version `1.0.0`, with placeholder digests:

Canonical bytes (349 bytes, UTF-8, no BOM, no trailing newline):

```
{"contract_version":"0.1","pack_id":"ion_example_pack","pack_version":"1.0.0","sources":[{"source_id":"alpha","source_sha256":"aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa","source_version":"1.0.0"},{"source_id":"beta","source_sha256":"bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb","source_version":"2.0.0"}]}
```

Canonical fingerprint:

```
15831ea9a25eb58530eeff965a71db1a783aca7a058393ae1eba1b11563d5655
```

Note the two observable properties: the declared input order (`beta`, `alpha`)
does not survive into the payload — canonical order does — and property names
within each entry are serialized in the serializer's own sorted order, which is
not the field order in which the contract states them.

---

## 12. Construction semantics

```
ContentPack.create(...)
  = canonical ordering + measured fingerprint construction

Direct ContentPack(...) construction
  = must already satisfy canonical ordering
  = must revalidate the supplied fingerprint by recomputation

Unchecked externally supplied fingerprint = NOT PERMITTED
```

- `create` accepts the inventory in any order, orders it canonically, and
  measures the fingerprint itself. It exposes **no** `canonical_fingerprint`
  parameter, so there is no route through which an unverified identity could be
  introduced. Its parameters are exactly
  `{pack_id, pack_version, sources, contract_version}`.
- Direct construction accepts a fingerprint and **recomputes** it, requiring
  exact equality. A mismatch fails closed.
- Direct construction **refuses** a mis-ordered inventory rather than quietly
  reordering it, so canonical order remains a checked property of the object
  rather than an unobserved side effect. `create` is the ordering path for a
  caller holding an arbitrary sequence.

Fail-closed conditions, all asserted by test:

```
empty / whitespace-padded / non-string pack_id        -> FAIL CLOSED
empty / whitespace-padded / non-string pack_version   -> FAIL CLOSED
unsupported contract_version                          -> FAIL CLOSED
empty source inventory                                -> FAIL CLOSED
duplicate source_id                                   -> FAIL CLOSED
invalid or empty source_id                            -> FAIL CLOSED
source_id = "unknown"                                 -> FAIL CLOSED
empty source_version                                  -> FAIL CLOSED
source_sha256 not exactly 64 lowercase hex characters -> FAIL CLOSED
sources not supplied as a tuple of SourceEntry        -> FAIL CLOSED
non-canonical source order (direct construction)      -> FAIL CLOSED
fingerprint not matching recomputation                -> FAIL CLOSED
```

Nothing is trimmed, defaulted, deduplicated, reordered or coerced into a
legal-looking value.

---

## 13. Purity

```
NO filesystem access  during pack identity calculation
NO network access     during pack identity calculation
NO Qdrant access      during pack identity calculation
NO clock, UUID, random source or environment variable input
```

Proved by mechanism rather than by absence of error: structurally, over the
package's own source (import allowlist, relative imports confined to the
package, no `open()` call anywhere); and at runtime, with `builtins.open` and
`io.open` replaced by a raiser while the fingerprint is computed, under the
repository's `netguard` guard which denies cloud imports, outbound sockets and
cloud credentials.

---

## 14. Dependency ruling

```
app.modules.content_pack.identity -> t4.jcs.serialize
  = BOUNDED CANONICALIZATION DEPENDENCY ONLY

t4 -> app
  = PROHIBITED / UNCHANGED
```

Content Pack gains no authority over and no dependency on `t4.manifest`,
`t4.identity`, `t4.emitter`, T4 run records, T4 execution semantics, or T4
artifact roles. General `app -> t4` coupling is **not** authorized by this
contract. `backend/t4/*` is not modified.

---

## 15. What this contract does not establish

- It does not establish source-to-chunk-to-embedding-to-Qdrant-point lineage.
  That belongs to a later, separately authorized layer and is not stated,
  implied or reserved here.
- It does not define a persistence format, a JSON schema, a CLI, an emitter, a
  registry adapter, a directory scanner, or an activation state.
- It does not modify the frozen per-source Evidence provenance contract in
  `backend/app/modules/retrieval/source_provenance.py`, which was reused as
  semantic precedent only.
- It defines no Cassette, Content Engine, Pack Factory or Dialogue Profile
  surface, and does not reserve a field for one.
