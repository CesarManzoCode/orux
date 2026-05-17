"""Tier 2: tree-sitter — el piso universal de la jerarquía (capa 16).

Esto es lo que de verdad mueve la aguja: un parser real (tree-sitter, C,
incremental) aísla la INTERFAZ del cuerpo igual que Python con `ast`, así el
aviso es fino ("cambió la firma de X") en vez del genérico "X cambió,
revisá". Llena el MISMO `Simbolo` del modelo común — no reimplementa la
regla de negocio (vive una sola vez en `modelo.py`).

Lenguajes con detección fina por tree-sitter:
- **jsts** (JS/TS/JSX/TSX) — capa 16, VERIFICADO en VPS (capas 16-19). Su
  clase y sus helpers NO se tocaron al generalizar: el contrato probado en
  producción queda byte-idéntico.
- **go** / **rust** — capa 25 (cierre de brecha): hasta acá Go/Rust tenían
  fan-out LSP real (gopls/rust-analyzer, capa 20) pero la DETECCIÓN caía a
  regex Tier 3 (mensaje grueso). Ahora detectan firma/superficie como jsts.

**Límite del sandbox (igual que asyncpg/Prism):** `tree-sitter` y las
grammars son paquetes con extensión nativa; sin internet acá no se instalan
ni se prueban. Por eso TODO está envuelto: si la dependencia no está, o su
API difiere, o algo falla, `disponible()` es False y la jerarquía cae sola
al Tier 3 (regex) — el sandbox queda exactamente como antes. La verificación
real del parser es en el VPS (puede pedir 1 ronda de fix; aceptado y
documentado, mismo patrón que el 1er build/deploy).

Decisiones (transversales a los 3 lenguajes):
- Una sola grammar por clave de lenguaje (la de TSX parsea JS/TS/JSX/TSX en
  la práctica); así `simbolos(source)` no necesita la extensión.
- Público = lo que rompe a quien usa el símbolo: no `#privado`/`private`
  (jsts), exportado=Mayúscula inicial (Go), `pub` (Rust). Mismo criterio que
  el `_superficie_clase` de Python — el producto es consistente.
- Mapeo mínimo y honesto: lo que tiene firma separable del cuerpo → función
  o clase (aviso fino); lo que ES su propia definición (type/interface/enum/
  trait/alias/const/mod) → "tipo" (el modelo da "su definición es su
  interfaz; revisá los usos", sin la coletilla "sin parser").
"""

from __future__ import annotations

from .modelo import Simbolo

# Import perezoso y ultra-defensivo: cualquier fallo => tier no disponible.
try:  # pragma: no cover - depende del entorno (VPS sí, sandbox no)
    from tree_sitter import Language, Parser  # type: ignore

    _IMPORT_OK = True
except Exception:  # noqa: BLE001 - a propósito: cualquier cosa => degradar
    _IMPORT_OK = False


def _construir_parser(candidatos):
    """Devuelve un Parser listo para `candidatos` [(modname, attr), ...], o
    None si no se puede (degradar a regex). Soporta las variantes de
    empaquetado/versión que conviven en el ecosistema sin poder probarlas
    acá: por eso tantas ramas defensivas.
    """
    if not _IMPORT_OK:
        return None
    lang = None
    for modname, attr in candidatos:
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
    n = _hijo_tipo(
        nodo, "identifier", "type_identifier", "property_identifier",
        "field_identifier",
    )
    return _txt(n, src) if n is not None else ""


def _deps(nodo, src: bytes, *cuerpos: str) -> frozenset[str]:
    """Capa 24b: nombres de TIPO de la INTERFAZ (params, retorno, herencia,
    tipos de campos), NO del cuerpo. Regla simple y robusta: recolectar
    `type_identifier` SIN descender al nodo de cuerpo (`statement_block` en
    jsts, `block` en Go/Rust). Así el transitivo propaga por tipos.
    Heurístico por nombre, como todo el análisis."""
    out: set[str] = set()
    pila = [nodo]
    while pila:
        n = pila.pop()
        if n is not nodo and n.type in cuerpos:
            continue  # cuerpo: no es interfaz
        if n.type == "type_identifier":
            out.add(_txt(n, src))
        pila.extend(n.children)
    return frozenset(out)


class _TSBase:
    """Mecánica común a todos los tiers tree-sitter. La parte específica de
    cada lenguaje son sólo los atributos de clase + `_decl_simbolo` (y, para
    jsts, `_desenvolver`). El recorrido, la disponibilidad y `referencias`
    se escriben una sola vez."""

    nivel = 2

    # (modname, attr) candidatos de grammar, en orden de preferencia.
    _GRAMMARS: tuple[tuple[str, str], ...] = ()
    # Tipos de nodo que SON referencias (identificadores usados).
    _IDENT_NODOS: tuple[str, ...] = ("identifier", "type_identifier")
    # Tipos de nodo cuyo contenido NO es referencia (no descender).
    _RUIDO_NODOS: tuple[str, ...] = ("string", "comment")

    def __init__(self) -> None:
        self._parser = _construir_parser(self._GRAMMARS)

    def disponible(self) -> bool:
        return self._parser is not None

    def _desenvolver(self, nodo):
        """Hook: del nodo top al nodo de declaración real. Por defecto
        identidad; jsts lo override para `export [default] <decl>`."""
        return nodo

    def _decl_simbolo(self, nodo, src: bytes) -> Simbolo | None:
        raise NotImplementedError

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
            objetivo = self._desenvolver(nodo)
            if objetivo is None:
                continue
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
            if n.type in self._IDENT_NODOS:
                usados.add(_txt(n, src))
            elif n.type in self._RUIDO_NODOS:
                continue  # no descender: nada de adentro es referencia
            pila.extend(n.children)
        return usados


# ===========================================================================
# jsts (JS/TS/JSX/TSX) — capa 16, VERIFICADO en VPS. Lógica byte-idéntica a
# la original: helpers y `_decl_simbolo` no cambiaron; sólo se movieron el
# armado del parser, `disponible`, el recorrido y `referencias` al base.
# ===========================================================================


def _deps_ts(nodo, src: bytes) -> frozenset[str]:
    return _deps(nodo, src, "statement_block")


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


class TreeSitter(_TSBase):
    _GRAMMARS = (
        ("tree_sitter_typescript", "language_tsx"),
        ("tree_sitter_typescript", "language_typescript"),
        ("tree_sitter_javascript", "language"),
    )
    _IDENT_NODOS = ("identifier", "type_identifier")
    _RUIDO_NODOS = ("string", "template_string", "comment")

    def _desenvolver(self, nodo):
        if nodo.type != "export_statement":
            return nodo
        # export [default] <decl>
        inner = None
        for h in nodo.children:
            if h.type not in ("export", "default", "{", "}", ";"):
                inner = h
        return inner

    def _decl_simbolo(self, nodo, src: bytes) -> Simbolo | None:
        t = nodo.type
        if t in _DECL_FUNC:
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            return Simbolo(
                nombre=nom, tipo="funcion", fuente=_txt(nodo, src),
                firma=_firma(_hijo_tipo(nodo, "formal_parameters"), src),
                detallado=True, deps=_deps_ts(nodo, src),
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
                deps=_deps_ts(nodo, src),
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
                detallado=True, deps=_deps_ts(valor, src),
            )
        return None


# ===========================================================================
# Go — capa 25. grammar tree-sitter-go. Visibilidad Go = inicial Mayúscula.
# ===========================================================================


def _firma_params(lista_nodo, src: bytes, decl_tipo: str, var_tipo: str,
                   self_tipos: tuple[str, ...] = ()) -> str:
    """Firma normalizada de una lista de parámetros, genérica Go/Rust:
    nombres de los parámetros (estable bajo cambios de cuerpo). `decl_tipo`
    = nodo de una declaración de parámetro; `var_tipo` = un parámetro
    variádico; `self_tipos` = nodos receptor/`self` que se listan como tal.
    Sin nombre (sólo tipo, p.ej. en interfaces) => `_`.
    """
    if lista_nodo is None:
        return "()"
    partes: list[str] = []
    for p in lista_nodo.children:
        t = p.type
        if t in self_tipos:
            partes.append("self")
        elif t == var_tipo:
            ident = _hijo_tipo(p, "identifier", "pattern")
            partes.append("..." + (_txt(ident, src) if ident else ""))
        elif t == decl_tipo:
            # Go: `a, b int` => varios identifier antes del tipo.
            # Rust: `pat: Tipo` => un identifier/_ en el patrón.
            ids = [h for h in p.children
                   if h.type in ("identifier", "field_identifier")]
            if ids:
                partes.extend(_txt(i, src) for i in ids)
            else:
                partes.append("_")
    return "(" + ", ".join(partes) + ")"


def _es_exportado_go(nombre: str) -> bool:
    return bool(nombre) and nombre[0].isupper()


def _superficie_struct_go(tipo_nodo, src: bytes) -> frozenset[str]:
    """Campos EXPORTADOS de un struct Go (Mayúscula inicial) — lo que rompe
    a quien construye/usa el valor. Mismo criterio que jsts/Python."""
    lista = _hijo_tipo(tipo_nodo, "field_declaration_list")
    if lista is None:
        return frozenset()
    pub: set[str] = set()
    for campo in lista.children:
        if campo.type != "field_declaration":
            continue
        for h in campo.children:
            if h.type == "field_identifier":
                nom = _txt(h, src)
                if _es_exportado_go(nom):
                    pub.add(nom)
    return frozenset(pub)


class TreeSitterGo(_TSBase):
    _GRAMMARS = (("tree_sitter_go", "language"),)
    _IDENT_NODOS = (
        "identifier", "type_identifier", "field_identifier",
        "package_identifier",
    )
    _RUIDO_NODOS = (
        "interpreted_string_literal", "raw_string_literal", "comment",
    )

    def _decl_simbolo(self, nodo, src: bytes) -> Simbolo | None:
        t = nodo.type
        if t == "function_declaration":
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            return Simbolo(
                nombre=nom, tipo="funcion", fuente=_txt(nodo, src),
                firma=_firma_params(
                    _hijo_tipo(nodo, "parameter_list"), src,
                    "parameter_declaration",
                    "variadic_parameter_declaration",
                ),
                detallado=True, deps=_deps(nodo, src, "block"),
            )
        if t == "method_declaration":
            # `func (r T) Name(params) ...`: hay 2 parameter_list (receiver y
            # params); el nombre (field_identifier) los separa.
            nom_n = _hijo_tipo(nodo, "field_identifier")
            if nom_n is None:
                return None
            params = None
            visto_nombre = False
            for h in nodo.children:
                if h is nom_n:
                    visto_nombre = True
                elif visto_nombre and h.type == "parameter_list":
                    params = h
                    break
            return Simbolo(
                nombre=_txt(nom_n, src), tipo="funcion",
                fuente=_txt(nodo, src),
                firma=_firma_params(
                    params, src, "parameter_declaration",
                    "variadic_parameter_declaration",
                ),
                detallado=True, deps=_deps(nodo, src, "block"),
            )
        if t == "type_declaration":
            spec = _hijo_tipo(nodo, "type_spec")
            if spec is None:
                return None
            nom = _nombre_decl(spec, src)
            if not nom:
                return None
            cuerpo = next(
                (h for h in spec.children
                 if h.type not in ("type_identifier", "=")),
                None,
            )
            if cuerpo is not None and cuerpo.type == "struct_type":
                return Simbolo(
                    nombre=nom, tipo="clase", fuente=_txt(nodo, src),
                    superficie=_superficie_struct_go(cuerpo, src),
                    detallado=True, deps=_deps(nodo, src, "block"),
                )
            # interface / alias / definición de tipo: ES su interfaz.
            return Simbolo(
                nombre=nom, tipo="tipo", fuente=_txt(nodo, src),
                detallado=True,
            )
        if t in ("var_declaration", "const_declaration"):
            spec = _hijo_tipo(nodo, "var_spec", "const_spec")
            if spec is None:
                return None
            nom = _nombre_decl(spec, src)
            if not nom:
                return None
            return Simbolo(
                nombre=nom, tipo="tipo", fuente=_txt(nodo, src),
                detallado=True,
            )
        return None


# ===========================================================================
# Rust — capa 25. grammar tree-sitter-rust. Visibilidad Rust = `pub`.
# ===========================================================================


def _es_pub_rust(nodo, src: bytes) -> bool:
    return _hijo_tipo(nodo, "visibility_modifier") is not None


def _superficie_struct_rust(nodo, src: bytes) -> frozenset[str]:
    """Campos `pub` de un struct Rust — lo que rompe a quien lo usa."""
    lista = _hijo_tipo(nodo, "field_declaration_list")
    if lista is None:
        return frozenset()
    pub: set[str] = set()
    for campo in lista.children:
        if campo.type != "field_declaration":
            continue
        if not _es_pub_rust(campo, src):
            continue
        nom_n = _hijo_tipo(campo, "field_identifier")
        if nom_n is not None:
            pub.add(_txt(nom_n, src))
    return frozenset(pub)


# item -> "tipo": su definición ES su interfaz (cambio = aviso honesto, sin
# coletilla "sin parser"). Cubre lo que el regex de rust.py listaba.
_RS_TIPO = (
    "enum_item", "trait_item", "type_item", "const_item",
    "static_item", "mod_item", "union_item",
)


class TreeSitterRust(_TSBase):
    _GRAMMARS = (("tree_sitter_rust", "language"),)
    _IDENT_NODOS = ("identifier", "type_identifier", "field_identifier")
    _RUIDO_NODOS = (
        "string_literal", "raw_string_literal", "char_literal",
        "line_comment", "block_comment",
    )

    def _decl_simbolo(self, nodo, src: bytes) -> Simbolo | None:
        t = nodo.type
        if t == "function_item":
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            return Simbolo(
                nombre=nom, tipo="funcion", fuente=_txt(nodo, src),
                firma=_firma_params(
                    _hijo_tipo(nodo, "parameters"), src,
                    "parameter", "variadic_parameter",
                    self_tipos=("self_parameter",),
                ),
                detallado=True, deps=_deps(nodo, src, "block"),
            )
        if t == "struct_item":
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            return Simbolo(
                nombre=nom, tipo="clase", fuente=_txt(nodo, src),
                superficie=_superficie_struct_rust(nodo, src),
                detallado=True, deps=_deps(nodo, src, "block"),
            )
        if t in _RS_TIPO:
            nom = _nombre_decl(nodo, src)
            if not nom:
                return None
            return Simbolo(
                nombre=nom, tipo="tipo", fuente=_txt(nodo, src),
                detallado=True,
            )
        return None
