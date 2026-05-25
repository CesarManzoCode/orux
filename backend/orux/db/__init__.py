"""Re-export desde la nueva ubicación tras el refactor hex (2026-05-24).

`Database` (pool asyncpg) vive ahora en `orux.adapters.outbound.postgres.pool`.
"""

from ..adapters.outbound.postgres.pool import Database  # noqa: F401

__all__ = ["Database"]
