"""Re-export desde la nueva ubicación tras el refactor hex (2026-05-24).

Los adapters JSON viven ahora en `orux.adapters.outbound.json`.
"""

from ..outbound.json import JsonOwnershipStore, JsonUserStore

__all__ = ["JsonOwnershipStore", "JsonUserStore"]
