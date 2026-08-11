"""LIVE-1 coherence rule-table loader, v0.2 infrastructure only.

Loads a frozen JSON rule-table artifact: recomputes SHA-256 from the raw
bytes (never trusts a stored hash), parses, schema-validates, then applies
the one semantic check the schema itself cannot express (min <= max per
count constraint) plus duplicate-rule_id detection, before constructing
the in-memory CoherenceRuleTable.

Independently implemented, not importing backend/t4/manifest.py -- that
module is scoped to T4's own closed 4-role enumeration, not a generic
loader library; this is a small, LIVE-1-specific loader following the
same recompute-and-verify principle.

No substantive rule content is defined here. No network. No provider SDK
import. Not wired into container.py/Core.ask().
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

from ...core.models import CoherenceCountConstraint, CoherenceRule, CoherenceRuleTable
from ...validation import validate_coherence_rule_table


class CoherenceRuleTableError(Exception):
    """A frozen coherence rule-table artifact failed integrity, schema, or
    semantic validation."""


def load_coherence_rule_table(raw: bytes, *, expected_sha256: str) -> CoherenceRuleTable:
    actual_sha256 = hashlib.sha256(raw).hexdigest()
    if actual_sha256 != expected_sha256:
        raise CoherenceRuleTableError(
            f"SHA-256 mismatch: expected {expected_sha256}, got {actual_sha256}"
        )

    try:
        document: dict[str, Any] = json.loads(raw.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise CoherenceRuleTableError(f"invalid JSON: {exc}") from None

    validate_coherence_rule_table(document)

    seen_ids: set[str] = set()
    rules: list[CoherenceRule] = []
    for raw_rule in document["rules"]:
        rule_id = raw_rule["rule_id"]
        if rule_id in seen_ids:
            raise CoherenceRuleTableError(f"duplicate rule_id: {rule_id!r}")
        seen_ids.add(rule_id)

        r2_counts: dict[str, CoherenceCountConstraint] = {}
        for key, constraint in raw_rule.get("r2_counts", {}).items():
            lo = constraint.get("min")
            hi = constraint.get("max")
            if lo is not None and hi is not None and lo > hi:
                raise CoherenceRuleTableError(
                    f"rule {rule_id!r}: r2_counts.{key} has min ({lo}) > max ({hi})"
                )
            r2_counts[key] = CoherenceCountConstraint(min=lo, max=hi)

        rules.append(CoherenceRule(
            rule_id=rule_id,
            r1=raw_rule.get("r1"),
            r4=raw_rule.get("r4"),
            r5=raw_rule.get("r5"),
            r2_counts=r2_counts,
            allowed_r6=list(raw_rule["allowed_r6"]),
        ))

    return CoherenceRuleTable(
        rule_table_version=document["rule_table_version"],
        rules=rules,
        integrity={"sha256": actual_sha256},
    )
