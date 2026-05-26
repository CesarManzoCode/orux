"""Compuerta de equipo (capa 15) — el lobby del server WS.

Después de autenticarse, el usuario llega acá sin equipo asignado. El
lobby le manda la lista de sus equipos y espera que cree uno, redima un
código de invitación, o seleccione uno propio. Devuelve el `team_id`
elegido (o `None` si la conexión se cierra sin elegir).

Extraído de `sync.py` (modularización 2026-05-23). La función es libre
y recibe `server` como primer argumento (igual que `dispatch.py`,
`impacto.py`, `auth_handshake.py`).
"""

from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from orux.protocol import (
    CreateTeamMessage,
    LobbyMessage,
    RedeemInviteMessage,
    SelectTeamMessage,
    decode,
    encode,
)
from orux.teams import TeamError
from .util import ip_cliente

if TYPE_CHECKING:
    from websockets.asyncio.server import ServerConnection

    from .sync import SyncServer

logger = logging.getLogger(__name__)


async def lobby(
    server: "SyncServer",
    websocket: "ServerConnection",
    usuario: str,
) -> str | None:
    """Compuerta de equipo (capa 15). Autenticado pero sin equipo: NO ve
    nada. Le mandamos sus equipos y esperamos que cree uno, redima un
    código, o elija uno suyo. Devuelve el team_id elegido, o None si la
    conexión se cierra sin elegir.

    Throttle (BACKEND-AUDIT-0218): mismo mecanismo que `autenticar`. Un
    cliente que manda basura infinita en el lobby no debe consumir
    CPU/IO del server sin coste. MAX_FALLOS de mensajes inválidos cierra
    el socket.
    """
    async def _mandar_lobby(error: str = "") -> None:
        equipos = await server.teams.equipos_de(usuario)
        await websocket.send(
            encode(LobbyMessage(teams=equipos, error=error))
        )

    fallos = 0
    MAX_FALLOS = 16  # más holgado que auth (lobby tiene UX legítima de retry)

    async def _fallo(reason: str) -> bool:
        nonlocal fallos
        fallos += 1
        await _mandar_lobby(reason)
        if fallos >= MAX_FALLOS:
            logger.warning(
                "lobby: %d fallos del usuario %s, se corta", fallos, usuario
            )
            return True
        await asyncio.sleep(min(2.0, 0.2 * fallos))
        return False

    await _mandar_lobby()
    async for raw in websocket:
        try:
            msg = decode(raw)
        except ValueError:
            if await _fallo("mensaje inválido"):
                return None
            continue
        if isinstance(msg, CreateTeamMessage):
            # BACKEND-AUDIT A-01: throttle por IP y por usuario. Sin esto,
            # un cliente autenticado podía reconectar y crear N equipos sin
            # tope, llenando Postgres + /data/ws/<id>/. El backoff por-conexión
            # del lobby NO frena un éxito (un create_team OK sale de inmediato).
            ip = ip_cliente(websocket)
            if not server._throttle_create_team(ip, usuario):
                logger.warning(
                    "create_team: tope alcanzado (ip=%s usuario=%s)",
                    ip, usuario,
                )
                if await _fallo(
                    "creaste demasiados equipos en poco tiempo, esperá una hora"
                ):
                    return None
                continue
            try:
                eq = await server.teams.crear_equipo(msg.nombre, usuario)
                return eq["id"]
            except TeamError as e:
                if await _fallo(str(e)):
                    return None
        elif isinstance(msg, RedeemInviteMessage):
            try:
                eq = await server.teams.redimir(msg.code, usuario)
            except TeamError as e:
                # Capa 22: tope de plan (equipo lleno). Mensaje de
                # upgrade, NO "código inválido": el código sigue vivo.
                if await _fallo(str(e)):
                    return None
                continue
            if eq is not None:
                # Capa 31: entró un miembro nuevo. Si el equipo es
                # premium, ajustá los asientos de su suscripción de
                # Stripe (en segundo plano: no bloquea el lobby).
                server._ajustar_asientos_bg(eq["id"])
                return eq["id"]
            if await _fallo("código inválido o ya usado"):
                return None
        elif isinstance(msg, SelectTeamMessage):
            if await server.teams.es_miembro(msg.team_id, usuario):
                return msg.team_id
            if await _fallo("no sos miembro de ese equipo"):
                return None
        else:
            # Cualquier mensaje de app antes de tener equipo: recordale
            # que primero hay que elegir/crear uno (la app sigue cerrada).
            if await _fallo("hay que crear/elegir equipo primero"):
                return None
    return None
