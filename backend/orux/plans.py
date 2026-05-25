"""Re-export desde la nueva ubicación tras el refactor hex (2026-05-24).

El módulo real vive en `orux.domain.plans`. Este archivo se mantiene para
no romper imports externos (`from orux.plans import X`); pendiente quitar
cuando todos los callers se actualicen.
"""

from .domain.plans import *  # noqa: F401,F403
from .domain.plans import (  # explicit re-export para que ide/type checker vea
    INF,
    PLAN_DEFECTO,
    PLANES,
    impacto_modo,
    limites,
    permite_jvm,
    permite_lenguaje,
    permite_miembro,
    permite_rename,
    permite_workspace,
)

__all__ = [
    "INF",
    "PLANES",
    "PLAN_DEFECTO",
    "impacto_modo",
    "limites",
    "permite_jvm",
    "permite_lenguaje",
    "permite_miembro",
    "permite_rename",
    "permite_workspace",
]
