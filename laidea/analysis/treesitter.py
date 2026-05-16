"""Tier 2: tree-sitter — el piso universal de la jerarquía (capa 16).

Esto es lo que de verdad mueve la aguja: hasta ahora JS/TS era un heurístico
`re` que NO podía separar la firma del cuerpo (por eso su aviso era el
genérico "sin parser de TS..."). Con un parser real (tree-sitter, C,
incremental) JS/TS por fin aísla interfaz de cuerpo igual que Python con
`ast`: avisa por firma de función cambiada, construcción/superficie de
clase, y por type/interface/enum (cuya definición ES su interfaz). Llena el
MISMO `Simbolo` del modelo común — no reimplementa la regla de negocio.

**Límite del sandbox (igual que asyncpg/Prism):** `tree-sitter` y las
grammars son paquetes con extensión nativa; sin internet acá no se instalan
ni se prueban. Por eso TODO está envuelto: si la dependencia no está, o su
API difiere, o algo falla, `disponible()` es False y la jerarquía cae sola
al Tier 3 (regex) — el sandbox queda exactamente como antes (212 verde sin
tree-sitter). La verificación real del parser es en el VPS (puede pedir 1
ronda de fix; aceptado y documentado, mismo patrón que el 1er build/deploy).

Decisiones:
- Una sola grammar para toda la clave de lenguaje "jsts": la de TSX
  (tree-sitter-typescript) parsea en la práctica JS/TS/JSX/TSX; así
  `simbolos(source)` no necesita la extensión y la interfaz Tier no cambia.
  Si TSX no carga, se intenta TS y luego JS (degradación dentro del tier).
- Público = lo que rompe a quien usa el símbolo: no `#privado` (JS), no
  modificador `private` (TS), no convención `_` (igual criterio que el
  `_superficie_clase` de Python, para que el producto sea consistente).
"""

from __future__ import annotations

from .modelo import Simbolo

# Import perezoso y ultra-defensivo: cualquier fallo => tier no disponible.
try:  # pragma: no cover - depende del entorno (VPS sí, sandbox no)
    from tree_sitter import Language, Parser  # type: ignore

    _IMPORT_OK = True
except Exception:  # noqa: BLE001 - a propósito: cualquier cosa => degradar
    _IMPORT_OK = False


def _construir_parser():
    """Devuelve un Parser listo, o None si no se puede (degradar a regex).

    Soporta las variantes de empaquetado/versión que conviven en el
    ecosistema sin poder probarlas acá: por eso tantas ramas defensivas.
    """
    if not _IMPORT_OK:
        return None
    lang = None
    for modname, attr in (
        ("tree_sitter_typescript", "language_tsx"),
        ("tree_sitter_typescript", "language_typescript"),
        ("tree_sitter_javascript", "language"),
    ):
        try:  # pragma: no cover - entorno-dependiente
            import importlib

            mod = importlib.import_module(modname)
            raw = getattr(mod, attr)()
            lang = Language(raw)
            break
        except Exception:  # noqa: BLE001
            continue
    if lang is None:
        return None
    try:  # pragma: no cover - la API del Parser cambió entre versiones
        try:
            return Parser(lang)
        except Exception:  # noqa: BLE001
            p = Parser()
            try:
                p.language = lang  # tree-sitter recientes
            except Exception:  # noqa: BLE001
                p.set_language(lang)  # tree-sitter antiguos
            return p
    except Exception:  # noqa: BLE001
        return None


def _txt(nodo, src: bytes) -> str:
    return src[nodo.start_byte : nodo.end_byte].decode("utf-8", "replace")


def _hijo_tipo(nodo, *tipos: str):
    for h in nodo.children:
        if h.type in tipos:
            return h
    return None


def _nombre_decl(nodo, src: bytes) -> str:
    n = _hijo_tipo(nodo, "identifier", "type_identifier", "property_identifier")
    return _txt(n, src) if n is not None else ""


def _firma(params_nodo, src: bytes) -> str:
    """Firma normalizada, estable e independiente del cuerpo (mismo espíritu
    que `_firma` de python.py): nombres y forma de los parámetros, presencia
    de default/opcional, rest. Cambiar el cuerpo no la altera => silencio;
    cambiar parámetros sí => aviso.
    """
    if params_nodo is None:
        return "()"
    partes: list[str] = []
    for p in params_nodo.children:
        t = p.type
        if t in ("(", ")", ","):
            continue
        if t == "rest_pattern" or t == "rest_parameter":
            ident = _hijo_tipo(p, "identifier")
            partes.append("..." + (_txt(ident, src) if ident else ""))
        elif t in ("required_parameter", "optional_parameter"):  # TS
            pat = _hijo_tipo(p, "identifier", "object_pattern", "array_pattern")
            nom = (
                _txt(pat, src)
                if pat is not None and pat.type == "identifier"
                else ("{}" if pat is not None and pat.type == "object_pattern"
                      else "[]" if pat is not None else "?")
            )
            opcional = t == "optional_parameter" or any(
                c.type == "?" for c in p.children
            ) or any(c.type == "=" for c in p.children)
            partes.append(nom + ("=" if opcional else ""))
        elif t == "identifier":
            partes.append(_txt(p, src))
        elif t == "assignment_pattern":  # JS: param = default
            ident = _hijo_tipo(p, "identifier")
            partes.append((_txt(ident, src) if ident else "?") + "=")
        elif t in ("object_pattern", "array_pattern"):
            partes.append("{}" if t == "object_pattern" else "[]")
    return "(" + ", ".join(partes) + ")"


def _superficie_clase(cuerpo, src: bytes) -> tuple[str, frozenset[str]]:
    """(firma de constructor, {miembros públicos}) — espejo del de Python."""
    init = ""
    publicos: set[str] = set()
    if cuerpo is None:
        return init, frozenset()
    for m in cuerpo.children:
        if m.type in ("method_definition", "method_signature"):
            nom_n = _hijo_tipo(m, "property_identifier", "identifier")
            nom = _txt(nom_n, src) if nom_n else ""
            params = _hijo_tipo(m, "formal_parameters")
            if nom == "constructor":
                init = _firma(params, src)
                continue
            if nom and not nom.startswith(("_", "#")) and not _es_privado(m, src):
                publicos.add(nom + "()")
        elif m.type in (
            "field_definition",
            "public_field_definition",
            "property_signature",
        ):
            nom_n = _hijo_tipo(m, "property_identifier", "identifier")
            nom = _txt(nom_n, src) if nom_n else ""
            if nom and not nom.startswith(("_", "#")) and not _es_privado(m, src):
                publicos.add(nom)
    return init, frozenset(publicos)


def _es_privado(miembro, src: bytes) -> bool:
    # TS: modificador `private`. JS: el `#name` ya lo filtra el prefijo.
    for h in miembro.children:
        if h.type == "accessibility_modifier" and _txt(h, src) == "private":
            return True
    return False


# Tipos top-level que nos importan (export_statement los envuelve).
_DECL_FUNC = ("function_declaration", "generator_function_declaration")
_DECL_CLASS = ("class_declaration", "abstract_class_declaration")
_DECL_TIPO = (
    "interface_declaration",
    "type_alias_declaration",
    "enum_declaration",
)


class TreeSitter:
    nivel = 2

    def __init__(self) -> None:
        self._parser = _construir_parser()

    def disponible(self) -> bool:
        return self._parser is not None

    def _decl_simbolo(self, nodo, src: bytes) -> Simbolo | None:
        t = nodo.type
        if t in _DECL_FUNC:
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            return Simbolo(
                nombre=nom, tipo="funcion", fuente=_txt(nodo, src),
                firma=_firma(_hijo_tipo(nodo, "formal_parameters"), src),
                detallado=True,
            )
        if t in _DECL_CLASS:
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            cuerpo = _hijo_tipo(nodo, "class_body")
            init, sup = _superficie_clase(cuerpo, src)
            return Simbolo(
                nombre=nom, tipo="clase", fuente=_txt(nodo, src),
                init=init, superficie=sup, detallado=True,
            )
        if t in _DECL_TIPO:
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            # detallado=True pero tipo="tipo": el modelo da el aviso honesto
            # "su definición es su interfaz" (sin la coletilla "sin parser").
            return Simbolo(
                nombre=nom, tipo="tipo", fuente=_txt(nodo, src),
                detallado=True,
            )
        if t == "lexical_declaration" or t == "variable_declaration":
            # const f = (...) => {...} / const f = function(...) {...}
            decl = _hijo_tipo(nodo, "variable_declarator")
            if decl is None:
                return None
            nom_n = _hijo_tipo(decl, "identifier")
            if nom_n is None:
                return None
            valor = _hijo_tipo(
                decl, "arrow_function", "function_expression", "function"
            )
            if valor is None:
                return None
            return Simbolo(
                nombre=_txt(nom_n, src), tipo="funcion",
                fuente=_txt(nodo, src),
                firma=_firma(_hijo_tipo(valor, "formal_parameters"), src),
                detallado=True,
            )
        return None

    def simbolos(self, source: str) -> dict[str, Simbolo] | None:
        if self._parser is None:
            return None
        try:
            src = source.encode("utf-8")
            arbol = self._parser.parse(src)
        except Exception:  # noqa: BLE001 - parser roto => degradar, no opinar
            return None
        out: dict[str, Simbolo] = {}
        for nodo in arbol.root_node.children:
            objetivo = nodo
            if nodo.type == "export_statement":
                # export [default] <decl>
                inner = None
                for h in nodo.children:
                    if h.type not in ("export", "default", "{", "}", ";"):
                        inner = h
                if inner is None:
                    continue
                objetivo = inner
            sym = self._decl_simbolo(objetivo, src)
            if sym is not None and sym.nombre:
                out[sym.nombre] = sym
        return out

    def referencias(self, source: str) -> set[str]:
        """Identificadores usados, vía el árbol real (sin ruido de strings/
        comentarios: tree-sitter ya los tipa aparte). Hint, no resolución —
        mismo criterio que los otros tiers.
        """
        if self._parser is None:
            return set()
        try:
            src = source.encode("utf-8")
            arbol = self._parser.parse(src)
        except Exception:  # noqa: BLE001
            return set()
        usados: set[str] = set()
        pila = [arbol.root_node]
        while pila:
            n = pila.pop()
            if n.type in ("identifier", "type_identifier"):
                usados.add(_txt(n, src))
            elif n.type in ("string", "template_string", "comment"):
                continue  # no descender: nada de adentro es referencia
            pila.extend(n.children)
        return usados
