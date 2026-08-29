"""Model Gateway module: the provider-neutral model execution mechanism boundary."""

from .gateway import (
    MODEL_GATEWAY_CONTRACT_ID,
    MODEL_GATEWAY_VERSION,
    ModelGateway,
)

__all__ = [
    "MODEL_GATEWAY_CONTRACT_ID",
    "MODEL_GATEWAY_VERSION",
    "ModelGateway",
]
