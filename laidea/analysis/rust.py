"""Extractor heurístico de Rust. Capa 20, mismo espíritu que `javascript.py`.

NO es un analizador de Rust: es el detector COARSE (regex, `re` stdlib) que
le da al sistema un símbolo de nivel módulo que "cambió", para que el
fan-out REAL (rust-analyzer vía LSP, capa 20) resuelva quién lo usa. La
precisión fina es pulido futuro con la grammar tree-sitter de Rust; hoy el
modelo da el aviso honesto genérico (`detallado=False`).

Honesto sobre los límites (igual que el módulo JS los documenta):
- Solo items de nivel módulo anclados a columna 0: `fn` (con `pub`,
  `async`, `unsafe`, `const`, `extern` opcionales), `struct`, `enum`,
  `trait`, `type`, `union`, `mod`, y `const`/`static`. Métodos dentro de
  `impl` no cuentan (no son un nombre nuevo de nivel módulo); aceptado.
- Referencias = identificadores usados sin keywords ni strings/comentarios.
  Los lifetimes (`'a`) pueden colarse como ruido: es un hint, no
  resolución (rust-analyzer resuelve de verdad).
"""

from __future__ import annotations

import re

_PUB = r"(?:pub(?:\([^)]*\))?[ \t]+)?"  # pub / pub(crate) opcional

_DECL = re.compile(
    r"^" + _PUB + r"(?:"
    r"(?:(?:async|unsafe|const|extern(?:[ \t]+\"[^\"]*\")?)[ \t]+)*"
    r"fn[ \t]+([A-Za-z_]\w*)"                                 # fn
    r"|(?:struct|enum|trait|union|type|mod)[ \t]+([A-Za-z_]\w*)"
    r"|(?:const|static)(?:[ \t]+mut)?[ \t]+([A-Za-z_]\w*)"   # const/static
    r")",
    re.M,
)

_KW = frozenset(
    """as async await break const continue crate dyn else enum extern false
    fn for if impl in let loop match mod move mut pub ref return self Self
    static struct super trait true type union unsafe use where while""".split()
)

# Strings/comentarios Rust: `//`, `/* */`, "...", r"..."/r#"..."# (aprox),
# char '...'. El comentario anidado de Rust se aproxima con no-greedy.
_RUIDO = re.compile(
    r"//[^\n]*|/\*[\s\S]*?\*/"
    r"|r#*\"[\s\S]*?\"#*|\"(?:\\.|[^\"\\\n])*\"|'(?:\\.|[^'\\\n])'"
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
