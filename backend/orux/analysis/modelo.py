"""Modelo de símbolo normalizado + la lógica ÚNICA de "qué cambió que importa".

Capa 16 (jerarquía de analizadores). Diseño cerrado con el usuario: en vez de
un módulo por lenguaje con su propia copia de la lógica de impacto, hay UN
modelo de símbolo común que CUALQUIER analizador (tier) produce, y UNA sola
función que decide qué cambio le importa a quien usa el símbolo. La diferencia
entre lenguajes deja de ser código distinto y pasa a ser una *capacidad del
tier*: si el analizador supo aislar la firma (`detallado=True`) se da el aviso
fino; si no (un heurístico sin parser, `detallado=False`) se da el genérico
honesto. Es exactamente la línea que hoy separa `python.py` (ast, fino) de
`javascript.py` (regex, genérico) — ahora expresada como datos, no como dos
implementaciones paralelas.

Por qué un modelo y no "que cada tier devuelva sus mensajes": un tier nuevo
(tree-sitter, mañana pyright) solo tiene que rellenar este `Simbolo`; no
reescribe la regla de negocio ni puede divergir de ella. La regla vive una
vez, acá, y se testea una vez.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

# Severidad del aviso. Union de strings (como `type: Literal[...]` del
# protocolo): documenta el dominio en UN lugar y lo chequea el typechecker.
Severidad = Literal["alta", "media", "baja"]


@dataclass(frozen=True)
class Simbolo:
    """Un símbolo de nivel módulo, visto por cualquier tier de análisis.

    - `nombre`: identificador top-level (función/clase).
    - `tipo`: "funcion" | "clase" (extensible; un tier que no distingue pone
      "?" y queda como opaco vía `detallado=False`).
    - `fuente`: texto del símbolo. Se compara para saber si cambió ALGO; no
      decide *qué* cambió (eso lo dan los campos finos). Un tier sin parser
      usa una región aproximada — suficiente para "algo cambió".
    - `firma`: firma normalizada si es función y el tier la pudo aislar; si
      no, "".
    - `init`: firma del constructor si es clase y el tier la aisló; si no, "".
    - `superficie`: miembros públicos de la clase si el tier los aisló; si
      no, frozenset() vacío.
    - `detallado`: True solo si el tier aisló interfaz de cuerpo (parser
      real). False = heurístico: solo puede decir "cambió/desapareció", no
      separar firma de cuerpo. Es la capacidad del tier, no del símbolo.
    - `deps`: nombres de TIPO que aparecen en la INTERFAZ del símbolo
      (anotación de retorno, anotaciones de parámetros, bases de clase,
      tipos de miembros públicos). Capa 24b: lo usa el impacto transitivo
      para propagar por dependencia de tipos. ADITIVO y aparte de `firma`
      a propósito: `cambios_que_importan_modelo` (capas 6/19) NO lo mira,
      así que esos avisos quedan byte-idénticos.
    """

    nombre: str
    tipo: str
    fuente: str
    firma: str = ""
    init: str = ""
    superficie: frozenset[str] = frozenset()
    detallado: bool = False
    deps: frozenset[str] = frozenset()


def cambios_que_importan_modelo(
    antes: dict[str, Simbolo], despues: dict[str, Simbolo]
) -> dict[str, str]:
    """Símbolo -> POR QUÉ su cambio le importa a quien lo usa. Tier-agnóstico.

    Es la misma regla de negocio de la capa 6/15, ahora una sola vez sobre el
    modelo. Reproduce EXACTO los dos comportamientos que hoy viven separados:

    - Tier detallado (parser, p.ej. Python-ast): avisa por eliminado/
      renombrado, firma de función cambiada, construcción de clase cambiada o
      miembro público quitado, def↔class. Cambio de cuerpo sin tocar interfaz
      => silencio (eso mata el "¿y a mí qué?").
    - Tier no detallado (heurístico, p.ej. regex JS/TS): el caso fuerte
      ("se eliminó/renombró", rompe seguro) se distingue igual; un cambio
      interno no se puede separar de uno de interfaz => "cambió, revisá".
      Un símbolo NUEVO no rompe a nadie que ya existía => silencio.

    Vacío (`{}`) si no hay símbolos (tier no opinó / código a medio escribir):
    el server entonces no avisa nada y nada se rompe.
    """
    motivos: dict[str, str] = {}

    # Eliminado/renombrado: idéntico en ambos comportamientos (rompe seguro).
    for nombre in antes:
        if nombre not in despues:
            motivos[nombre] = (
                f"se eliminó o renombró «{nombre}» — el código que lo usa "
                f"va a romper"
            )

    for nombre, a in antes.items():
        d = despues.get(nombre)
        if d is None:
            continue  # ya cubierto arriba
        if a.fuente == d.fuente:
            continue  # no cambió nada textualmente: no hay nada que avisar

        # Tier sin parser (heurístico): no puede separar firma de cuerpo.
        # Honesto sobre su límite, igual que el viejo javascript.py.
        # BACKEND-AUDIT-0122: el mensaje no menciona TS específicamente
        # (Go/Rust/JS también cae al heurístico cuando falta el grammar).
        if not (a.detallado and d.detallado):
            motivos[nombre] = (
                f"«{nombre}» cambió — sin parser fino para este lenguaje "
                f"no puedo separar firma de cuerpo; revisá si tu uso sigue válido"
            )
            continue

        # Tier detallado: aislamos qué cambió de la INTERFAZ (no del cuerpo).
        if a.tipo != d.tipo:
            motivos[nombre] = (
                f"«{nombre}» cambió de tipo de definición — revisá cómo lo usás"
            )
        elif a.tipo == "funcion":
            if a.firma != d.firma:
                motivos[nombre] = (
                    f"cambió la firma de «{nombre}»: {a.firma} → {d.firma} — "
                    f"revisá las llamadas"
                )
            # firma igual, solo cambió el cuerpo => silencio (a propósito)
        elif a.tipo == "tipo":
            # type/interface/enum (TS): no hay "cuerpo" separable de la
            # interfaz — su definición ES su contrato. Un tier detallado
            # (tree-sitter) puede afirmarlo sin la coletilla "sin parser".
            motivos[nombre] = (
                f"cambió «{nombre}» — su definición es su interfaz; "
                f"revisá los usos"
            )
        elif a.tipo == "clase":
            if a.init != d.init:
                motivos[nombre] = (
                    f"cambió cómo se construye «{nombre}»: __init__{a.init} → "
                    f"__init__{d.init}"
                )
            else:
                quitados = a.superficie - d.superficie
                if quitados:
                    cosas = ", ".join(sorted(quitados))
                    motivos[nombre] = (
                        f"«{nombre}» ya no expone: {cosas} — quien lo usaba "
                        f"va a romper"
                    )
                # superficie intacta, cuerpo cambió => silencio (a propósito)
    return motivos


# Severidad del aviso (capa 24d). Clasifica por keywords de NUESTROS propios
# motivos (los controlamos: determinista). ADITIVO — no cambia ningún
# mensaje ni el shape de `cambios_que_importan_modelo`; solo lo interpreta
# para priorizar el triage del dueño.
#   alta  = rompe casi seguro (eliminado/firma/construcción/superficie/tipo-def)
#   media = puede romper / revisá (tipo cambió, sin parser, se propaga)
#   baja  = uso en cuerpo, la onda cortó ahí (probablemente no te afecta)
_SEV_ALTA = (
    "se eliminó o renombró",
    # Capa 26: el aviso de rename ("se renombró «x» → «y» …") rompe a quien
    # usa el miembro -> es ALTA, no "media". No reclasifica nada más: la
    # cadena genérica "se eliminó o renombró" ya era alta por sí sola.
    "se renombró",
    "cambió la firma de",
    "cambió cómo se construye",
    "ya no expone",
    "cambió de tipo de definición",
)
_SEV_BAJA = ("en su cuerpo — revisá",)


def severidad_de(motivo: str) -> Severidad:
    """'alta' | 'media' | 'baja'. Desconocido => 'media' (no sub-avisar)."""
    if any(k in motivo for k in _SEV_ALTA):
        return "alta"
    if any(k in motivo for k in _SEV_BAJA):
        return "baja"
    return "media"
