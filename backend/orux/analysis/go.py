"""Extractor heurístico de Go. Capa 20, mismo espíritu que `javascript.py`.

NO es un analizador de Go: es el detector COARSE (regex, `re` stdlib) que
le da al sistema un símbolo de nivel paquete que "cambió", para que el
fan-out REAL (gopls vía LSP, capa 20) pueda resolver quién lo usa. La
precisión fina ("cambió la firma de X") es pulido futuro con la grammar
tree-sitter de Go; hoy el modelo da el aviso honesto genérico
(`detallado=False`).

Honesto sobre los límites (igual que el módulo JS los documenta):
- Solo declaraciones de nivel paquete ancladas a columna 0: `func` (incl.
  métodos con receiver), `type`, y `var`/`const` de una línea. Bloques
  `type (...)`/`var (...)` agrupados se omiten (raro, aceptado).
- Referencias = todo identificador usado, sin keywords ni lo que está en
  strings/comentarios. Sobre-aproxima a propósito: es un hint, no
  resolución (gopls hace la resolución de verdad).
"""

from __future__ import annotations

import re

# Declaración de nivel paquete (col 0, `re.M`). El nombre queda en el primer
# grupo que matchee. `func (r T) Name(` (método) lleva un receiver opcional
# entre `func` y el nombre.
_DECL = re.compile(
    r"^(?:"
    r"func(?:[ \t]+\([^)]*\))?[ \t]+([A-Za-z_]\w*)"   # func / método
    r"|type[ \t]+([A-Za-z_]\w*)"                        # type
    r"|(?:var|const)[ \t]+([A-Za-z_]\w*)"              # var/const simple
    r")",
    re.M,
)

_KW = frozenset(
    """break case chan const continue default defer else fallthrough for
    func go goto if import interface map package range return select struct
    switch type var nil true false iota""".split()
)

# Strings/comentarios: se borran antes de tokenizar (no son referencias).
# Go: `//`, `/* */`, "...", `...` (raw), '...' (rune).
_RUIDO = re.compile(
    r"//[^\n]*|/\*[\s\S]*?\*/|`[^`]*`"
    r"|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])*'"
)
_IDENT = re.compile(r"[A-Za-z_]\w*")


def _tops(source: str) -> list[tuple[str, int]]:
    out = []
    for m in _DECL.finditer(source):
        nombre = m.group(1) or m.group(2) or m.group(3)
        if nombre:
            out.append((nombre, m.start()))
    return out


def definiciones_top(source: str) -> dict[str, str]:
    """Símbolo top -> su 'región' (de su decl a la siguiente). Aproximada a
    propósito: sirve para detectar "este símbolo cambió" comparando texto."""
    tops = _tops(source)
    defs: dict[str, str] = {}
    for i, (nombre, ini) in enumerate(tops):
        fin = tops[i + 1][1] if i + 1 < len(tops) else len(source)
        defs[nombre] = source[ini:fin]
    return defs


def referencias(source: str) -> set[str]:
    """Identificadores usados, sin keywords ni los de strings/comentarios."""
    limpio = _RUIDO.sub(" ", source)
    return {t for t in _IDENT.findall(limpio) if t not in _KW}
