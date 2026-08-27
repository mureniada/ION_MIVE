"""Core Adapter: the Product-facing boundary over the frozen B0 governance stack.

The export list below is deliberately closed. It carries no governance internal,
no promotion / authority / receipt name, and no evidence-set vocabulary, so
Product code cannot reach mutation authority through this package.
"""

from .facade import CoreAdapter
from .models import (
    CoreAdapterOutcome,
    CoreAdapterOutcomeState,
    CoreAdapterRequest,
    CoreInvocationMode,
)

__all__ = [
    "CoreAdapter",
    "CoreAdapterOutcome",
    "CoreAdapterOutcomeState",
    "CoreAdapterRequest",
    "CoreInvocationMode",
]
