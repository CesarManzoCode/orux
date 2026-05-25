"""Use cases de impacto y propagación de rename (capa 19/24/26).

Extraído de `server/impacto.py` para que la orquestación viva en application
y no en server. Las funciones reciben `TeamRuntime` + Ports + datos del
cambio, y devuelven **efectos** (mensajes a emitir, propuestas a persistir).
El inbound (`server/dispatch.py:_h_save`) los traduce a sends del WebSocket.

Nota: `rt.lsp_sesion(lang, cap)` se sigue invocando desde acá porque la
gestión LSP vive en el runtime (sesiones tibias por equipo). Conceptualmente
encajaría en `LspFactoryPort`, pero el runtime ya cachea/recicla/cooldown
las sesiones; mover ese ciclo es otro refactor.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from ..analysis import impacto as analizar_impacto
from ..analysis import motivos as analizar_motivos
from ..analysis import tiers
from ..analysis.modelo import severidad_de
from ..analysis.rename import (
    Rename,
    aplicar_rename,
    texto_sugerencia,
)
from ..analysis.tiers import lenguaje_de
from ..analysis.transitive import impacto_transitivo
from ..plans import limites
from ..ports import ProposalsStorePort, TeamStorePort
from ..protocol import ImpactMessage, Proposal

if TYPE_CHECKING:
    from ..server.runtime import TeamRuntime


@dataclass
class ImpactoEfectos:
    """Efectos calculados de un Save (capa 19).

    `mensajes_directos` y `mensajes_transitivos` son tuples
    `(dueño, ImpactMessage)` que el inbound entrega con `_enviar_a`.
    """

    mensajes_directos: list[tuple[str, ImpactMessage]] = field(default_factory=list)
    mensajes_transitivos: list[tuple[str, ImpactMessage]] = field(default_factory=list)


@dataclass
class PropagarRenameEfectos:
    """Efectos calculados al detectar un rename premium.

    `updates_directos`: archivos que se actualizaron en el workspace (sin
    dueño o propios del autor); el inbound difunde el UpdateMessage.
    `propuestas`: tuples (dueño, Proposal) para enviar al dueño ajeno;
    la propuesta YA quedó registrada en `rt.proposals` y persistida.
    """

    updates_directos: list[tuple[str, str]] = field(default_factory=list)  # (path, content)
    propuestas: list[tuple[str, Proposal]] = field(default_factory=list)


async def calcular_impacto_save(
    rt: "TeamRuntime",
    teams: TeamStorePort,
    path: str,
    viejo: str,
    nuevo: str,
    autor_id: str,
    autor_nombre: str,
    *,
    rename: Rename | None = None,
) -> ImpactoEfectos:
    """Capa 6/24: avisa al dueño de cada archivo afectado por el cambio.

    Capa 26 (free): si `rename` viene seteado y el plan no aplica el codemod,
    el "por qué" del símbolo renombrado se reemplaza por el texto accionable.
    Premium (impacto transitivo) agrega una segunda tanda por interfaz
    contaminada.

    Devuelve `ImpactoEfectos`; el caller emite los mensajes vía `enviar_a`.
    """
    efectos = ImpactoEfectos()
    snap = rt.workspace.snapshot()
    plan = await teams.plan(rt.team_id)
    cap_langs = limites(plan)["max_langs"]

    def _analizar() -> tuple[dict, dict, str]:
        ses = rt.lsp_sesion(lenguaje_de(path), cap_langs)
        af = analizar_impacto(snap, path, viejo, nuevo, ses)
        if not af:
            return {}, {}, ""
        return (
            af,
            analizar_motivos(path, viejo, nuevo, ses),
            tiers.analizador_efectivo(path, ses),
        )

    afectados, razones, analiz_directo = await asyncio.to_thread(_analizar)
    if not afectados:
        return efectos

    # Capa 26 (free): rename detectado pero plan no lo aplica → "por qué"
    # accionable.
    if rename is not None and rename.clase in razones:
        razones = {**razones, rename.clase: texto_sugerencia(rename)}

    por_archivo: dict[str, list[str]] = {}
    for simbolo, archivos in afectados.items():
        for af in archivos:
            por_archivo.setdefault(af, []).append(simbolo)

    for af, simbolos in por_archivo.items():
        dueño = rt.ownership.owner(af)
        if dueño is None:
            continue
        syms = sorted(simbolos)
        efectos.mensajes_directos.append((
            dueño,
            ImpactMessage(
                source_path=path,
                author_name=autor_nombre,
                affected_path=af,
                symbols=syms,
                motivos=[razones.get(s, "") for s in syms],
                severidades=[severidad_de(razones.get(s, "")) for s in syms],
                analizador=analiz_directo,
            ),
        ))

    # Premium: cadena transitiva. Si el plan no la soporta, devolvemos solo
    # los directos.
    if limites(plan)["impacto"] != "transitivo":
        return efectos

    directos = set(por_archivo)
    analiz_trans = tiers.analizador_efectivo(path, None)

    def _trans():
        lang = lenguaje_de(path)
        tier = tiers.tier_para(path)
        if tier is None or lang is None:
            return {}, False
        cambiados = list(tiers.cambios(path, viejo, nuevo))
        if not cambiados:
            return {}, False
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
    sufijo = " · análisis truncado (cambio muy amplio)" if trunc else ""

    for af, items in out.items():
        if af in directos:
            continue
        dueño = rt.ownership.owner(af)
        if dueño is None:
            continue
        props = [d for d in items if not d["terminal"]]
        if not props:
            continue
        props.sort(key=lambda d: (d["cadena"][0], len(d["cadena"])))
        syms = [d["cadena"][0].rsplit(":", 1)[1] for d in props]
        efectos.mensajes_transitivos.append((
            dueño,
            ImpactMessage(
                source_path=path,
                author_name=autor_nombre,
                affected_path=af,
                symbols=syms,
                motivos=[d["motivo"] + sufijo for d in props],
                severidades=[severidad_de(d["motivo"]) for d in props],
                cadena=props[0]["cadena"],
                analizador=analiz_trans,
            ),
        ))

    return efectos


async def calcular_propagar_rename(
    rt: "TeamRuntime",
    teams: TeamStorePort,
    proposals_store: ProposalsStorePort | None,
    path: str,
    viejo: str,
    nuevo: str,
    ren: Rename,
    autor_id: str,
    autor_nombre: str,
) -> PropagarRenameEfectos:
    """Capa 26 (premium): propaga un rename a quienes usan la clase como
    propuesta tentativa (sin dueño / propio → update directo; ajeno →
    proposal). Las mutaciones del estado (workspace, proposals) y la
    persistencia se hacen ACÁ; el inbound solo difunde los efectos.
    """
    efectos = PropagarRenameEfectos()
    snap = rt.workspace.snapshot()
    plan = await teams.plan(rt.team_id)
    cap_langs = limites(plan)["max_langs"]

    def _afectados() -> dict[str, list[str]]:
        ses = rt.lsp_sesion(lenguaje_de(path), cap_langs)
        return analizar_impacto(snap, path, viejo, nuevo, ses)

    afectados = await asyncio.to_thread(_afectados)
    for af in afectados.get(ren.clase, []):
        if af == path:
            continue
        contenido = snap.get(af)
        if contenido is None:
            continue
        propuesto = aplicar_rename(contenido, ren.viejo, ren.nuevo)
        if propuesto == contenido:
            continue
        dueño = rt.ownership.owner(af)
        etiqueta = f"OruxBot · rename {ren.viejo}→{ren.nuevo}"
        if dueño is None or dueño == autor_id:
            rt.workspace.update(af, propuesto)
            rt._analizado[af] = propuesto
            efectos.updates_directos.append((af, propuesto))
        else:
            prop = rt.proposals.put(
                path=af,
                author_id=autor_id,
                author_name=etiqueta,
                content=propuesto,
            )
            if proposals_store is not None:
                await proposals_store.guardar(rt.team_id, prop)
            efectos.propuestas.append((dueño, prop))

    return efectos
