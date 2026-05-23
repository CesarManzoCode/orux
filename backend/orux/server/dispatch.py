"""Dispatch de mensajes de sesión de equipo.

Cada tipo de mensaje del protocolo (Update, Save, Delete, Claim,
AdminAssign, etc.) tiene su handler dedicado. La tabla `HANDLERS` mapea
clase de mensaje -> handler; `dispatch()` busca y ejecuta el handler
correspondiente.

Extraído de `sync.py` (modularización 2026-05-23): el `_aplicar` original
era un if/elif gigante de ~410 líneas con todas las reglas. Separarlo:
- baja `sync.py` por debajo de las 1100 líneas (manejable por humano);
- pone cada regla en su propia función testeable;
- permite agregar un mensaje nuevo sumando un handler y una entrada en
  la tabla, sin tocar el orquestador.

Los handlers son funciones libres que reciben `server` por parámetro
(igual que `impacto.py`) para usar broadcasts y persistencia ya
cableados. NO se usa mixin para mantener clara la firma de `SyncServer`.

INVARIANTE: cuando `_aplicar` lo invoca para un mensaje que muta estado,
corre bajo `rt._estado_lock` (los handlers NO re-toman el lock).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING, Awaitable, Callable

from ..analysis import tiers
from ..analysis.rename import detectar_rename
from ..plans import permite_rename
from ..protocol import (
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
    ProposalMessage,
    PushMessage,
    ResolveMessage,
    SaveMessage,
    UpdateMessage,
    encode,
)
from ..identity import normalizar
from ..state import lineas_tocadas, path_seguro
from ..teams import TeamError
from .util import autor_git

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from .runtime import TeamRuntime
    from .sync import SyncServer

logger = logging.getLogger(__name__)


# Cada handler tiene esta firma. Devuelve None; los efectos van a través
# de `server.*` (broadcasts, persistencia) o a la conexión directa.
Handler = Callable[
    ["SyncServer", "TeamRuntime", "ServerConnection", object, str, object],
    Awaitable[None],
]


async def _h_update(server, rt, websocket, yo, team_id, message):
    dueño = rt.ownership.owner(message.path)
    if dueño is not None and dueño != yo.client_id:
        # Archivo con dueño y no sos vos: edición tentativa. No se aplica
        # ni difunde — se guarda como propuesta y se le avisa al dueño.
        # "Editar primero, negociar después."
        prop = rt.proposals.put(
            path=message.path,
            author_id=yo.client_id,
            author_name=yo.name,
            content=message.content,
        )
        await server._persistir_prop(rt, prop)
        await server._enviar_a(
            rt, dueño, encode(ProposalMessage(proposal=prop))
        )
        return
    # Sin dueño, o sos el dueño: se aplica directo.
    # Capa 5 (colisiones por línea): si NO tiene dueño y pisás una línea
    # ocupada por otro presente, se rechaza el update entero. El dueño
    # tiene preferencia.
    viejo = rt.workspace.snapshot().get(message.path, "")
    if dueño is None:
        tocadas = lineas_tocadas(viejo, message.content)
        ocupadas = rt.roster.lineas_ocupadas(
            message.path, excepto=yo.client_id
        )
        if tocadas & ocupadas:
            await websocket.send(
                encode(UpdateMessage(path=message.path, content=viejo))
            )
            return
    # Primera vez que se ve el path = lo está creando: quien crea un
    # archivo es su dueño, sin botón.
    es_nuevo = not rt.workspace.exists(message.path)
    # Capa 19: el impacto NO corre por tecla. Acá solo se siembra el
    # baseline del checkpoint la 1ª vez que se toca el path (contenido
    # PREVIO a editar); el análisis espera al `save` (Ctrl+S). El
    # contenido sí sigue viajando en vivo (abajo).
    rt._analizado.setdefault(message.path, viejo)
    rt.workspace.update(message.path, message.content)
    await server._broadcast(
        rt,
        websocket,
        encode(UpdateMessage(path=message.path, content=message.content)),
    )
    if es_nuevo and dueño is None:
        rt.ownership.claim(message.path, yo.client_id)
        await server._persistir_own(rt)
        await server._broadcast_todos(
            rt,
            encode(OwnershipMessage(owners=rt.ownership.snapshot())),
        )


async def _h_save(server, rt, websocket, yo, team_id, message):
    """Capa 19: el checkpoint del dev (Ctrl+S). NO guarda nada (el
    contenido ya está sincronizado); es el disparo del análisis. Diff
    baseline->ahora; el autor del aviso es quien marca el checkpoint.
    El baseline avanza siempre (haya o no impacto): el próximo Ctrl+S
    mide desde acá. No se retransmite (es un disparador, no estado a
    converger)."""
    actual = rt.workspace.snapshot().get(message.path)
    if actual is None:
        return
    base = rt._analizado.get(message.path, "")
    rt._analizado[message.path] = actual

    # Capa 26: ¿este checkpoint ES un rename de miembro confiable? La
    # detección usa los Simbolo del tier (parseo) -> a un hilo (no
    # bloquear el loop).
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
        # Premium: se propaga como propuesta capa 4. El aviso genérico
        # de ese símbolo lo reemplaza la propuesta accionable (no se
        # manda además).
        await server._propagar_rename(
            rt, message.path, base, actual,
            ren, yo.client_id, yo.name,
        )
    else:
        # Free (o sin rename): impacto normal; si hubo rename confiable,
        # el "por qué" se vuelve el texto accionable (premium lo aplica
        # por vos).
        await server._notificar_impacto(
            rt, message.path, base, actual,
            yo.client_id, yo.name, rename=ren,
        )


async def _h_delete(server, rt, websocket, yo, team_id, message):
    """Sólo borra el dueño, o cualquiera si no tiene dueño."""
    dueño = rt.ownership.owner(message.path)
    if dueño is not None and dueño != yo.client_id:
        return
    if not rt.workspace.delete(message.path):
        return
    logger.info(
        "delete: %s borró %r en equipo %s",
        yo.client_id, message.path, team_id,
    )
    rt.proposals.drop_path(message.path)
    await server._borrar_props_path(rt, message.path)
    # Capa 19: si se recrea, re-basea desde cero.
    rt._analizado.pop(message.path, None)
    cambio_owner = rt.ownership.liberar(message.path)
    if cambio_owner:
        await server._persistir_own(rt)
    await server._broadcast_todos(
        rt, encode(DeleteMessage(path=message.path))
    )
    if cambio_owner:
        await server._broadcast_todos(
            rt,
            encode(OwnershipMessage(owners=rt.ownership.snapshot())),
        )


async def _h_claim(server, rt, websocket, yo, team_id, message):
    rt.ownership.claim(message.path, yo.client_id)
    await server._persistir_own(rt)
    await server._broadcast_todos(
        rt,
        encode(OwnershipMessage(owners=rt.ownership.snapshot())),
    )


async def _h_admin_assign(server, rt, websocket, yo, team_id, message):
    """Capa 12/15: el admin DEL EQUIPO reparte ownership. Sólo el admin
    del equipo; un no-admin se ignora (con audit log). `username` vacío
    = revocar. El destino debe ser miembro del equipo (asignar a alguien
    de afuera rompería el aislamiento)."""
    if not await server._es_admin_o_logear(
        team_id, yo.client_id,
        f"admin_assign(path={message.path!r}, "
        f"username={message.username!r})",
    ):
        return
    aplicado = False
    if message.username:
        destino = normalizar(message.username)
        if await server.teams.es_miembro(team_id, destino):
            rt.ownership.asignar(message.path, destino)
            aplicado = True
    else:
        aplicado = rt.ownership.liberar(message.path)
    if aplicado:
        await server._persistir_own(rt)
        await server._broadcast_todos(
            rt,
            encode(OwnershipMessage(owners=rt.ownership.snapshot())),
        )


async def _h_admin_assign_many(server, rt, websocket, yo, team_id, message):
    """Capa 13/15: reparto masivo, un solo broadcast. Misma compuerta
    (admin del equipo) y reglas que admin_assign."""
    if not await server._es_admin_o_logear(
        team_id, yo.client_id,
        f"admin_assign_many(n={len(message.paths)}, "
        f"username={message.username!r})",
    ):
        return
    destino = normalizar(message.username) if message.username else ""
    valido = (
        not destino
        or await server.teams.es_miembro(team_id, destino)
    )
    aplicado = False
    if valido:
        for p in message.paths:
            # Robustez M1: filtrá path-a-path (no el reparto entero) — un
            # path inseguro en la lista no debe meter ownership fantasma
            # ni anular el resto.
            if not path_seguro(p):
                continue
            if destino:
                rt.ownership.asignar(p, destino)
                aplicado = True
            elif rt.ownership.liberar(p):
                aplicado = True
    if aplicado:
        await server._persistir_own(rt)
        await server._broadcast_todos(
            rt,
            encode(OwnershipMessage(owners=rt.ownership.snapshot())),
        )


async def _h_create_invite(server, rt, websocket, yo, team_id, message):
    """Capa 15: el admin del equipo genera un código para invitar. Sólo
    el admin; un no-admin se ignora pero queda en el audit log (un member
    sondeando "puedo invitar" es señal útil para diagnóstico)."""
    if not await server._es_admin_o_logear(
        team_id, yo.client_id, "create_invite",
    ):
        return
    try:
        code = await server.teams.crear_invitacion(team_id, yo.client_id)
        await server._enviar_a(
            rt, yo.client_id,
            encode(InviteCreatedMessage(code=code)),
        )
    except TeamError:
        pass  # carrera benigna (dejó de ser admin, etc.)


async def _h_resolve(server, rt, websocket, yo, team_id, message):
    prop = rt.proposals.get(message.proposal_id)
    # Sólo el dueño actual resuelve. Si ya no existe o no sos el dueño,
    # se ignora (carrera benigna).
    if prop is None or rt.ownership.owner(prop.path) != yo.client_id:
        return
    rt.proposals.pop(message.proposal_id)
    await server._borrar_prop(rt, message.proposal_id)
    if message.accept:
        viejo = rt.workspace.snapshot().get(prop.path, "")
        rt.workspace.update(prop.path, prop.content)
        await server._broadcast_todos(
            rt,
            encode(UpdateMessage(path=prop.path, content=prop.content)),
        )
        await server._notificar_impacto(
            rt, prop.path, viejo, prop.content,
            prop.author_id, prop.author_name,
        )
    else:
        await server._enviar_a(
            rt,
            prop.author_id,
            encode(
                UpdateMessage(
                    path=prop.path,
                    content=rt.workspace.snapshot().get(prop.path, ""),
                )
            ),
        )


async def _h_presence(server, rt, websocket, yo, team_id, message):
    estado = rt.roster.mover(yo.client_id, message.path, message.line)
    if estado is None:
        return
    await server._broadcast(
        rt,
        websocket,
        encode(
            PresenceMessage(
                client_id=estado.client_id,
                name=estado.name,
                color=estado.color,
                path=estado.path,
                line=estado.line,
            )
        ),
    )


async def _h_git_refresh(server, rt, websocket, yo, team_id, message):
    await server._enviar_git_status(rt, websocket)


async def _h_commit(server, rt, websocket, yo, team_id, message):
    if rt.git is None:
        await server._enviar_a(
            rt, yo.client_id,
            encode(GitResultMessage(False, "git no disponible")),
        )
        return
    msg = (message.message or "").strip()[:500]
    if not msg:
        await server._enviar_a(
            rt, yo.client_id,
            encode(GitResultMessage(
                False, "escribí un mensaje de commit")),
        )
        return
    nombre, email = autor_git(yo.client_id)
    async with rt._git_lock:
        ok, detalle = await asyncio.to_thread(
            rt.git.commitear, msg, nombre, email
        )
    await server._enviar_a(
        rt, yo.client_id,
        encode(GitResultMessage(ok, detalle)),
    )
    if ok:
        payload = await server._git_status_encoded(rt)
        if payload is not None:
            await server._broadcast_todos(rt, payload)


async def _h_clone(server, rt, websocket, yo, team_id, message):
    if rt.git is None:
        await server._enviar_a(
            rt, yo.client_id,
            encode(GitResultMessage(False, "git no disponible")),
        )
        return
    # Destructivo: reemplaza el workspace del equipo entero. En
    # producción tiene que quedar auditado quién y de dónde.
    logger.info(
        "clone (DESTRUCTIVO) pedido por %s en equipo %s",
        yo.client_id, team_id,
    )
    async with rt._git_lock:
        ok, detalle = await asyncio.to_thread(
            rt.git.clonar,
            message.url, message.username, message.token,
        )
        if ok:
            # El clone reemplaza TODO el workspace/ownership: tomá
            # también el lock de estado para que un Update concurrente
            # no aplique sobre el árbol viejo justo mientras se
            # reinicia. Orden git->estado (nunca al revés en ningún
            # handler) => sin deadlock.
            async with rt._estado_lock:
                await server._reiniciar_para_todos(rt)
    await server._enviar_a(
        rt, yo.client_id,
        encode(GitResultMessage(ok, detalle)),
    )


async def _h_push(server, rt, websocket, yo, team_id, message):
    if rt.git is None:
        await server._enviar_a(
            rt, yo.client_id,
            encode(GitResultMessage(False, "git no disponible")),
        )
        return
    # Capa 21b: la rama destino la ELIGE el usuario. Vacío = la rama de
    # publicación del equipo (default seguro: force-with-lease + PR;
    # orux es su único escritor). Cualquier otra (p.ej. main) = push
    # normal SIN forzar (capa 10: non-ff honesto, jamás pisa historia
    # compartida). orux decide force-o-no por el destino; el usuario
    # solo elige a dónde.
    rama_eq = f"orux/{rt.team_id}"
    destino = (message.rama or "").strip() or rama_eq
    async with rt._git_lock:
        if destino == rama_eq:
            ok, detalle, pr_url = await asyncio.to_thread(
                rt.git.push_a_rama,
                message.username, message.token,
                rama_eq, message.url or None,
            )
        else:
            ok, detalle = await asyncio.to_thread(
                rt.git.push,
                message.username, message.token,
                message.url or None, destino,
            )
            pr_url = ""
    await server._enviar_a(
        rt, yo.client_id,
        encode(GitResultMessage(ok, detalle, pr_url)),
    )
    if ok:
        payload = await server._git_status_encoded(rt)
        if payload is not None:
            await server._broadcast_todos(rt, payload)


# Tabla de despacho: agregar un mensaje nuevo es sumar UNA entrada acá +
# una función `_h_<x>`. El orden no importa; `dispatch` busca por tipo.
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
    yo,
    team_id: str,
    message,
) -> None:
    """Despacha UN mensaje ya decodificado de la sesión de equipo.

    Si el tipo no está en la tabla (Init/Welcome/Leave del cliente,
    mensajes de lobby que llegan a la sesión, etc.) se ignora silencioso:
    eran posibles ya antes y `_aplicar` original también caía a no-op.
    """
    handler = HANDLERS.get(type(message))
    if handler is None:
        return  # Init/Welcome/Leave/lobby: no aplica acá, ignorar.
    await handler(server, rt, websocket, yo, team_id, message)
