"""Canonical Context Pack builder (ContextPackBuilderPort).

No reasoning happens here (docs/04). Document identifiers are taken straight from
retrieval and remain stable through IVE and MIVE. Size is measurable; truncation,
if needed to fit the character budget, is explicit and recorded in metadata.
Provider-specific prompt content is never stored in the pack.
"""

from __future__ import annotations

import hashlib

from ...core.errors import ContextPackError
from ...core.models import ContextDocument, ContextPack, Evidence
from ...validation import validate_context_pack


class ContextPackBuilder:
    def __init__(self, *, char_budget: int = 60000) -> None:
        self._char_budget = char_budget

    def build(self, question: str, evidence: list[Evidence]) -> ContextPack:
        if not evidence:
            raise ContextPackError("Cannot build a Context Pack with no evidence.")

        documents: list[ContextDocument] = []
        total_chars = 0
        truncated = False
        for e in evidence:
            content = e.content
            if total_chars + len(content) > self._char_budget and documents:
                truncated = True
                break
            documents.append(
                ContextDocument(
                    document_id=e.document_id,
                    title=e.title,
                    content=content,
                    source=e.source_id,
                    page=e.page,
                    chunk_id=e.chunk_id,
                )
            )
            total_chars += len(content)

        pack_id = "cp_" + hashlib.sha256(
            (question + "|" + "|".join(d.document_id for d in documents)).encode("utf-8")
        ).hexdigest()[:16]

        pack = ContextPack(
            context_pack_id=pack_id,
            question=question,
            documents=documents,
            metadata={
                "evidence_count": len(evidence),
                "included_documents": len(documents),
                "total_characters": total_chars,
                "char_budget": self._char_budget,
                "truncated": truncated,
            },
        )

        # Guarantee the pack satisfies the canonical schema before it leaves the module.
        validate_context_pack(pack.to_dict())
        return pack
