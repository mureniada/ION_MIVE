# Local working materials

Working space for **new** ION material — Adaptive Dialogue concepts, ION definitions,
research notes, interpretations, hypotheses, drafts.

This layer is entirely local. It never contacts Qdrant Cloud, never uploads anything, never
touches the protected books, and never publishes. The protected corpus and this working
material are kept apart on purpose: material here is draft by default and must not be
presented as an approved ION position.

## Layout

```
local_materials/
  registry.json        the admission gate — the only thing that makes a file usable
  documents/           source material
  .index/              generated lexical index (derived data, git-ignored)
```

## Registering a material

A file in `documents/` is invisible to the system until a record names it in
`registry.json`. Dropping a file in the folder does nothing on its own — it is reported as
unregistered and skipped.

Every record needs all eight fields:

```json
{
  "id": "adaptive_dialogue_intro",
  "title": "Adaptive Dialogue — Working Definition",
  "source_file": "adaptive_dialogue_intro.md",
  "version": "0.1.0",
  "status": "draft",
  "authority": "working_material",
  "retrieval_enabled": true,
  "approved_for_publication": false
}
```

- `status` — `draft` | `review` | `approved`
- `authority` — `working_material` | `reference` | `canonical`
- `retrieval_enabled` — `false` keeps a registered material out of retrieval entirely
- `approved_for_publication` — leave `false` unless the operator has actually approved it

New material should start at `draft` / `working_material` / not approved. Do not raise these
values to record an intention; raise them only to record a decision that was actually taken.

The contract is `schemas/local_material_registry.schema.json`. Unknown fields, duplicate ids,
missing fields and wrong types are all rejected, and the error names the material and the
field.

## Policy: a missing source file fails fast

If a record names a file that is not on disk, loading raises `MissingSourceFileError` and
nothing is processed. It does **not** skip the record and carry on.

The reason is that a registry entry is a claim that the file exists. Skipping a broken claim
would let the working corpus silently shrink — retrieval would keep answering, just from less
material than anyone thought, with no signal that anything was missing. Failing loudly keeps
the registry and the disk honest with each other. This applies even when
`retrieval_enabled` is `false`.

## Provenance

Every fragment cut from a material carries its `material_id`, `fragment_id`, `title`,
`source_file`, `version`, `status`, `authority` and `approved_for_publication` from the moment
it is cut, all the way into the Context Pack. Draft material stays visibly labelled as draft
at every stage — the label is never something a later stage has to look up and reattach.

## The index is derived data

`.index/` is generated and git-ignored. It can be deleted at any time and rebuilt from
`registry.json` and `documents/` alone; deleting and rebuilding leaves both untouched and
produces an identical ranking.

```python
from app.modules.local_layer.pipeline import build_index, delete_index, run_control_question

delete_index()                 # remove the derived index
build_index(persist=True)      # rebuild it from source material and registry
run_control_question()         # the Phase 1 acceptance scenario
```

Run from `backend/`. Tests live in `backend/tests/test_local_*.py`; the isolation harness they
use is `backend/tests/netguard.py`.
