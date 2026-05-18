"""Capa 26: rename seguro coordinado (premium) — núcleo PURO y sandbox-testeable.

Diseño cerrado con el usuario (NO re-litigar). El flujo: User1 renombra una
variable/miembro de interfaz de su clase (`variable` -> `name`) editando
normal + Ctrl+S; el sistema lo detecta y propaga el cambio a quien usa esa
clase como una **propuesta tentativa de capa 4 VERBATIM** (la misma ventana
aprobar/rechazar que ya conocen). Cero UX nueva, cero protocolo nuevo:
"entra a la perfección en lo que ya está".

Este módulo NO toca red ni LSP: es la parte 100% testeable sin internet.
Dos piezas:

- `detectar_rename(antes, despues)`: a partir de los `Simbolo` que YA produce
  cualquier tier (capa 16: ast/tree-sitter/regex), decide si el cambio es un
  *rename de miembro* CONFIABLE. Guardarraíl crítico de confianza: solo
  cuando el emparejamiento quitado<->agregado es inequívoco (exactamente 1
  miembro removido + 1 agregado en la MISMA clase, mismo tipo de miembro,
  constructor intacto). Ante cualquier duda -> None: el sistema se comporta
  como hoy (aviso de impacto normal) y NO reescribe. Sub-ofrecer es
  preferible a reescribir mal el código de alguien (un solo "orux me
  cambió mal el código" mata la confianza ganada en capas 16-21).

- `aplicar_rename(contenido, viejo, nuevo)`: el codemod mecánico mínimo y
  HONESTO sobre su límite — renombra el acceso a miembro `.viejo` -> `.nuevo`.
  NO toca strings/dinámico/reflexión/kwargs (`C(viejo=...)`): eso lo dice
  claro la copy y, sobre todo, el dueño REVISA el diff antes de aprobarlo
  (la aprobación de capa 4 es la red de seguridad: no es auto-commit a
  ciegas, es una propuesta revisable). Funciona igual en py/ts/go/rust:
  todos usan acceso por punto y el modelo de `Simbolo` ya es agnóstico.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .modelo import Simbolo


@dataclass(frozen=True)
class Rename:
    """Un rename de miembro de interfaz, detectado con confianza.

    - `clase`: el símbolo (clase/struct) cuya superficie cambió — es el
      símbolo que el fan-out (capas 17-21) resuelve para saber qué archivos
      lo usan, exactamente el mismo que el impacto normal reportaría.
    - `viejo`/`nuevo`: nombre del miembro, SIN el sufijo `()` de método (el
      codemod renombra el identificador, no la forma de llamada).
    """

    clase: str
    viejo: str
    nuevo: str


def _pelar(miembro: str) -> tuple[str, bool]:
    """`"foo()"` -> ("foo", True método) ; `"bar"` -> ("bar", False atributo).
    La superficie de `Simbolo` marca los métodos con `()` (ver capa 16)."""
    if miembro.endswith("()"):
        return miembro[:-2], True
    return miembro, False


def detectar_rename(
    antes: dict[str, Simbolo], despues: dict[str, Simbolo]
) -> Rename | None:
    """¿El cambio es un rename de miembro CONFIABLE? Si sí, cuál; si hay la
    más mínima duda, None (el sistema se comporta como hoy, no reescribe).

    Confianza = inequívoco: una clase presente antes y después, su
    constructor intacto, y su superficie cambió en EXACTAMENTE un miembro
    quitado + un miembro agregado, del mismo tipo (ambos método o ambos
    atributo). Eso casa 1:1 viejo->nuevo sin adivinar. Cualquier otra cosa
    (2 cambios, cambió el __init__, no es clase, no parsea => dict vacío)
    cae a None. Devuelve el PRIMer rename así (un save enfocado renombra una
    cosa; multi-rename simultáneo es raro y queda para una capa futura).
    """
    for nombre, a in antes.items():
        d = despues.get(nombre)
        if d is None:
            continue
        # Solo clases/structs (tienen superficie). El tier detallado marca
        # tipo "clase"; los no detallados ("?") no aíslan superficie => no
        # se arriesga un rename sobre un heurístico ciego.
        if a.tipo != "clase" or d.tipo != "clase":
            continue
        # Si además cambió cómo se construye, NO es un rename limpio de
        # miembro: es un cambio mayor -> que lo vea el impacto normal.
        if a.init != d.init:
            continue
        quitados = a.superficie - d.superficie
        agregados = d.superficie - a.superficie
        if len(quitados) != 1 or len(agregados) != 1:
            continue
        viejo, viejo_m = _pelar(next(iter(quitados)))
        nuevo, nuevo_m = _pelar(next(iter(agregados)))
        if viejo_m != nuevo_m:
            continue  # método<->atributo: no es el mismo miembro renombrado
        if not viejo or not nuevo or viejo == nuevo:
            continue
        return Rename(clase=nombre, viejo=viejo, nuevo=nuevo)
    return None


def aplicar_rename(contenido: str, viejo: str, nuevo: str) -> str:
    """Codemod mecánico mínimo: renombra el acceso a miembro `.viejo` ->
    `.nuevo` (incluye `self.viejo`, `obj.viejo`). Honesto sobre su límite a
    propósito: no toca strings/comentarios/kwargs/atributos por reflexión.
    No pretende ser perfecto — el dueño revisa el diff antes de aprobar la
    propuesta (capa 4 = la red de seguridad). Idempotente y conservador:
    `\\b` evita pisar `.variableX`; si no hay nada que cambiar, devuelve el
    mismo texto (el server entonces no propone nada a ese archivo).

    Guard de robustez (B-varios): `viejo`/`nuevo` vacío => no-op. Hoy
    `detectar_rename` ya garantiza ambos no vacíos, pero esta función es
    pública y reutilizable; con `viejo=""` el patrón sería `\\.\\b` y
    reescribiría cada punto del archivo (corrupción masiva). Fail-safe: ante
    un argumento degenerado, no tocar nada."""
    if not viejo or not nuevo:
        return contenido
    patron = re.compile(r"\." + re.escape(viejo) + r"\b")
    return patron.sub("." + nuevo, contenido)


def texto_sugerencia(r: Rename) -> str:
    """Free: el aviso de TEXTO accionable (sin aplicar nada). Reemplaza el
    genérico "«C» ya no expone: variable" por el qué-hacer concreto. El
    valor (saber qué y dónde) es gratis; premium automatiza la mano."""
    return (
        f"se renombró «{r.viejo}» → «{r.nuevo}» en «{r.clase}» — "
        f"actualizá los usos a «{r.nuevo}» (premium lo aplica por vos)"
    )
