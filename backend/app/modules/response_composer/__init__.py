"""Response Composer: user-facing composition boundary.

The export list below is deliberately closed. It carries no evidence-citation
projection type and no concrete IVE/`ModelGateway`/provider-adapter class,
because this package implements and reuses none of them here: it depends on
the standard library, this package's own vocabulary, and — for
`VOEResponseComposer` — `VOERuntimeProfile`'s verified identity-and-text
shape (`app.modules.voe_profile`), only.

Gate 1 defined the composer's input/output contracts (`ComposerClaimView`,
`ComposerInput`, `ComposedResponse`) and the `ResponseComposerPort` Protocol
(declared in `app.core.ports`). Gate 3 (`composer.py`) added the one
authorized implementation, `VOEResponseComposer`, its composer-owned system
instruction/user-payload builders, and its local error vocabulary
(`ResponseComposerError` and subclasses) — reusing only the provider-agnostic
`generate(system, user, schema)` primitive beneath the IVE boundary, never
`ive_common`, `IVEPort`, or `ModelGateway`. Gate 3B removed
`ComposerClaimView`'s unused `evidence_document_ids` field (v0.1 composition
has no functional use for any evidence-identity value) and added
`ResponseComposerResult` — `compose()`'s new return type, pairing a
`ComposedResponse` with the raw execution facts a real provider call
produces, never a cost or status field. No wiring into `Core.ask()`,
`app.container`, or any runtime entry point exists yet; nothing here is
imported by any of them at this stage.
"""

from .composer import (
    COMPOSER_RESPONSE_SCHEMA,
    VOE_RESPONSE_COMPOSER_ID,
    VOE_RESPONSE_COMPOSER_VERSION,
    ResponseComposerError,
    ResponseComposerOutputError,
    ResponseComposerProviderError,
    VOEResponseComposer,
    build_composer_system_instruction,
    build_composer_user_payload,
)
from .models import (
    RESPONSE_COMPOSER_CONTRACT_ID,
    RESPONSE_COMPOSER_VERSION,
    ComposedResponse,
    ComposerClaimView,
    ComposerContractError,
    ComposerInput,
    ResponseComposerResult,
)

__all__ = [
    "COMPOSER_RESPONSE_SCHEMA",
    "RESPONSE_COMPOSER_CONTRACT_ID",
    "RESPONSE_COMPOSER_VERSION",
    "VOE_RESPONSE_COMPOSER_ID",
    "VOE_RESPONSE_COMPOSER_VERSION",
    "ComposedResponse",
    "ComposerClaimView",
    "ComposerContractError",
    "ComposerInput",
    "ResponseComposerError",
    "ResponseComposerOutputError",
    "ResponseComposerProviderError",
    "ResponseComposerResult",
    "VOEResponseComposer",
    "build_composer_system_instruction",
    "build_composer_user_payload",
]
