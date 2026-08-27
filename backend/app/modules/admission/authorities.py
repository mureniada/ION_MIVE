from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, FrozenSet, Iterable, Optional, Set

from .status import AuthorityRight, PromotionTarget


@dataclass(frozen=True)
class AuthorityGrant:
    actor: str
    right: AuthorityRight
    targets: FrozenSet[PromotionTarget] = field(default_factory=frozenset)

    def __post_init__(self) -> None:
        if not self.actor:
            raise ValueError("actor is required")
        if self.right == AuthorityRight.PROMOTION_RIGHT and not self.targets:
            raise ValueError("PROMOTION_RIGHT requires at least one explicit target")


class AuthorityRegistry:
    def __init__(self, grants: Iterable[AuthorityGrant] = ()) -> None:
        self._grants = tuple(grants)

    def has_right(
        self,
        actor: str,
        right: AuthorityRight,
        target: Optional[PromotionTarget] = None,
    ) -> bool:
        for grant in self._grants:
            if grant.actor != actor or grant.right != right:
                continue
            if right == AuthorityRight.PROMOTION_RIGHT:
                return target is not None and target in grant.targets
            return True
        return False

    @property
    def grants(self):
        return self._grants
