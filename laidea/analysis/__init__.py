"""Análisis semántico de impacto — capa 6, ahora sobre jerarquía de tiers.

Historia: empezó solo-Python (`ast`), luego entró JS/TS por gatillo real
(devs de TS) con un heurístico `re`. Capa 16 reorganizó eso en una
**jerarquía de analizadores** (`tiers.py`): por archivo corre el tier más
profundo disponible (Python-ast; tree-sitter universal; regex de fallback),
todos hablando UN modelo de símbolo común y UNA sola regla de "qué cambió
que importa" (`modelo.py`). El despachador de acá ya no conoce módulos por
lenguaje: delega en `tiers`.

`impacto` se queda DENTRO del lenguaje (un símbolo de `models.ts` solo
afecta otros `.ts/.tsx/...`; cruzar lenguajes no tendría sentido). Para
`.py` el resultado es idéntico al de siempre (mismo `ast`, ahora vía el
tier): los tests de capa 6 no cambian.

Se re-exportan las funciones de `python.py` (`definiciones_top`/
`referencias`/`simbolos_cambiados`/`cambios_que_importan`) por
compatibilidad: son la referencia del contrato y lo que prueban los tests
puros del lenguaje.
"""

from __future__ import annotations

from . import javascript, python, tiers
from .modelo import Simbolo, cambios_que_importan_modelo
from .python import (
    cambios_que_importan,
    definiciones_top,
    referencias,
    simbolos_cambiados,
)


def impacto(
    workspace: dict[str, str], path: str, viejo: str, nuevo: str
) -> dict[str, list[str]]:
    """Símbolo cambiado en `path` -> otros archivos (del MISMO lenguaje) que
    lo referencian. La pregunta del onboarding: "cambié esto, ¿a quién le
    importa?". Lenguaje sin tier (o sin cambios que importen) -> {}: el
    server no avisa nada y nada se rompe (degradación con gracia).
    """
    lang = tiers.lenguaje_de(path)
    if lang is None:
        return {}
    # Solo los cambios que de verdad afectan a quien usa el símbolo (no
    # cualquier cambio de cuerpo). El POR QUÉ lo da `motivos()`.
    cambiados = tiers.cambios(path, viejo, nuevo)
    if not cambiados:
        return {}
    tier = tiers.tier_para(path)
    resultado: dict[str, list[str]] = {}
    for sym in cambiados:
        afectados = sorted(
            otro
            for otro, contenido in workspace.items()
            if otro != path
            and tiers.lenguaje_de(otro) == lang
            and sym in tier.referencias(contenido)
        )
        if afectados:
            resultado[sym] = afectados
    return resultado


def motivos(path: str, viejo: str, nuevo: str) -> dict[str, str]:
    """Símbolo cambiado en `path` -> POR QUÉ su cambio le importa a quien lo
    usa. Mismo lenguaje/regla que `impacto` (es el mismo cálculo). El server
    lo usa para que el aviso no sea "algo cambió" sino la razón concreta.
    """
    return tiers.cambios(path, viejo, nuevo)


__all__ = [
    "Simbolo",
    "cambios_que_importan",
    "cambios_que_importan_modelo",
    "definiciones_top",
    "impacto",
    "motivos",
    "referencias",
    "simbolos_cambiados",
    "tiers",
]
