"""Re-export desde la nueva ubicación tras el refactor hex (2026-05-24).

El adapter real vive en `orux.adapters.outbound.git.binary` como `GitRepo`
(alias `GitBinaryAdapter`). `EstadoGit` (value object) vive en `orux.ports.git`.
"""

from ..adapters.outbound.git.binary import GitRepo  # noqa: F401
from ..ports.git import EstadoGit  # noqa: F401

__all__ = ["EstadoGit", "GitRepo"]
