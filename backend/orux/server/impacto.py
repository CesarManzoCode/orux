"""Notificación de impacto (capas 6/24) y propagación de rename (capa 26).

El "núcleo" del producto desde la perspectiva del dev: cuando alguien
salva (capa 19), Orux ejecuta el análisis semántico, descubre qué
archivos OTROS se ven impactados por el cambio, y le manda un aviso
accionable al dueño de cada uno. En premium hay además una onda
transitiva (capa 24) y un rename codemod automático (capa 26).

Extraído de `sync.py` (modularización 2026-05-23): la lógica de
impacto era ~290 líneas de comportamiento cohesivo (análisis +
broadcast a dueños) que viven mejor aparte. Reciben `server` por
parámetro para usar los broadcasts ya cableados (`_enviar_a`,
`_broadcast_todos`, `_persistir_prop`, `teams`). NO se usa mixin para
preservar el tipo `SyncServer` claro en `sync.py`.
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from ..analysis import impacto, motivos as motivos_de, tiers
from ..analysis.modelo import severidad_de
from ..analysis.rename import Rename, aplicar_rename, texto_sugerencia
from ..analysis.tiers import lenguaje_de
from ..analysis.transitive import impacto_transitivo
from ..plans import limites
from ..protocol import (
    ImpactMessage,
    ProposalMessage,
    UpdateMessage,
    encode,
)

if TYPE_CHECKING:
    from .runtime import TeamRuntime
    from .sync import SyncServer


async def notificar_impacto(
    server: "SyncServer",
    rt: "TeamRuntime",
    path: str,
    viejo: str,
    nuevo: str,
    autor_id: str,
    autor_nombre: str,
    *,
    rename: Rename | None = None,
) -> None:
    """Capa 6: avisa al dueño de cada archivo afectado por este cambio.

    Capa 26: `rename` (free) = se detectó un rename de miembro confiable
    pero el plan NO aplica el codemod; el aviso de ESE símbolo se
    reescribe al texto accionable ("se renombró X→Y, actualizá los
    usos"). `rename=None` => comportamiento byte-idéntico a capa 6/24
    (todos los tests previos siguen valiendo sin tocarse).

    "Sin clickear, lo hace solo" (README). Reglas: si el afectado no
    tiene dueño no hay a quién avisar; si no parsea, `impacto` da {} y
    no manda nada. Todo scopeado al workspace/ownership de ESTE equipo.

    Decisión del usuario: el aviso TAMBIÉN va al autor cuando el
    afectado le pertenece. Misma tesis aplicada de forma simétrica —
    si cambiar `Usuario` rompe `auth.py`, importa por igual sea quien
    sea el dueño de `auth.py`. El archivo origen del cambio ya queda
    fuera por `archivos_afectados` (filtra `o != path`), así que no
    hay auto-eco del archivo recién editado: solo OTROS archivos
    suyos donde el símbolo realmente se usa.
    """
    # Capa 16: el análisis corre casi por tecla y antes era SÍNCRONO en
    # el event loop — bloqueaba presencia/locks/broadcasts de TODO el
    # equipo. Ahora todo el trabajo (incl. el lazy-arranque de pyright,
    # que hace spawn+handshake bloqueante) va a UN hilo: ni el parser C
    # ni el subproceso LSP tocan el event loop. Capa 17: la sesión LSP
    # del equipo (tibia) hace el fan-out resolución-real; si no hay
    # (sandbox/sin pyright) o falla, `impacto`/`motivos` degradan solos
    # a capa 16. Seguro: `snapshot()` es copia, todo lo demás strings.
    snap = rt.workspace.snapshot()
    # Capa 22: el cap de lenguajes LSP del plan se lee acá (el store es
    # async, vive en el loop) y se pasa al hilo. Premium = sin tope.
    plan = await server.teams.plan(rt.team_id)
    cap_langs = limites(plan)["max_langs"]

    # Capa 24 (rehecho): el camino DIRECTO (capas 17-21) corre SIEMPRE,
    # free y premium. Es el aviso de alto valor ("cambió la firma de X
    # → revisá las llamadas", severidad real). Antes premium hacía
    # `return` ANTES de esto y solo mandaba la onda transitiva: te dejaba
    # SIN el aviso bueno y encima mal etiquetado. Bug arreglado: premium
    # = free + cadena (la cadena se agrega DESPUÉS, sin reemplazar nada).
    def _analizar() -> tuple[dict, dict, str]:
        ses = rt.lsp_sesion(lenguaje_de(path), cap_langs)
        af = impacto(snap, path, viejo, nuevo, ses)
        if not af:
            return {}, {}, ""
        # Capa 35: el analizador efectivo se decide ACÁ, con la misma
        # sesión LSP que se intentó usar. Etiquetar afuera, recalculando,
        # se desincronizaría con el resultado real (un retry/cache de la
        # sesión podría diferir). Acá es la verdad.
        return (
            af,
            motivos_de(path, viejo, nuevo, ses),
            tiers.analizador_efectivo(path, ses),
        )

    afectados, razones, analiz_directo = await asyncio.to_thread(_analizar)
    if not afectados:
        return
    # Capa 26 (free): el cambio ES un rename confiable pero el plan no
    # lo aplica solo. Se cambia el "por qué" de ESE símbolo por el
    # qué-hacer concreto; el resto del aviso (a quién, byte-idéntico).
    if rename is not None and rename.clase in razones:
        razones = {**razones, rename.clase: texto_sugerencia(rename)}
    # Reagrupamos símbolo->archivos ==> archivo_afectado->símbolos.
    por_archivo: dict[str, list[str]] = {}
    for simbolo, archivos in afectados.items():
        for af in archivos:
            por_archivo.setdefault(af, []).append(simbolo)
    for af, simbolos in por_archivo.items():
        dueño = rt.ownership.owner(af)
        # El autor SÍ recibe aviso si el afectado le pertenece
        # (decisión del usuario): saber qué de tu propio código usa
        # lo que acabás de tocar es la misma tesis aplicada simétrica.
        if dueño is None:
            continue
        syms = sorted(simbolos)
        await server._enviar_a(
            rt,
            dueño,
            encode(
                ImpactMessage(
                    source_path=path,
                    author_name=autor_nombre,
                    affected_path=af,
                    symbols=syms,
                    motivos=[razones.get(s, "") for s in syms],
                    severidades=[
                        severidad_de(razones.get(s, "")) for s in syms
                    ],
                    analizador=analiz_directo,
                )
            ),
        )

    # --- Capa 24 (premium) = free + cadena -----------------------------
    # El directo de arriba YA se mandó (free y premium igual). Premium
    # AGREGA la onda por interfaz contaminada que llega MÁS ALLÁ del
    # directo. Decisión del usuario: se descartan (a) los hops
    # TERMINALES (uso en cuerpo: no se propaga, era ruido redundante con
    # el directo) y (b) los archivos que el directo YA cubrió (el
    # cliente deduplica por source+affected: un 2º mensaje los pisaría).
    # Resultado: premium NUNCA peor que free; la cadena solo suma valor.
    if limites(plan)["impacto"] != "transitivo":
        return
    directos = set(por_archivo)
    # Capa 35: el transitivo NO usa LSP a propósito (decisión de costo:
    # un símbolo aguas-abajo no justifica el round-trip a pyright). Su
    # analizador efectivo es el del tier de detección sin LSP — el chip
    # del cliente refleja eso.
    analiz_trans = tiers.analizador_efectivo(path, None)

    def _trans():
        lang = lenguaje_de(path)
        tier = tiers.tier_para(path)
        if tier is None or lang is None:
            return {}, False
        cambiados = list(tiers.cambios(path, viejo, nuevo))
        if not cambiados:
            return {}, False
        # Perf (capa 24c): índice de referencias 1 vez/análisis;
        # `extraer` memoizado por contenido (no D×N parseos).
        refs_idx = {
            f: tier.referencias(c)
            for f, c in snap.items()
            if lenguaje_de(f) == lang
        }

        def _fan(s: str, origen: str) -> set[str]:
            return {
                f for f, r in refs_idx.items()
                if f != origen and s in r
            }

        _cache: dict[str, dict] = {}

        def _extraer(c: str):
            if c not in _cache:
                _cache[c] = tier.simbolos(c) or {}
            return _cache[c]

        return impacto_transitivo(
            snap, path, cambiados, fan_out=_fan,
            extraer=_extraer, lenguaje_de=lenguaje_de,
        )

    out, trunc = await asyncio.to_thread(_trans)
    sufijo = (
        " · análisis truncado (cambio muy amplio)" if trunc else ""
    )
    for af, items in out.items():
        if af in directos:
            continue  # ya lo cubrió el directo (no duplicar/pisar)
        dueño = rt.ownership.owner(af)
        # Misma simetría que el directo: el autor también recibe la
        # onda transitiva si el archivo aguas-abajo le pertenece.
        if dueño is None:
            continue
        # Solo la propagación REAL (interfaz contaminada). Terminal =
        # uso en cuerpo: no es la onda, es ruido (decisión del usuario).
        props = [d for d in items if not d["terminal"]]
        if not props:
            continue
        props.sort(key=lambda d: (d["cadena"][0], len(d["cadena"])))
        # Bug #2 arreglado: el encabezado nombra lo que REALMENTE
        # cambió (el símbolo ORIGEN de la cadena, que vive en
        # source_path), no el símbolo terminal. `cadena[0]` =
        # "<path>:<sym_original>" -> el sym es lo de después del último
        # ":" (los paths del workspace y los símbolos no llevan ":").
        syms = [d["cadena"][0].rsplit(":", 1)[1] for d in props]
        await server._enviar_a(
            rt,
            dueño,
            encode(
                ImpactMessage(
                    source_path=path,
                    author_name=autor_nombre,
                    affected_path=af,
                    symbols=syms,
                    motivos=[d["motivo"] + sufijo for d in props],
                    severidades=[
                        severidad_de(d["motivo"]) for d in props
                    ],
                    cadena=props[0]["cadena"],
                    analizador=analiz_trans,
                )
            ),
        )


async def propagar_rename(
    server: "SyncServer",
    rt: "TeamRuntime",
    path: str,
    viejo: str,
    nuevo: str,
    ren: Rename,
    autor_id: str,
    autor_nombre: str,
) -> None:
    """Capa 26 (premium): propaga un rename de miembro detectado a quien
    usa la clase, como **propuesta tentativa de capa 4 VERBATIM** — la
    misma ventana aprobar/rechazar que ya conocen. Cero UX/protocolo
    nuevo: la feature entra por la puerta que ya existe.

    Reusa el fan-out de capas 17-21 (`impacto`) para saber QUÉ archivos
    usan la clase de verdad: con sesión LSP viva es resolución real
    (mata falsos positivos); sin ella degrada a token-scan, igual que
    TODO el análisis. El dueño REVISA el diff y aprueba/rechaza: no es
    auto-commit a ciegas — la aprobación es la red de seguridad que
    hace seguro un codemod heurístico (la tesis trabajando a favor).
    """
    snap = rt.workspace.snapshot()
    plan = await server.teams.plan(rt.team_id)
    cap_langs = limites(plan)["max_langs"]

    def _afectados() -> dict[str, list[str]]:
        ses = rt.lsp_sesion(lenguaje_de(path), cap_langs)
        return impacto(snap, path, viejo, nuevo, ses)

    afectados = await asyncio.to_thread(_afectados)
    for af in afectados.get(ren.clase, []):
        if af == path:
            continue  # el origen ya tiene el rename (lo hizo el autor)
        contenido = snap.get(af)
        if contenido is None:
            continue
        propuesto = aplicar_rename(contenido, ren.viejo, ren.nuevo)
        if propuesto == contenido:
            continue  # el acceso no aparece textual acá: nada que hacer
        dueño = rt.ownership.owner(af)
        # Capa 26 (premium): el cambio lo construye el server (codemod
        # `aplicar_rename`), no lo tipeó nadie en ese archivo. El dueño
        # ve un autor explícito "OruxBot" para que la propuesta se lea
        # como "el sistema te propone esto" — misma ventana aprobar/
        # rechazar de capa 4, solo cambia quién aparece arriba. El
        # contexto del rename va en el mismo string (lo que cambió a lo
        # que pasa). `author_id` queda como el client_id real del que
        # disparó el rename: si el dueño rechaza, el revert (capa 4) le
        # llega a esa identidad y no a un id sintético sin conexión.
        etiqueta = f"OruxBot · rename {ren.viejo}→{ren.nuevo}"
        if dueño is None or dueño == autor_id:
            # Sin dueño o propio: se aplica directo (igual que un
            # update de capa 4 sin dueño). El baseline avanza: el
            # codemod ya es un punto coherente, no re-avisar sobre él.
            rt.workspace.update(af, propuesto)
            rt._analizado[af] = propuesto
            await server._broadcast_todos(
                rt, encode(UpdateMessage(path=af, content=propuesto))
            )
        else:
            # Dueño ajeno: propuesta capa 4 VERBATIM. La etiqueta lleva
            # el contexto -> el dueño ve "Ana · rename x→y propone
            # cambios a af" + el diff, con la MISMA UI de siempre.
            prop = rt.proposals.put(
                path=af,
                author_id=autor_id,
                author_name=etiqueta,
                content=propuesto,
            )
            await server._persistir_prop(rt, prop)
            await server._enviar_a(
                rt, dueño, encode(ProposalMessage(proposal=prop))
            )
