"""Conversation Context: the bounded, in-session memory a follow-up turn may use.

Amendment OD22-08-A1 (docs/ION_PHASE2_CONVERSATION_CONTEXT_AMENDMENT_v1.md).
At most two prior COMPLETED turns of ONE session, each reduced to exactly its
question, its IVE abstract and its IVE uncertainty, capped and hashed. It is
never evidence, never source authority, never persisted and never shared
across sessions. This package imports the standard library only.
"""

from .builder import (
    build_conversation_context,
    cap_text,
    prior_turn_from_ask_result,
    retrieval_query_for,
    root_question_for,
)
from .models import (
    CONVERSATION_CONTEXT_CONTRACT_ID,
    CONVERSATION_CONTEXT_VERSION,
    INTERPRETATION_CHAR_CAP,
    MAX_PRIOR_TURNS,
    QUESTION_CHAR_CAP,
    TOTAL_CHAR_CAP,
    TRUNCATION_MARK,
    UNCERTAINTY_CHAR_CAP,
    UNCERTAINTY_ITEM_CAP,
    ConversationContext,
    ConversationContextError,
    PriorTurnContext,
    canonical_context_bytes,
    context_sha256,
)

__all__ = [
    "CONVERSATION_CONTEXT_CONTRACT_ID",
    "CONVERSATION_CONTEXT_VERSION",
    "INTERPRETATION_CHAR_CAP",
    "MAX_PRIOR_TURNS",
    "QUESTION_CHAR_CAP",
    "TOTAL_CHAR_CAP",
    "TRUNCATION_MARK",
    "UNCERTAINTY_CHAR_CAP",
    "UNCERTAINTY_ITEM_CAP",
    "ConversationContext",
    "ConversationContextError",
    "PriorTurnContext",
    "build_conversation_context",
    "canonical_context_bytes",
    "cap_text",
    "context_sha256",
    "prior_turn_from_ask_result",
    "retrieval_query_for",
    "root_question_for",
]
