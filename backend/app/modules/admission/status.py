from __future__ import annotations

from enum import Enum


class EvidenceStatus(str, Enum):
    UNKNOWN = "UNKNOWN"
    PENDING = "PENDING"
    VERIFIED = "VERIFIED"
    PROMOTED = "PROMOTED"
    REJECTED = "REJECTED"


class ValidationOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"


class CheckOutcome(str, Enum):
    PASS = "PASS"
    FAIL = "FAIL"
    UNKNOWN = "UNKNOWN"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class PromotionDecisionValue(str, Enum):
    AUTHORIZE = "AUTHORIZE"
    DENY = "DENY"


class PromotionOutcome(str, Enum):
    PROMOTED = "PROMOTED"
    DENIED = "DENIED"
    BLOCKED = "BLOCKED"
    UNKNOWN = "UNKNOWN"


class AuthorityRight(str, Enum):
    COLLECTION_RIGHT = "COLLECTION_RIGHT"
    ADMISSION_RIGHT = "ADMISSION_RIGHT"
    VALIDATION_RIGHT = "VALIDATION_RIGHT"
    PROMOTION_RIGHT = "PROMOTION_RIGHT"
    ACTION_RIGHT = "ACTION_RIGHT"


class PromotionTarget(str, Enum):
    KNOWLEDGE_GRAPH = "KNOWLEDGE_GRAPH"
    TRUSTED_MEMORY = "TRUSTED_MEMORY"
    DECISION_SUPPORT = "DECISION_SUPPORT"
    AUTOMATION_INPUT = "AUTOMATION_INPUT"
