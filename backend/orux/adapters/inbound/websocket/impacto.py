"""Inbound translator del save (capa 19/24/26): use case → sends del WS.

La orquestación vive en `orux.application.impacto`; este módulo solo:
1. Llama al use case (que calcula efectos puros: mensajes y propuestas).
2. Traduce los efectos a `server._enviar_a` / `server._broadcast_todos`.

Se mantiene como módulo dentro de `server/` porque traduce a primitivas
específicas del transporte WebSocket. En Fase F se moverá a
`adapters/inbound/websocket/` junto al resto del transporte.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from orux.application.impacto import (
    calcular_impacto_save,
    calcular_propagar_rename,
)
from orux.analysis.rename import Rename
from orux.protocol import ProposalMessage, UpdateMessage, encode

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
    """Capa 6/24: avisa al dueño de cada archivo afectado por este cambio.

    Delega el cálculo a `application/impacto.calcular_impacto_save` y entrega
    los `ImpactMessage` resultantes al dueño correspondiente.
    """
    efectos = await calcular_impacto_save(
        rt,
        server.teams,
        path, viejo, nuevo, autor_id, autor_nombre,
        rename=rename,
    )
    for dueño, msg in efectos.mensajes_directos:
        await server._enviar_a(rt, dueño, encode(msg))
    for dueño, msg in efectos.mensajes_transitivos:
        await server._enviar_a(rt, dueño, encode(msg))


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
    usa la clase. Delega al use case y traduce los efectos a broadcasts/
    sends del WS. Las mutaciones del estado del runtime (workspace,
    proposals) las hace el use case.
    """
    efectos = await calcular_propagar_rename(
        rt,
        server.teams,
        server._proposals_store,
        path, viejo, nuevo, ren, autor_id, autor_nombre,
    )
    for af, propuesto in efectos.updates_directos:
        await server._broadcast_todos(
            rt, encode(UpdateMessage(path=af, content=propuesto)),
        )
    for dueño, prop in efectos.propuestas:
        await server._enviar_a(rt, dueño, encode(ProposalMessage(proposal=prop)))
