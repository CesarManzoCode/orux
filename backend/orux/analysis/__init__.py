"""Re-export desde la nueva ubicación tras el refactor hex (2026-05-24).

El paquete real vive en `orux.domain.analysis`. Este `__init__.py` se
mantiene para no romper imports externos (`from orux.analysis import X`).
"""

from ..domain.analysis import (  # noqa: F401
    Simbolo,
    cambios_que_importan,
    cambios_que_importan_modelo,
    definiciones_top,
    impacto,
    motivos,
    referencias,
    simbolos_cambiados,
    tiers,
)
# Submódulos disponibles vía atributo para `from orux.analysis import javascript`.
from ..domain.analysis import (  # noqa: F401
    go,
    javascript,
    python,
    rust,
)

__all__ = [
    "Simbolo",
    "cambios_que_importan",
    "cambios_que_importan_modelo",
    "definiciones_top",
    "go",
    "impacto",
    "javascript",
    "motivos",
    "python",
    "referencias",
    "rust",
    "simbolos_cambiados",
    "tiers",
]
