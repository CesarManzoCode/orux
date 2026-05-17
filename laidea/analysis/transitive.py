"""Impacto transitivo — capa 24. La onda expansiva de un cambio.

Lo difícil de verdad, y la decisión que lo hace correcto: transitivo NO es
"referencias de referencias" (eso explota en ruido — justo lo que mataron
las capas 16-19). Es **propagación por interfaz contaminada**:

  - El cambio de S llega a un archivo R que lo usa.
  - Para cada símbolo T de R que menciona a S:
      · si S aparece en la INTERFAZ de T (firma/constructor/superficie) →
        la interfaz de T quedó contaminada: se avisa Y se PROPAGA (los que
        usan T también están en la onda).
      · si S aparece solo en el CUERPO de T → la interfaz de T no cambió:
        se avisa TERMINAL (revisá) y la onda CORTA ahí.

Eso acota la explosión y es lo honesto. Reusa el `Simbolo` de capa 16
(firma/init/superficie ya extraídos) y el fan-out de capa 17 (inyectado:
LSP en deploy, falso en tests). Ciclos por `visitados`; profundidad y
presupuesto de nodos con truncado honesto (nunca cuelga, nunca miente).

Puro y con todo inyectado: 100% sandbox-testeable sin LSP ni Postgres. NO
toca el `impacto()` directo de capas 17-21 (free sigue byte-idéntico; esto
es el camino premium aparte).
"""

from __future__ import annotations

import re
from collections import deque
from typing import Callable

from .modelo import Simbolo

# Extractor de símbolos de un contenido (content -> {nombre: Simbolo}).
Extraer = Callable[[str], "dict[str, Simbolo] | None"]
# Fan-out: archivos (≠ origen) que referencian `sym`. LSP/real o falso.
FanOut = Callable[[str, str], "set[str]"]
# Clave de lenguaje de un path (para no cruzar lenguajes), o None.
LangDe = Callable[[str], "str | None"]


def _menciona(texto: str, nombre: str) -> bool:
    """`nombre` aparece como identificador en `texto` (con borde de palabra:
    `User` no matchea dentro de `Username`). Heurístico por nombre, mismo
    espíritu que toda la capa de análisis."""
    if not texto:
        return False
    return re.search(r"(?<![\w$])" + re.escape(nombre) + r"(?![\w$])",
                     texto) is not None


def _en_interfaz(s: Simbolo, nombre: str) -> bool:
    """¿`nombre` está en la INTERFAZ de `s` (lo que ven sus usuarios:
    firma, constructor, miembros públicos)? Si sí, un cambio de `nombre`
    cambia el contrato de `s` → se propaga."""
    interfaz = " ".join([s.firma or "", s.init or "", *sorted(s.superficie)])
    return _menciona(interfaz, nombre)


def impacto_transitivo(
    workspace: dict[str, str],
    path: str,
    syms_cambiados: list[str],
    *,
    fan_out: FanOut,
    extraer: Extraer,
    lenguaje_de: LangDe,
    max_prof: int = 4,
    max_nodos: int = 200,
) -> tuple[dict[str, list[dict]], bool]:
    """{archivo_afectado: [{sym, cadena, motivo, terminal}]}, truncado.

    `cadena` = los hops desde el cambio original hasta acá ("file:sym" →
    "file:sym" → …): el porqué de la onda, legible. `terminal=True` = uso
    en cuerpo, no se propagó más allá de ese símbolo. `truncado=True` = se
    alcanzó el límite (cambio muy amplio): se devuelve lo hallado y se
    avisa honesto, no se cuelga.
    """
    lang = lenguaje_de(path)
    out: dict[str, list[dict]] = {}
    truncado = False
    nodos = 0
    # Frontera: (símbolo, archivo_donde_vive, cadena, profundidad).
    cola: deque[tuple[str, str, list[str], int]] = deque(
        (s, path, [f"{path}:{s}"], 0) for s in syms_cambiados
    )
    # Evita re-expandir el mismo (símbolo, archivo) — corta ciclos.
    visitados: set[tuple[str, str]] = {(s, path) for s in syms_cambiados}

    while cola:
        sym, origen, cadena, prof = cola.popleft()
        for otro in sorted(fan_out(sym, origen)):
            if otro == origen or lenguaje_de(otro) != lang:
                continue
            simbolos = extraer(workspace.get(otro, "")) or {}
            for nombre, s in simbolos.items():
                if not _menciona(s.fuente, sym):
                    continue  # ese símbolo no usa `sym`
                interfaz = _en_interfaz(s, sym)
                nueva_cadena = cadena + [f"{otro}:{nombre}"]
                motivo = (
                    f"«{nombre}» expone «{sym}» en su interfaz — el cambio "
                    f"se propaga"
                    if interfaz else
                    f"«{nombre}» usa «{sym}» (que cambió) en su cuerpo — "
                    f"revisá; la onda corta acá"
                )
                out.setdefault(otro, []).append({
                    "sym": nombre,
                    "cadena": nueva_cadena,
                    "motivo": motivo,
                    "terminal": not interfaz,
                })
                nodos += 1
                if nodos >= max_nodos:
                    truncado = True
                    return out, truncado
                # Propaga SOLO si la interfaz de `nombre` quedó contaminada
                # y queda profundidad. Uso solo-cuerpo = terminal.
                if (
                    interfaz
                    and prof + 1 < max_prof
                    and (nombre, otro) not in visitados
                ):
                    visitados.add((nombre, otro))
                    cola.append((nombre, otro, nueva_cadena, prof + 1))
                elif interfaz and prof + 1 >= max_prof:
                    truncado = True  # había para propagar, se cortó por prof
    return out, truncado
