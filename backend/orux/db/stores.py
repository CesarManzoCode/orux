"""Re-export del submódulo movido a `orux.adapters.outbound.postgres.stores`."""

from ..adapters.outbound.postgres.stores import (  # noqa: F401
    PgOwnershipStore,
    PgProposalsStore,
    PgUserStore,
    PgWebhooksStore,
)

__all__ = [
    "PgOwnershipStore",
    "PgProposalsStore",
    "PgUserStore",
    "PgWebhooksStore",
]
