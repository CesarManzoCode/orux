"""Barrido de runtimes y sesiones LSP ociosas.

Lo que evita: que `_runtimes` y las sesiones LSP crezcan sin techo.
Cada `TeamRuntime` puede traer cientos de MB de RAM por sus sesiones LSP
(pyright tiene índices de tipos en memoria); un equipo que se conectó
una vez y se fue NO debería retener esa RAM. Las dos tareas viven en el
fondo del server WS.

- **LSP**: barrido fino, cada sesión LSP que estuvo ociosa > TTL se cierra
  (el runtime sigue). Reiniciarla degrada a tree-sitter mientras reindexa.
- **Runtime**: barrido grueso, un runtime SIN conexiones desde hace > TTL
  se evicta entero (más invalida pero recupera más RAM). Las propuestas
  pendientes deben estar persistidas en Postgres antes de evictar; si no,
  preferimos retener (en dev sin DB).

Extraído de `sync.py` (modularización 2026-05-23): la lógica de eviction
no toca el flujo principal del server (handshake/lobby/sesión), así que
aislarla deja `sync.py` más fino y permite cambiar la política sin riesgo
de regresión en el dispatch de mensajes.
"""

from __future__ import annotations

import asyncio
import logging
import time

from .runtime import TeamRuntime

logger = logging.getLogger(__name__)


async def barrer_lsp_ociosas(
    runtimes: dict[str, TeamRuntime], ttl: float,
) -> None:
    """Tarea de fondo: cada minuto evicta sesiones LSP sin uso hace más
    de `ttl`. La RAM escala con equipos ACTIVOS, no totales. El
    re-arranque al volver degrada a tree-sitter mientras reindexa (net
    de capa 17): nunca se rompe."""
    while True:
        await asyncio.sleep(60)
        for tid, rt in list(runtimes.items()):
            ev = rt.evictar_lsp_ociosas(ttl)
            if ev:
                logger.info(
                    "LSP evictadas por ociosas (%ds) equipo %s: %s",
                    int(ttl), tid, ", ".join(ev),
                )


def runtime_evictable(
    rt: TeamRuntime,
    ttl: float,
    ahora: float,
    *,
    tiene_proposals_store: bool,
) -> bool:
    """¿Es seguro evictar este runtime ahora?

    Reglas (todas deben cumplirse):
    - Sin conexiones vivas (`rt.clients` vacío).
    - Ocioso desde hace > `ttl` (`_vacio_desde` no None y suficientemente
      viejo).
    - Sus propuestas tentativas están persistidas O no tiene propuestas
      pendientes. Sin persistencia, evictar significa PERDER propuestas;
      en modo dev preferimos retener RAM.
    - Sin trabajo en vuelo: si el git_lock o el estado_lock están
      tomados, alguien está procesando un mensaje justo ahora — no
      tocar. (Race contra `_runtime_para` la cubre el lock por team_id
      del caller.)
    """
    if rt.clients:
        return False
    if rt._vacio_desde is None:
        return False
    if ahora - rt._vacio_desde < ttl:
        return False
    if rt.proposals._pendientes and not tiene_proposals_store:
        return False
    if rt._git_lock.locked() or rt._estado_lock.locked():
        return False
    return True


async def evictar_runtime(
    team_id: str,
    *,
    runtimes: dict[str, TeamRuntime],
    rt_locks: dict[str, asyncio.Lock],
    asientos_locks: dict[str, asyncio.Lock],
) -> bool:
    """Saca el runtime del registro y libera sus sesiones LSP.

    Re-chequea bajo el lock por team_id que sigue siendo evictable
    (otra conexión pudo entrar entre el barrido y acá). Devuelve True
    si efectivamente lo evictó."""
    lock = rt_locks.get(team_id)
    if lock is None:
        return False
    async with lock:
        rt = runtimes.get(team_id)
        if rt is None:
            return False
        # Re-check defensivo: si una conexión entró justo entre el
        # barrido y este lock, abortar.
        if rt.clients or rt._vacio_desde is None:
            return False
        rt.reciclar_lsp()  # cierra subprocesos LSP (cientos de MB)
        del runtimes[team_id]
    # Limpieza fuera del lock (otras conexiones del MISMO equipo van a
    # crear locks nuevos al volver, vía `setdefault`).
    rt_locks.pop(team_id, None)
    asientos_locks.pop(team_id, None)
    return True


async def barrer_runtimes_ociosos(
    ttl: float,
    *,
    runtimes: dict[str, TeamRuntime],
    rt_locks: dict[str, asyncio.Lock],
    asientos_locks: dict[str, asyncio.Lock],
    tiene_proposals_store: bool,
) -> None:
    """Tarea de fondo: cada minuto evicta runtimes sin conexiones desde
    hace > `ttl`. Sin esto, `runtimes` crece sin techo (cada equipo que
    se conectó alguna vez retiene RAM hasta que el proceso muera).

    Al volver alguien al equipo, el caller reconstruye el runtime y
    rehidrata ownership + propuestas desde Postgres (capa 15 y
    persistencia de propuestas). El usuario no ve diferencia más allá
    de un instante de "primer mensaje" un poco más caro (igual que la
    primera conexión al deploy).
    """
    while True:
        await asyncio.sleep(60)
        ahora = time.monotonic()
        candidatos = [
            tid for tid, rt in list(runtimes.items())
            if runtime_evictable(
                rt, ttl, ahora,
                tiene_proposals_store=tiene_proposals_store,
            )
        ]
        for tid in candidatos:
            if await evictar_runtime(
                tid,
                runtimes=runtimes,
                rt_locks=rt_locks,
                asientos_locks=asientos_locks,
            ):
                logger.info(
                    "runtime evictado por ocioso (%ds) equipo %s",
                    int(ttl), tid,
                )
