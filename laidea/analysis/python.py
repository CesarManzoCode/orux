"""Análisis semántico de impacto para Python. Núcleo puro de la capa 6.

El feature estrella del onboarding (README): cambias una clase/función y el
sistema te dice solo —sin clickear nada— qué otros archivos la usan, para
avisar a sus dueños. Esta es la pieza pura que responde "¿qué cambió y quién
lo usa?", sin red ni estado: dado el workspace y el antes/después de un
archivo, devuelve los símbolos de nivel módulo que cambiaron y qué otros
archivos los referencian.

**Por qué Python primero** (decisión del usuario, el README sugería TS): es el
stack del proyecto, `ast` está en la stdlib (cero toolchain externo) y permite
dogfooding sobre el propio laidea.

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
    cambiados = simbolos_cambiados(viejo, nuevo)
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
