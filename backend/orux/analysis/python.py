"""Análisis semántico de impacto para Python. Núcleo puro de la capa 6.

El feature estrella del onboarding (README): cambias una clase/función y el
sistema te dice solo —sin clickear nada— qué otros archivos la usan, para
avisar a sus dueños. Esta es la pieza pura que responde "¿qué cambió y quién
lo usa?", sin red ni estado: dado el workspace y el antes/después de un
archivo, devuelve los símbolos de nivel módulo que cambiaron y qué otros
archivos los referencian.

**Por qué Python primero** (decisión del usuario, el README sugería TS): es el
stack del proyecto, `ast` está en la stdlib (cero toolchain externo) y permite
dogfooding sobre el propio orux.

**Alcance mínimo, deuda consciente (README riesgo #2):**

- Solo símbolos *de nivel módulo* (def/class en la raíz del archivo). Métodos,
  anidados y variables no cuentan todavía.
- Las referencias son por *nombre*, no por import resuelto: si `b.py` usa el
  identificador `Usuario` y `a.py` define `Usuario`, se asume relación. No se
  resuelve a qué módulo pertenece realmente. Sobre-aproxima a propósito: como
  hint "míralo", no como verdad de compilador. Resolver imports de verdad es
  trabajo futuro.
- Si el código no parsea (estás a mitad de escribir, lo más normal en un
  editor en vivo), se devuelve vacío en vez de fallar. El análisis solo opina
  sobre código que parsea: cero falsos positivos por estados intermedios.
"""

from __future__ import annotations

import ast


def _parse(source: str) -> ast.Module | None:
    """Parsea o devuelve None si el código está roto (edición a medias)."""
    try:
        return ast.parse(source)
    except SyntaxError:
        return None


def definiciones_top(source: str) -> dict[str, str]:
    """Símbolos de nivel módulo -> su código fuente. {} si no parsea.

    El código fuente del símbolo se usa para detectar si *cambió*: si el texto
    de la función es idéntico, no hubo cambio semántico que avisar.
    """
    arbol = _parse(source)
    if arbol is None:
        return {}
    defs: dict[str, str] = {}
    for nodo in arbol.body:
        if isinstance(
            nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            segmento = ast.get_source_segment(source, nodo)
            defs[nodo.name] = segmento if segmento is not None else ""
    return defs


def referencias(source: str) -> set[str]:
    """Nombres que este archivo usa. Conjunto vacío si no parsea.

    Incluye todo identificador leído (`ast.Name` en contexto Load) y lo que se
    trae con `from ... import X`. Sobre-aproxima (un local que se llame igual
    cuenta): es un hint para mirar, no una resolución exacta.
    """
    arbol = _parse(source)
    if arbol is None:
        return set()
    usados: set[str] = set()
    for nodo in ast.walk(arbol):
        if isinstance(nodo, ast.Name) and isinstance(nodo.ctx, ast.Load):
            usados.add(nodo.id)
        elif isinstance(nodo, ast.ImportFrom):
            for alias in nodo.names:
                usados.add(alias.asname or alias.name)
    return usados


def simbolos_cambiados(viejo: str, nuevo: str) -> set[str]:
    """Símbolos top que cambiaron entre `viejo` y `nuevo` (agregados/quitados/
    modificados). Vacío si `nuevo` no parsea: no opinamos sobre código roto.
    """
    if _parse(nuevo) is None:
        return set()
    antes = definiciones_top(viejo)
    despues = definiciones_top(nuevo)
    cambiados: set[str] = set()
    for nombre, src in despues.items():
        if antes.get(nombre) != src:  # nuevo o con cuerpo distinto
            cambiados.add(nombre)
    for nombre in antes:
        if nombre not in despues:  # eliminado/renombrado
            cambiados.add(nombre)
    return cambiados


def _firma(nodo: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    """Firma normalizada de una función/método: qué parámetros acepta.

    Es lo que de verdad le importa a QUIEN LA LLAMA. Compara nombres, orden,
    posicionales-solo (`/`), keyword-only (`*`), `*args`/`**kw` y si cada
    parámetro tiene default (presencia, no el valor: cambiar un default no
    rompe la llamada). Si esta cadena cambia, una llamada existente puede
    romperse → ESO sí se avisa. Si solo cambió el cuerpo, la firma es igual
    y no se avisa nada.
    """
    a = nodo.args
    partes: list[str] = []
    for arg in a.posonlyargs:
        partes.append(arg.arg)
    if a.posonlyargs:
        partes.append("/")
    n_def = len(a.defaults)
    pos = a.posonlyargs + a.args
    for i, arg in enumerate(a.args):
        # ¿este posicional tiene default? (los defaults aplican a los últimos)
        tiene = i >= len(a.args) - (n_def - len(a.posonlyargs)) if n_def else False
        partes.append(arg.arg + ("=" if tiene else ""))
    if a.vararg:
        partes.append("*" + a.vararg.arg)
    elif a.kwonlyargs:
        partes.append("*")
    for arg, d in zip(a.kwonlyargs, a.kw_defaults):
        partes.append(arg.arg + ("=" if d is not None else ""))
    if a.kwarg:
        partes.append("**" + a.kwarg.arg)
    return "(" + ", ".join(partes) + ")"


def _superficie_clase(nodo: ast.ClassDef) -> tuple[str, frozenset[str]]:
    """Lo que una clase EXPONE: cómo se construye + sus miembros públicos.

    Devuelve (firma de __init__, {métodos/atributos públicos}). "Público" =
    no empieza con `_`. Quitar/renombrar un miembro público, o cambiar el
    __init__, rompe a quien usa la clase; tocar un método privado o el
    cuerpo de uno público, no. Esa es la línea entre aviso real y ruido.
    """
    init = ""
    publicos: set[str] = set()
    for hijo in nodo.body:
        if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if hijo.name == "__init__":
                init = _firma(hijo)
            if not hijo.name.startswith("_"):
                publicos.add(hijo.name + "()")
        elif isinstance(hijo, ast.AnnAssign) and isinstance(
            hijo.target, ast.Name
        ):
            if not hijo.target.id.startswith("_"):
                publicos.add(hijo.target.id)
        elif isinstance(hijo, ast.Assign):
            for t in hijo.targets:
                if isinstance(t, ast.Name) and not t.id.startswith("_"):
                    publicos.add(t.id)
    return init, frozenset(publicos)


def _nombres_en(nodo: ast.AST | None) -> set[str]:
    """Identificadores de tipo dentro de una anotación: `Usuario`,
    `list[Usuario]`, `mod.Usuario` -> {Usuario, ...}. Sobre-aproxima (toma
    Name y el .attr de Attribute): es un hint, mismo espíritu que el resto
    del análisis por nombre."""
    if nodo is None:
        return set()
    out: set[str] = set()
    for n in ast.walk(nodo):
        if isinstance(n, ast.Name):
            out.add(n.id)
        elif isinstance(n, ast.Attribute):
            out.add(n.attr)
    return out


def _deps_interfaz(nodo: ast.AST) -> frozenset[str]:
    """Nombres de TIPO que aparecen en la INTERFAZ del símbolo (lo que ven
    sus usuarios): retorno y params de funciones, bases de clase, tipos del
    __init__ y de métodos/atributos públicos. Capa 24b: el impacto
    transitivo propaga a través de esto (una función que retorna `Usuario`
    depende de `Usuario` en su contrato, no solo en su cuerpo).
    """
    deps: set[str] = set()

    def _de_args(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        a = fn.args
        for arg in (
            *a.posonlyargs, *a.args, *a.kwonlyargs,
            a.vararg, a.kwarg,
        ):
            if arg is not None:
                deps.update(_nombres_en(arg.annotation))
        deps.update(_nombres_en(fn.returns))

    if isinstance(nodo, (ast.FunctionDef, ast.AsyncFunctionDef)):
        _de_args(nodo)
    elif isinstance(nodo, ast.ClassDef):
        for base in nodo.bases:
            deps.update(_nombres_en(base))
        for hijo in nodo.body:
            if isinstance(hijo, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if hijo.name == "__init__" or not hijo.name.startswith("_"):
                    _de_args(hijo)
            elif isinstance(hijo, ast.AnnAssign) and isinstance(
                hijo.target, ast.Name
            ) and not hijo.target.id.startswith("_"):
                deps.update(_nombres_en(hijo.annotation))
    return frozenset(deps)


def _nodos_top(source: str) -> dict[str, ast.AST]:
    arbol = _parse(source)
    if arbol is None:
        return {}
    out: dict[str, ast.AST] = {}
    for nodo in arbol.body:
        if isinstance(
            nodo, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            out[nodo.name] = nodo
    return out


def cambios_que_importan(viejo: str, nuevo: str) -> dict[str, str]:
    """Símbolo top -> POR QUÉ su cambio le importa a quien lo usa.

    El corazón del arreglo: el análisis dejaba de ser adorno cuando, en vez
    de "algo cambió", dice "cambió la firma de X" o "X ya no existe" — y solo
    cuando ESO pasa. Cambiar el cuerpo de una función sin tocar su firma NO
    aparece acá: el que la llama no se entera ni le importa. Vacío si `nuevo`
    no parsea (no opinamos sobre código a medio escribir).

    Casos que importan (mínimo, real):
    - símbolo eliminado o renombrado;
    - función: cambió su firma (parámetros);
    - clase: cambió cómo se construye (__init__) o se quitó/renombró un
      miembro público.
    """
    if _parse(nuevo) is None:
        return {}
    antes = _nodos_top(viejo)
    despues = _nodos_top(nuevo)
    motivos: dict[str, str] = {}

    for nombre, na in antes.items():
        nd = despues.get(nombre)
        if nd is None:
            motivos[nombre] = (
                f"se eliminó o renombró «{nombre}» — el código que lo usa "
                f"va a romper"
            )
            continue
        # Función top-level: ¿cambió la firma?
        if isinstance(na, (ast.FunctionDef, ast.AsyncFunctionDef)) and isinstance(
            nd, (ast.FunctionDef, ast.AsyncFunctionDef)
        ):
            fa, fd = _firma(na), _firma(nd)
            if fa != fd:
                motivos[nombre] = (
                    f"cambió la firma de «{nombre}»: {fa} → {fd} — revisá "
                    f"las llamadas"
                )
        # Clase: ¿cambió su construcción o su superficie pública?
        elif isinstance(na, ast.ClassDef) and isinstance(nd, ast.ClassDef):
            ia, pa = _superficie_clase(na)
            idef, pd = _superficie_clase(nd)
            if ia != idef:
                motivos[nombre] = (
                    f"cambió cómo se construye «{nombre}»: __init__{ia} → "
                    f"__init__{idef}"
                )
            else:
                quitados = pa - pd
                if quitados:
                    cosas = ", ".join(sorted(quitados))
                    motivos[nombre] = (
                        f"«{nombre}» ya no expone: {cosas} — quien lo usaba "
                        f"va a romper"
                    )
        # Cambió de def a class (o viceversa): cómo se usa cambia de raíz.
        elif type(na) is not type(nd):
            motivos[nombre] = (
                f"«{nombre}» cambió de tipo de definición — revisá cómo lo usás"
            )
    return motivos


def impacto(
    workspace: dict[str, str], path: str, viejo: str, nuevo: str
) -> dict[str, list[str]]:
    """Símbolo cambiado en `path` -> otros archivos .py que lo referencian.

    Esta es la pregunta del onboarding: "cambié esto, ¿a quién le importa?".
    Solo mira archivos `.py` del workspace, excluye el propio `path`, y solo
    reporta símbolos que de verdad cambiaron. Un símbolo sin usos en ningún
    otro archivo no aparece (no hay a quién avisar).
    """
    if not path.endswith(".py"):
        return {}
    # Antes: simbolos_cambiados (disparaba con CUALQUIER cambio de cuerpo →
    # adorno ruidoso). Ahora: solo los cambios que de verdad afectan a quien
    # usa el símbolo. Si solo cambió un cuerpo, esto es {} y no se avisa nada.
    cambiados = cambios_que_importan(viejo, nuevo)
    if not cambiados:
        return {}
    resultado: dict[str, list[str]] = {}
    for sym in cambiados:
        afectados = sorted(
            otro
            for otro, contenido in workspace.items()
            if otro != path
            and otro.endswith(".py")
            and sym in referencias(contenido)
        )
        if afectados:
            resultado[sym] = afectados
    return resultado
