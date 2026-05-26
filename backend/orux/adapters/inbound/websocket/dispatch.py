"""Dispatch de mensajes de sesión de equipo.

Cada handler decodifica el mensaje del protocolo, arma el Command, llama al
use case correspondiente (`orux.application.use_cases`) y traduce el Result
en sends del WebSocket. La lógica de dominio + orquestación vive en los use
cases; este módulo es estrictamente un **inbound adapter** del transporte
WebSocket — solo conoce el protocolo y los broadcasts.

INVARIANTE: cuando `_aplicar` invoca este dispatch para un mensaje que muta
estado, corre bajo `rt._estado_lock` (los handlers NO re-toman el lock).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

from orux.analysis import tiers
from orux.analysis.rename import detectar_rename
from orux.application import (
    AdminAssignCommand,
    AdminAssignManyCommand,
    ClaimCommand,
    CloneCommand,
    CommitCommand,
    CreateInviteCommand,
    DeleteCommand,
    PresenceCommand,
    PushCommand,
    ResolveCommand,
    UpdateCommand,
    admin_assign_many_use_case,
    admin_assign_use_case,
    claim_use_case,
    clone_use_case,
    commit_use_case,
    create_invite_use_case,
    delete_use_case,
    presence_use_case,
    push_use_case,
    resolve_use_case,
    update_use_case,
)
from orux.plans import permite_rename
from orux.protocol import (
    AdminAssignManyMessage,
    AdminAssignMessage,
    ClaimMessage,
    CloneMessage,
    CommitMessage,
    CreateInviteMessage,
    DeleteMessage,
    GitRefreshMessage,
    GitResultMessage,
    InviteCreatedMessage,
    OwnershipMessage,
    PresenceMessage,
    PresenceState,
    ProposalMessage,
    PushMessage,
    ResolveMessage,
    SaveMessage,
    UpdateMessage,
    encode,
)
from .util import autor_git

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from .runtime import TeamRuntime
    from .sync import SyncServer

logger = logging.getLogger(__name__)


# `yo` es el `PresenceState` del cliente que envió el mensaje (el server lo
# resolvió en el handshake y lo pasa a cada handler). Tiparlo evita que un
# refactor inadvertido cambie su forma sin que el typechecker grite.
Handler = Callable[
    ["SyncServer", "TeamRuntime", "ServerConnection",
     PresenceState, str, object],
    Awaitable[None],
]


async def _h_update(server, rt, websocket, yo, team_id, message):
    res = await update_use_case(
        rt,
        server._ownership_store,
        server._proposals_store,
        UpdateCommand(
            path=message.path,
            content=message.content,
            autor_id=yo.client_id,
            autor_nombre=yo.name,
        ),
    )
    if res.rebotar_a_autor is not None:
        await websocket.send(
            encode(UpdateMessage(path=message.path, content=res.rebotar_a_autor))
        )
        return
    if res.propuesta_para_dueno is not None:
        dueño, prop = res.propuesta_para_dueno
        await server._enviar_a(rt, dueño, encode(ProposalMessage(proposal=prop)))
        return
    if res.broadcast_update is not None:
        path, content = res.broadcast_update
        await server._broadcast(
            rt, websocket, encode(UpdateMessage(path=path, content=content)),
        )
    if res.broadcast_ownership is not None:
        await server._broadcast_todos(
            rt, encode(OwnershipMessage(owners=res.broadcast_ownership)),
        )


async def _h_save(server, rt, websocket, yo, team_id, message):
    """Capa 19: el checkpoint del dev (Ctrl+S). NO guarda nada (el contenido
    ya está sincronizado); es el disparo del análisis.

    Save sigue siendo orquestado acá porque la rama de impacto/rename
    (`server._propagar_rename` / `server._notificar_impacto`) vive en
    `server/impacto.py` con sus broadcasts a los dueños. Mover esa lógica a
    application requiere también extraer el broadcast a dueños — queda para
    una iteración futura del hex (Fase F).
    """
    actual = rt.workspace.snapshot().get(message.path)
    if actual is None:
        return
    # BACKEND-AUDIT M-04: Save (checkpoint, dispara análisis) solo lo
    # acepta del dueño. Sin esto, cualquier miembro podía mandar Save sobre
    # un archivo ajeno: baseline=`_analizado.get(path,"")` falso → diff
    # sintético sobre TODO el archivo → notificaciones de impacto/rename
    # ruidosas a otros usuarios. Save NO modifica contenido (eso lo hace
    # Update/Resolve), pero sí dispara broadcasts: filtrar acá ahorra
    # ruido sin perder UX. Si el archivo no tiene dueño aún, dejamos pasar
    # (alguien tiene que disparar el primer análisis tras crearlo).
    dueño = rt.ownership.owner(message.path)
    if dueño is not None and dueño != yo.client_id:
        logger.info(
            "save-ignorado: %s no es dueño de %r en equipo %s (dueño=%s)",
            yo.client_id, message.path, team_id, dueño,
        )
        return
    base = rt._analizado.get(message.path, "")
    rt._analizado[message.path] = actual

    def _det(b=base, a=actual, p=message.path):
        t = tiers.tier_para(p)
        if t is None:
            return None
        sa = t.simbolos(b)
        sd = t.simbolos(a)
        if sa is None or sd is None:
            return None
        return detectar_rename(sa, sd)

    ren = await asyncio.to_thread(_det)
    plan = await server.teams.plan(rt.team_id)
    if ren is not None and permite_rename(plan):
        await server._propagar_rename(
            rt, message.path, base, actual, ren, yo.client_id, yo.name,
        )
    else:
        await server._notificar_impacto(
            rt, message.path, base, actual,
            yo.client_id, yo.name, rename=ren,
        )


async def _h_delete(server, rt, websocket, yo, team_id, message):
    res = await delete_use_case(
        rt,
        server._ownership_store,
        server._proposals_store,
        DeleteCommand(path=message.path, autor_id=yo.client_id),
    )
    if res.broadcast_delete is not None:
        logger.info(
            "delete: %s borró %r en equipo %s",
            yo.client_id, res.broadcast_delete, team_id,
        )
        await server._broadcast_todos(
            rt, encode(DeleteMessage(path=res.broadcast_delete)),
        )
    if res.broadcast_ownership is not None:
        await server._broadcast_todos(
            rt, encode(OwnershipMessage(owners=res.broadcast_ownership)),
        )


async def _h_claim(server, rt, websocket, yo, team_id, message):
    res = await claim_use_case(
        rt,
        server._ownership_store,
        ClaimCommand(path=message.path, autor_id=yo.client_id),
    )
    await server._broadcast_todos(
        rt, encode(OwnershipMessage(owners=res.broadcast_ownership)),
    )


async def _h_admin_assign(server, rt, websocket, yo, team_id, message):
    """Capa 12/15: la compuerta de admin del equipo se chequea acá (necesita
    logging contextual con el detalle de la operación). El use case asume
    que ya pasó."""
    if not await server._es_admin_o_logear(
        team_id, yo.client_id,
        f"admin_assign(path={message.path!r}, "
        f"username={message.username!r})",
    ):
        return
    res = await admin_assign_use_case(
        rt,
        server._ownership_store,
        server.teams,
        AdminAssignCommand(
            path=message.path,
            username=message.username,
            autor_id=yo.client_id,
        ),
    )
    if res.broadcast_ownership is not None:
        await server._broadcast_todos(
            rt, encode(OwnershipMessage(owners=res.broadcast_ownership)),
        )


async def _h_admin_assign_many(server, rt, websocket, yo, team_id, message):
    if not await server._es_admin_o_logear(
        team_id, yo.client_id,
        f"admin_assign_many(n={len(message.paths)}, "
        f"username={message.username!r})",
    ):
        return
    res = await admin_assign_many_use_case(
        rt,
        server._ownership_store,
        server.teams,
        AdminAssignManyCommand(
            paths=list(message.paths),
            username=message.username,
            autor_id=yo.client_id,
        ),
    )
    if res.broadcast_ownership is not None:
        await server._broadcast_todos(
            rt, encode(OwnershipMessage(owners=res.broadcast_ownership)),
        )


async def _h_create_invite(server, rt, websocket, yo, team_id, message):
    if not await server._es_admin_o_logear(
        team_id, yo.client_id, "create_invite",
    ):
        return
    res = await create_invite_use_case(
        rt, server.teams, CreateInviteCommand(autor_id=yo.client_id),
    )
    if res.code is not None:
        logger.info(
            "create_invite: team=%s admin=%s emitió code", team_id, yo.client_id,
        )
        await server._enviar_a(
            rt, yo.client_id, encode(InviteCreatedMessage(code=res.code)),
        )


async def _h_resolve(server, rt, websocket, yo, team_id, message):
    res = await resolve_use_case(
        rt,
        server._proposals_store,
        ResolveCommand(
            proposal_id=message.proposal_id,
            autor_id=yo.client_id,
            accept=message.accept,
        ),
    )
    if res.aplicado_update is not None:
        path, viejo, nuevo, prop_author_id = res.aplicado_update
        logger.info(
            "resolve: team=%s dueño=%s aceptó propuesta id=%r path=%r autor=%s",
            team_id, yo.client_id, message.proposal_id, path, prop_author_id,
        )
        await server._broadcast_todos(
            rt, encode(UpdateMessage(path=path, content=nuevo)),
        )
        await server._notificar_impacto(
            rt, path, viejo, nuevo, prop_author_id,
            res.nombre_autor_propuesta,
        )
    if res.devolver_a_autor is not None:
        author_id, path, content_actual = res.devolver_a_autor
        logger.info(
            "resolve: team=%s dueño=%s rechazó propuesta id=%r path=%r autor=%s",
            team_id, yo.client_id, message.proposal_id, path, author_id,
        )
        await server._enviar_a(
            rt, author_id,
            encode(UpdateMessage(path=path, content=content_actual)),
        )


async def _h_presence(server, rt, websocket, yo, team_id, message):
    res = await presence_use_case(
        rt,
        PresenceCommand(
            autor_id=yo.client_id, path=message.path, line=message.line,
        ),
    )
    if res.broadcast_presence is not None:
        client_id, name, color, path, line = res.broadcast_presence
        await server._broadcast(
            rt, websocket,
            encode(PresenceMessage(
                client_id=client_id, name=name, color=color,
                path=path, line=line,
            )),
        )


async def _h_git_refresh(server, rt, websocket, yo, team_id, message):
    await server._enviar_git_status(rt, websocket)


async def _h_commit(server, rt, websocket, yo, team_id, message):
    nombre, email = autor_git(yo.client_id)
    async with rt._git_lock:
        res = await commit_use_case(
            rt,
            CommitCommand(
                mensaje=message.message,
                autor_nombre=nombre,
                autor_email=email,
            ),
        )
    if not res.ok:
        # Correlación con los logs de git/binary.py: éstos tienen la salida
        # cruda de git pero no quién la pidió desde qué equipo. Loguear acá
        # un warning con team/cliente cierra ese gap. (Camino feliz no se
        # loguea: commit es alta-frecuencia y `ok=True` no aporta señal.)
        logger.warning(
            "commit falló: team=%s autor=%s detalle=%r",
            team_id, yo.client_id, res.detalle,
        )
    await server._enviar_a(
        rt, yo.client_id, encode(GitResultMessage(res.ok, res.detalle)),
    )
    if res.git_status_cambio:
        payload = await server._git_status_encoded(rt)
        if payload is not None:
            await server._broadcast_todos(rt, payload)


async def _h_clone(server, rt, websocket, yo, team_id, message):
    # BACKEND-AUDIT C-02: clone destructivo SOLO admin.
    # Reemplaza el workspace entero, resetea ownership y borra propuestas
    # pendientes del equipo: blast radius sistémico. Antes era abierto a
    # cualquier miembro y combinado con C-01 (paths locales permitidos)
    # daba cross-team data exfiltration. Misma compuerta que admin_assign
    # / invite. El use case ya cierra permitir_local=False; el gate de
    # admin acota además el daño "destructivo intencional".
    if not await server._es_admin_o_logear(
        team_id, yo.client_id,
        f"clone(url={message.url!r})",
    ):
        await server._enviar_a(
            rt, yo.client_id,
            encode(GitResultMessage(False, "solo el admin del equipo puede clonar")),
        )
        return
    logger.info(
        "clone (DESTRUCTIVO) pedido por %s en equipo %s",
        yo.client_id, team_id,
    )
    async with rt._git_lock:
        res = await clone_use_case(
            rt,
            CloneCommand(
                url=message.url,
                usuario=message.username,
                token=message.token,
                autor_id=yo.client_id,
            ),
        )
        if res.reiniciar_equipo:
            # Orden git→estado (nunca al revés) ⇒ sin deadlock.
            async with rt._estado_lock:
                await server._reiniciar_para_todos(rt)
    if not res.ok:
        # binary.py loguea git rc/stderr; acá agregamos quién pidió el clone
        # y a qué equipo afectó (DESTRUCTIVO ⇒ una falla amerita trazabilidad
        # incluso si el cliente recibe el detalle humano-readable).
        logger.warning(
            "clone falló: team=%s autor=%s detalle=%r",
            team_id, yo.client_id, res.detalle,
        )
    await server._enviar_a(
        rt, yo.client_id, encode(GitResultMessage(res.ok, res.detalle)),
    )


async def _h_push(server, rt, websocket, yo, team_id, message):
    async with rt._git_lock:
        res = await push_use_case(
            rt,
            PushCommand(
                url=message.url,
                usuario=message.username,
                token=message.token,
                rama=message.rama,
                autor_id=yo.client_id,
            ),
        )
    if not res.ok:
        # binary.py loguea rc/destino/out de git; acá enriquecemos con
        # team/cliente/rama para correlación (sin secretos: usuario/token
        # nunca se loguean — `binary.py:_git_cred` los scrubea).
        logger.warning(
            "push falló: team=%s autor=%s rama=%r detalle=%r",
            team_id, yo.client_id, message.rama, res.detalle,
        )
    await server._enviar_a(
        rt, yo.client_id,
        encode(GitResultMessage(res.ok, res.detalle, res.pr_url)),
    )
    if res.git_status_cambio:
        payload = await server._git_status_encoded(rt)
        if payload is not None:
            await server._broadcast_todos(rt, payload)


HANDLERS: dict[type, Handler] = {
    UpdateMessage: _h_update,
    SaveMessage: _h_save,
    DeleteMessage: _h_delete,
    ClaimMessage: _h_claim,
    AdminAssignMessage: _h_admin_assign,
    AdminAssignManyMessage: _h_admin_assign_many,
    CreateInviteMessage: _h_create_invite,
    ResolveMessage: _h_resolve,
    PresenceMessage: _h_presence,
    GitRefreshMessage: _h_git_refresh,
    CommitMessage: _h_commit,
    CloneMessage: _h_clone,
    PushMessage: _h_push,
}


async def dispatch(
    server: "SyncServer",
    rt: "TeamRuntime",
    websocket: "ServerConnection",
    yo: PresenceState,
    team_id: str,
    message,
) -> None:
    """Despacha UN mensaje ya decodificado de la sesión de equipo.

    Si el tipo no está en la tabla (Init/Welcome/Leave del cliente,
    mensajes de lobby) se ignora silencioso.
    """
    handler = HANDLERS.get(type(message))
    if handler is None:
        return
    await handler(server, rt, websocket, yo, team_id, message)
