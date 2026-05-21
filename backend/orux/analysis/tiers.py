"""Jerarquía de analizadores (tiers) — capa 16.

Diseño cerrado con el usuario: por archivo corre UN solo analizador, el más
profundo que esté disponible para ese lenguaje; si ese tier no está (p.ej.
tree-sitter sin instalar) se cae al siguiente. La caída es por
*disponibilidad del tier*, NO por "el código no parsea": un tier presente que
dice "esto está a medio escribir" es una opinión definitiva (no opinar), no
una razón para bajar de tier — así Python conserva exacto su contrato de
capa 6 ("nuevo roto => no aviso nada").

Tiers de hoy:

- **Tier 1** `PythonAst` — Python vía `ast` (stdlib, siempre disponible).
  Detallado: aísla firma/superficie. Reusa el código probado de `python.py`
  (no se reescribe lo que funciona; los tests de capa 6 quedan intactos).
- **Tier 2** `TreeSitter` — piso universal multi-lenguaje (parser C). Su
  disponibilidad depende de que el paquete esté instalado (en el VPS sí; en
  el sandbox sin internet no). Vive en `treesitter.py`; acá solo se registra.
- **Tier 3** `Regex` — el heurístico `re` de `javascript.py`. Siempre
  disponible, no detallado: fallback honesto sobre su límite.

`.py` solo lo atiende `PythonAst` (ast siempre está; meter tree-sitter para
Python no aporta precisión y arriesgaría capa 6 — decisión explícita). JS/TS:
`TreeSitter` y si no `Regex`.
"""

from __future__ import annotations

import logging
from typing import Protocol

_log = logging.getLogger(__name__)

from . import go, javascript, python, rust
from .modelo import Simbolo, cambios_que_importan_modelo


class Tier(Protocol):
    """Un analizador. Produce el modelo normalizado para un lenguaje."""

    nivel: int  # menor = más profundo (1 = el mejor)

    def disponible(self) -> bool:
        """¿Este tier puede usarse acá? (p.ej. su dependencia instalada)."""
        ...

    def simbolos(self, source: str) -> dict[str, Simbolo] | None:
        """Símbolos top del fuente, o None si no es analizable (código a
        medio escribir). None es "no opino", NO "probá otro tier"."""
        ...

    def referencias(self, source: str) -> set[str]:
        """Identificadores que el fuente usa (hint, no resolución)."""
        ...


# --- Tier 1: Python vía ast (envuelve python.py, no lo reescribe) ----------


class _PythonAst:
    nivel = 1

    def disponible(self) -> bool:
        return True  # `ast` es stdlib

    def simbolos(self, source: str) -> dict[str, Simbolo] | None:
        if python._parse(source) is None:
            return None  # roto: no opino (contrato capa 6, byte-idéntico)
        nodos = python._nodos_top(source)
        defs = python.definiciones_top(source)
        out: dict[str, Simbolo] = {}
        for nombre, nodo in nodos.items():
            fuente = defs.get(nombre, "")
            deps = python._deps_interfaz(nodo)  # capa 24b: tipos en interfaz
            if isinstance(nodo, python.ast.ClassDef):
                init, superficie = python._superficie_clase(nodo)
                atrs = python._atributos_instancia(nodo)
                out[nombre] = Simbolo(
                    nombre=nombre, tipo="clase", fuente=fuente,
                    init=init, superficie=superficie, detallado=True,
                    deps=deps, atrs_instancia=atrs,
                )
            else:  # FunctionDef | AsyncFunctionDef
                out[nombre] = Simbolo(
                    nombre=nombre, tipo="funcion", fuente=fuente,
                    firma=python._firma(nodo), detallado=True, deps=deps,
                )
        return out

    def referencias(self, source: str) -> set[str]:
        return python.referencias(source)


# --- Tier 3: regex heurístico (envuelve un módulo por-lenguaje) -----------
# Genérico: envuelve cualquier módulo con la superficie (definiciones_top,
# referencias). javascript.py fue el primero; go.py/rust.py (capa 20) son
# el MISMO patrón. detallado=False: sin parser no se aísla la firma -> el
# modelo da el aviso honesto genérico. El fan-out real (LSP) NO depende de
# esto; solo necesita que haya un símbolo que cambió para preguntar.


class _Regex:
    nivel = 3

    def __init__(self, mod) -> None:
        self._mod = mod

    def disponible(self) -> bool:
        return True  # `re` es stdlib

    def simbolos(self, source: str) -> dict[str, Simbolo] | None:
        # El heurístico no tiene "parsea o no": si no hay tops, dict vacío
        # (cero falsos positivos), nunca None — siempre es su propia opinión.
        defs = self._mod.definiciones_top(source)
        return {
            nombre: Simbolo(
                nombre=nombre, tipo="?", fuente=region, detallado=False
            )
            for nombre, region in defs.items()
        }

    def referencias(self, source: str) -> set[str]:
        return self._mod.referencias(source)


# Registro: extensión -> (clave de lenguaje, [tiers ordenados por nivel]).
# La clave de lenguaje evita cruzar lenguajes (un símbolo de models.ts no
# afecta .py), igual que el viejo dispatcher.
_PY = _PythonAst()
_REGEX = _Regex(javascript)
_GO = _Regex(go)
_RUST = _Regex(rust)


def _treesitter_tier(clase: str) -> Tier | None:
    """Tier 2 (tree-sitter) para `clase` ('jsts'|'go'|'rust') si su grammar
    está; si no, None. Import perezoso y ultra-defensivo: el sandbox sin
    internet no lo tiene y NO debe romper nada (cae a regex como antes).
    BACKEND-AUDIT-0149: loguear la razón para que un grammar incompatible
    en el VPS deje rastro (antes silencio total, indiagnosticable)."""
    try:
        from . import treesitter

        cls = {
            "jsts": treesitter.TreeSitter,
            "go": treesitter.TreeSitterGo,
            "rust": treesitter.TreeSitterRust,
        }[clase]
        t = cls()
        if not t.disponible():
            _log.info("tree-sitter %s no disponible (grammar)", clase)
            return None
        return t
    except Exception as e:  # noqa: BLE001
        _log.info("tree-sitter %s no se pudo cargar: %r", clase, e)
        return None


_TS_JS = _treesitter_tier("jsts")
_TS_GO = _treesitter_tier("go")
_TS_RUST = _treesitter_tier("rust")

_JS_TIERS: list[Tier] = [t for t in (_TS_JS, _REGEX) if t is not None]

_POR_EXT: dict[str, tuple[str, list[Tier]]] = {
    "py": ("py", [_PY]),
}
for _ext in ("js", "jsx", "mjs", "cjs", "ts", "tsx", "mts", "cts"):
    _POR_EXT[_ext] = ("jsts", _JS_TIERS)
# Capa 25 (cierre de brecha): Go y Rust ahora tienen detección FINA por
# tree-sitter (firma/superficie), no sólo el regex coarse de capa 20. El
# fan-out real sigue siendo LSP (gopls/rust-analyzer); regex queda de
# fallback honesto si la grammar no carga (sandbox sin internet).
_POR_EXT["go"] = ("go", [t for t in (_TS_GO, _GO) if t is not None])
_POR_EXT["rs"] = ("rust", [t for t in (_TS_RUST, _RUST) if t is not None])


def lenguaje_de(path: str) -> str | None:
    """Clave de lenguaje de un path (o None si no se analiza)."""
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    par = _POR_EXT.get(ext)
    return par[0] if par else None


# Lenguajes con Tier 0 LSP. Capa 17: py (pyright). Capa 18: jsts
# (typescript-language-server) — el cliente LSP era universal, sumarlo fue
# enchufar. La detección de cambio sigue en la jerarquía de capa 16; el LSP
# aporta SOLO el fan-out real (ver `cambios`/`archivos_afectados`).
_LSP_LANGS = {"py", "jsts", "go", "rust"}


def _usar_lsp(sesion, path: str) -> bool:
    """¿Hay sesión LSP viva y aplica a este lenguaje? Es el Tier 0 (el más
    profundo). Si no, se cae a la jerarquía de capa 16 (ast/tree-sitter/
    regex) — la red de seguridad que hace seguro adoptar LSP."""
    return (
        sesion is not None
        and lenguaje_de(path) in _LSP_LANGS
        and sesion.disponible()
    )


def cambios(
    path: str, viejo: str, nuevo: str, sesion=None
) -> dict[str, str]:
    """Símbolo cambiado en `path` -> por qué importa.

    DETECCIÓN del cambio = jerarquía de capa 16 (ast para Python, ya aísla
    firma/superficie perfecto; tree-sitter; regex). El `documentSymbol` de
    pyright NO sirve para esto: no rellena la firma en `detail`, así que un
    cambio de `__init__` pasaba inadvertido (verificado en el VPS). El
    aporte real de pyright es OTRO —el fan-out con resolución real, ver
    `archivos_afectados`—, no la detección. Por eso `sesion` no se usa acá:
    detección y fan-out son cosas distintas y se las desacopla a propósito.
    Sin sesión = idéntico (los tests sin sesión no cambian).
    """
    tier = tier_para(path)
    if tier is None:
        return {}
    despues = tier.simbolos(nuevo)
    if despues is None:
        return {}  # no opinamos sobre código roto (idéntico a capa 6)
    antes = tier.simbolos(viejo) or {}
    return cambios_que_importan_modelo(antes, despues)


def archivos_afectados(
    path: str, workspace: dict[str, str], nuevo: str,
    syms: list[str], lang: str, tier, sesion=None,
) -> dict[str, list[str]]:
    """{símbolo: [otros archivos que lo usan]}.

    Con sesión LSP viva: fan-out REAL (pyright resolvió imports — quién usa
    de verdad el símbolo, no quién tiene el token). Ése es el salto que mata
    los falsos positivos. Si LSP falló entera, o sin sesión: token-scan de
    capa 16, byte-idéntico.

    Falso-negativo (BUG-PROD-PERSONA): cuando LSP devuelve set() para UN
    símbolo porque el cliente tiene imports rotos / archivo huérfano / el
    índice aún no sincronizó ese path, antes nos quedábamos MUDOS (peor que
    free). El fix: por-símbolo, si LSP no encontró refs PERO el símbolo SÍ
    aparece como identificador en otros archivos, caemos al token-scan para
    ese símbolo. Es la regla "LSP suma, no resta": cuando LSP afirma usos los
    confiamos (sigue matando los falsos positivos clásicos del token-scan);
    cuando guarda silencio Y token-scan ve algo, preferimos avisar (un falso
    positivo ocasional << un dueño no enterado de que rompiste su archivo).
    """
    def _scan(sym: str) -> list[str]:
        return sorted(
            o for o, c in workspace.items()
            if o != path and lenguaje_de(o) == lang
            and sym in tier.referencias(c)
        )

    if _usar_lsp(sesion, path):
        real = sesion.fan_out(workspace, path, nuevo, syms)
        if real is not None:
            out: dict[str, list[str]] = {}
            for s in syms:
                af_lsp = real.get(s) or set()
                if af_lsp:
                    out[s] = sorted(af_lsp)
                    continue
                # LSP guardó silencio sobre este símbolo: respaldo token-scan.
                # Si token-scan tampoco ve nada, no hay aviso (correcto:
                # nadie lo usa). Si SÍ ve, probablemente el import del
                # consumidor está roto / pyright no lo indexó: avisamos.
                af_tok = _scan(s)
                if af_tok:
                    out[s] = af_tok
                    _log.info(
                        "fan-out LSP vacío para %r en %s; rescate token-scan: %s",
                        s, path, af_tok,
                    )
            return out
        # fan-out LSP falló ENTERO (excepción) -> degradar al token-scan
    out2: dict[str, list[str]] = {}
    for s in syms:
        af = _scan(s)
        if af:
            out2[s] = af
    return out2


def tier_para(path: str) -> Tier | None:
    """El tier más profundo DISPONIBLE para este path, o None si el lenguaje
    no se analiza. La caída es por disponibilidad del tier, no por sintaxis.
    """
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    par = _POR_EXT.get(ext)
    if par is None:
        return None
    for tier in par[1]:
        if tier.disponible():
            return tier
    return None
