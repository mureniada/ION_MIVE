"""Local Context Pack representation, carrying working-material provenance.

Why this exists rather than an extension of the shared builder
--------------------------------------------------------------
Mandate §7 asks that an existing Context Pack schema be extended minimally rather
than a competing one created. The shared `ContextPackBuilder` builds `ContextDocument`,
which has no provenance field, so provenance would be dropped on the way through.
Adding that field would mean editing `backend/app/core/models.py` — and the CLAUDE.md
freeze on application code is in force and was upheld by the operator on 2026-08-07.
So the provenance-carrying builder lives here instead. The departure is declared in
the phase report; this docstring is the in-code record of it.

What it does NOT depart from
----------------------------
The emitted pack validates against the canonical, *unmodified*
`schemas/context_pack.schema.json`, using the repository's own `validate_context_pack`.
That is possible because the canonical schema already declares
`"additionalProperties": true` on document items and leaves `metadata` unconstrained.
Top level stays exactly the canonical four keys, since the schema sets
`"additionalProperties": false` there. Pack ids use the same derivation as the shared
builder, so ids remain reproducible and comparable across the two.
"""

from __future__ import annotations

import hashlib
from typing import Any, Iterable

from ...core.errors import ContextPackError
from ...core.models import Evidence
from ...validation import validate_context_pack

# The nine elements mandate §7 requires to survive to the pack: eight provenance
# fields plus the fragment text itself (carried as the document's `content`).
PROVENANCE_FIELDS: tuple[str, ...] = (
    "material_id",
    "fragment_id",
    "title",
    "source_file",
    "version",
    "status",
    "authority",
    "approved_for_publication",
)


class LocalContextPackBuilder:
    """Builds a schema-valid Context Pack in which every document keeps its provenance."""

    def __init__(self, *, char_budget: int = 60000) -> None:
        self._char_budget = char_budget

    def build(
        self,
        question: str,
        evidence: Iterable[Evidence],
        *,
        registry_version: str,
        material_count: int,
        index_fingerprint: str,
    ) -> dict[str, Any]:
        evidence = list(evidence)
        if not evidence:
            raise ContextPackError("Cannot build a Context Pack with no evidence.")

        documents: list[dict[str, Any]] = []
        total_chars = 0
        truncated = False

        for item in evidence:
            if total_chars + len(item.content) > self._char_budget and documents:
                truncated = True
                break

            provenance = dict(item.metadata.get("provenance") or {})
            missing = [f for f in PROVENANCE_FIELDS if f not in provenance]
            if missing:
                raise ContextPackError(
                    f"evidence '{item.document_id}' is missing provenance field(s) {missing}; "
                    "a working material must stay labelled through the whole chain."
                )

            documents.append(
                {
                    "document_id": item.document_id,
                    "title": item.title,
                    "content": item.content,
                    "source": provenance["source_file"],
                    "chunk_id": item.chunk_id,
                    "provenance": provenance,
                }
            )
            total_chars += len(item.content)

        pack_id = "cp_" + hashlib.sha256(
            (question + "|" + "|".join(d["document_id"] for d in documents)).encode("utf-8")
        ).hexdigest()[:16]

        pack = {
            "context_pack_id": pack_id,
            "question": question,
            "documents": documents,
            "metadata": {
                "evidence_count": len(evidence),
                "included_documents": len(documents),
                "total_characters": total_chars,
                "char_budget": self._char_budget,
                "truncated": truncated,
                # local-layer additions (metadata is unconstrained in the schema)
                "registry_version": registry_version,
                "material_count": material_count,
                "index_fingerprint": index_fingerprint,
                "origin": "local_working_layer",
            },
        }

        # Same guarantee the shared builder gives: nothing leaves this module unvalidated.
        validate_context_pack(pack)
        return pack
