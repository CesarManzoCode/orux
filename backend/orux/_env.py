"""Helpers de lectura defensiva de variables de entorno.

Centralizados acá (antes había 3 copias idénticas en `server/config.py`,
`db/pool.py` y `state/workspace.py`) porque son patrón transversal: el
operador setea un env, el código necesita un valor en rango sano, y un
`-1` o `999999999` o `"abc"` NUNCA debe tirar el proceso.

Los call-sites siguen importando de sus módulos históricos (`config.py`
re-exporta) para no romper imports externos ni tests.
"""

from __future__ import annotations

import os


def _env_int(name: str, default: int, minimo: int, maximo: int) -> int:
    """Lee `name` como int, clampa a [minimo, maximo]. Fallback al default
    ante valor ausente, vacío o no convertible."""
    try:
        v = int(os.environ.get(name, default))
    except (TypeError, ValueError):
        v = default
    return max(minimo, min(maximo, v))


def _env_float(
    name: str, default: float, minimo: float, maximo: float,
) -> float:
    """Idem `_env_int` pero para floats (rate-limits, timeouts en segundos)."""
    try:
        v = float(os.environ.get(name, default))
    except (TypeError, ValueError):
        v = default
    return max(minimo, min(maximo, v))
