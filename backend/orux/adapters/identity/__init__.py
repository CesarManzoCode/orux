"""Re-export desde la nueva ubicación tras el refactor hex (2026-05-24).

Los adapters de identidad viven ahora en `orux.adapters.outbound.identity`.
"""

from ..outbound.identity import GithubOAuthAdapter, HmacSessionTokenAdapter

__all__ = ["GithubOAuthAdapter", "HmacSessionTokenAdapter"]
