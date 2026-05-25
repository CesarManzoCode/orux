"""Re-export del submódulo movido a `orux.domain.state.locks`."""

from ..domain.state.locks import *  # noqa: F401,F403
from ..domain.state.locks import lineas_tocadas  # noqa: F401

# Internos que tests inspeccionan directamente.
from ..domain.state.locks import (  # noqa: F401
    _LCS_MAX_CELDAS,
    _tocadas_posicional,
)
