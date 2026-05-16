"""Análisis semántico de impacto (capa 6), ahora pluggable por lenguaje.

Empezó solo-Python a propósito (README riesgo #2: no querer multi-lenguaje
antes de tiempo). El segundo lenguaje entró por el gatillo real: devs de
TypeScript probando el producto — sin el análisis, para ellos esto no tiene
diferenciador. NO se metió el compilador de TS: el análisis siempre fue un
heurístico por nombres (el de Python usa `ast` solo porque viene gratis),
así que TS/JS es el MISMO heurístico con otro extractor (`javascript.py`),
en `re` puro, sin dependencias ni cambios de arquitectura del server.

`impacto` despacha por extensión y se queda DENTRO del lenguaje (un símbolo
de `models.ts` solo afecta otros `.ts/.tsx/...`; cruzar lenguajes no tendría
sentido). Para `.py` el resultado es idéntico al de antes (usa `python.py`):
los tests de capa 6 no cambian.

Se re-exportan las funciones de Python (`definiciones_top`/`referencias`/
`simbolos_cambiados`) por compatibilidad: son la referencia del contrato y
lo que prueban los tests puros.
"""

from __future__ import annotations

from . import javascript, python
from .python import (
    cambios_que_importan,
    definiciones_top,
    referencias,
    simbolos_cambiados,
)

# Extensión -> módulo de lenguaje. Mismo módulo para js/jsx/ts/tsx: a nivel
# de NOMBRE TS es JS + anotaciones (ver javascript.py).
_POR_EXT = {
    "py": python,
    "js": javascript, "jsx": javascript, "mjs": javascript,
    "cjs": javascript, "ts": javascript, "tsx": javascript,
    "mts": javascript, "cts": javascript,
}


def _modulo(path: str):
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _POR_EXT.get(ext)


def impacto(
    workspace: dict[str, str], path: str, viejo: str, nuevo: str
) -> dict[str, list[str]]:
    """Símbolo cambiado en `path` -> otros archivos (del MISMO lenguaje) que
    lo referencian. La pregunta del onboarding: "cambié esto, ¿a quién le
    importa?". Lenguaje sin extractor (o sin símbolos cambiados) -> {}: el
    server no avisa nada y nada se rompe (degradación con gracia, igual que
    siempre).
    """
    mod = _modulo(path)
    if mod is None:
        return {}
    # Antes: simbolos_cambiados (cualquier cambio de cuerpo → ruido). Ahora:
    # solo cambios que afectan a quien usa el símbolo. El POR QUÉ de cada uno
    # lo da `motivos()` (mismo cálculo, lo expone el server en el aviso).
    cambiados = mod.cambios_que_importan(viejo, nuevo)
    if not cambiados:
        return {}
    resultado: dict[str, list[str]] = {}
    for sym in cambiados:
        afectados = sorted(
            otro
            for otro, contenido in workspace.items()
            if otro != path
            and _modulo(otro) is mod
            and sym in mod.referencias(contenido)
        )
        if afectados:
            resultado[sym] = afectados
    return resultado


def motivos(path: str, viejo: str, nuevo: str) -> dict[str, str]:
    """Símbolo cambiado en `path` -> POR QUÉ su cambio le importa a quien lo
    usa. Despacha por extensión igual que `impacto` (mismo lenguaje, misma
    regla). El server lo usa para que el aviso no sea "algo cambió" sino la
    razón concreta — que era justo lo que faltaba para que no fuera adorno.
    """
    mod = _modulo(path)
    if mod is None:
        return {}
    return mod.cambios_que_importan(viejo, nuevo)


__all__ = [
    "cambios_que_importan",
    "definiciones_top",
    "impacto",
    "motivos",
    "referencias",
    "simbolos_cambiados",
]
