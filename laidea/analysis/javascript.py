"""Análisis de impacto para JavaScript/TypeScript. Capa 6, segundo lenguaje.

Mismo espíritu y MISMA superficie que `python.py` (`definiciones_top`,
`referencias`, `simbolos_cambiados`): un heurístico por *nombres*, no un
analizador de tipos. Cubre `.js/.jsx/.ts/.tsx` con un solo extractor porque
para detección a nivel de nombre TS es JS + anotaciones: las declaraciones
top-level y los identificadores usados se ven igual.

Por qué NO el compilador de TypeScript: el de Python tampoco es un
compilador (usa `ast` porque viene gratis). La versión "de verdad"
(resolución de tipos cross-módulo) es la parte absurda que el README marca
como riesgo #2 y sigue diferida — para AMBOS lenguajes por igual. Acá, `re`
de la stdlib, cero dependencias.

Honesto sobre los límites (igual que el módulo Python lo documenta):
- Solo declaraciones de nivel módulo (función/clase/const-arrow/type/
  interface/enum), exportadas o no. Métodos y anidados no cuentan.
- Las referencias son todos los identificadores usados (sobre-aproxima a
  propósito: es un hint "míralo", no resolución de imports).
- La "región" de un símbolo para detectar cambios es aproximada (de su
  declaración hasta la siguiente declaración top-level): sin parser real
  no se pueden contar llaves con fiabilidad. Suficiente para el hint.
"""

from __future__ import annotations

import re

# Declaración de nivel módulo. Una alternativa por forma; el nombre queda en
# el primer grupo que matchee. Anclado a COLUMNA 0 (con `re.M`): top-level de
# verdad. Lo indentado (métodos, anidados) NO cuenta — igual que `python.py`
# solo mira el cuerpo del módulo. Heurístico: código con top-level indentado
# (raro) se omitiría; aceptado y documentado.
_DECL = re.compile(
    r"^(?:export[ \t]+)?(?:default[ \t]+)?(?:declare[ \t]+)?(?:"
    r"(?:async[ \t]+)?function\*?[ \t]+([A-Za-z_$][\w$]*)"      # function f
    r"|(?:abstract[ \t]+)?class[ \t]+([A-Za-z_$][\w$]*)"        # class C
    r"|(?:const|let|var)[ \t]+([A-Za-z_$][\w$]*)[ \t]*="        # const x =
    r"|(?:type|interface|enum)[ \t]+([A-Za-z_$][\w$]*)"          # type/iface
    r")",
    re.M,
)

# Identificadores que NO son "referencias" útiles (palabras del lenguaje).
_KW = frozenset(
    """abstract any as async await boolean break case catch class const
    continue debugger declare default delete do else enum export extends
    false finally for from function get if implements import in instanceof
    interface is keyof let namespace never new null number object of package
    private protected public readonly return satisfies set static string
    super switch symbol this throw true try type typeof undefined unknown var
    void while with yield""".split()
)

# Para no contar identificadores dentro de strings/comentarios: los borramos
# antes de tokenizar (igual que el `ast` de Python ignora literales).
_RUIDO = re.compile(
    r"//[^\n]*|/\*[\s\S]*?\*/|`(?:\\.|[^`\\])*`"
    r"|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'"
)
_IDENT = re.compile(r"[A-Za-z_$][\w$]*")


def _tops(source: str) -> list[tuple[str, int]]:
    """(nombre, índice donde empieza la declaración) de cada símbolo top."""
    out = []
    for m in _DECL.finditer(source):
        nombre = m.group(1) or m.group(2) or m.group(3) or m.group(4)
        if nombre:
            out.append((nombre, m.start()))
    return out


def definiciones_top(source: str) -> dict[str, str]:
    """Símbolo top -> su 'región' de código (de su decl a la siguiente).

    La región es aproximada a propósito (ver docstring del módulo). Sirve
    para detectar "este símbolo cambió" comparando su texto entre versiones,
    igual que `python.py` usa el segmento exacto del `ast`.
    """
    tops = _tops(source)
    defs: dict[str, str] = {}
    for i, (nombre, ini) in enumerate(tops):
        fin = tops[i + 1][1] if i + 1 < len(tops) else len(source)
        defs[nombre] = source[ini:fin]
    return defs


def referencias(source: str) -> set[str]:
    """Identificadores usados, sin los de strings/comentarios ni keywords.

    Sobre-aproxima (cuenta también el propio nombre si se autoreferencia,
    etc.): es un hint, no resolución. Mismo criterio que el módulo Python.
    """
    limpio = _RUIDO.sub(" ", source)
    return {t for t in _IDENT.findall(limpio) if t not in _KW}


def simbolos_cambiados(viejo: str, nuevo: str) -> set[str]:
    """Símbolos top agregados, quitados o cuya región cambió.

    Sin concepto de "parsea o no" (no hay parser): si no hay declaraciones
    top, no hay nada que reportar y queda vacío — cero falsos positivos.
    """
    antes = definiciones_top(viejo)
    despues = definiciones_top(nuevo)
    cambiados: set[str] = set()
    for nombre, region in despues.items():
        if antes.get(nombre) != region:  # nuevo o región distinta
            cambiados.add(nombre)
    for nombre in antes:
        if nombre not in despues:  # eliminado/renombrado
            cambiados.add(nombre)
    return cambiados


def cambios_que_importan(viejo: str, nuevo: str) -> dict[str, str]:
    """Símbolo top -> por qué su cambio importa. Versión JS/TS, honesta sobre
    su límite: sin parser no se puede aislar la firma del cuerpo, así que el
    caso fuerte ("se eliminó/renombró", que ROMPE seguro) sí se distingue,
    pero un cambio dentro del símbolo no se puede separar de un cambio de
    interfaz → se reporta como "cambió, revisá tu uso".

    Es deliberadamente menos fino que el de Python (que sí parsea y aísla la
    firma). El usuario aceptó un caso de uso real; el real y validado vive en
    `python.py` (el stack del proyecto). Mejor mensaje que antes igual: ya
    no es "algo cambió" a secas, dice qué símbolo y si desapareció.
    """
    antes = definiciones_top(viejo)
    despues = definiciones_top(nuevo)
    motivos: dict[str, str] = {}
    for nombre, region in despues.items():
        if nombre not in antes:
            continue  # nuevo símbolo: no rompe a nadie que ya existía
        if antes[nombre] != region:
            motivos[nombre] = (
                f"«{nombre}» cambió — sin parser de TS no puedo separar "
                f"firma de cuerpo; revisá si tu uso sigue válido"
            )
    for nombre in antes:
        if nombre not in despues:
            motivos[nombre] = (
                f"se eliminó o renombró «{nombre}» — el código que lo usa "
                f"va a romper"
            )
    return motivos
