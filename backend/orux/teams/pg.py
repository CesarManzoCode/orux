"""Re-export del adapter movido a `orux.adapters.outbound.postgres.teams`."""

from ..adapters.outbound.postgres.teams import PgTeamStore  # noqa: F401

__all__ = ["PgTeamStore"]
