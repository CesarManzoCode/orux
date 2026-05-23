"""Ajuste de asientos de Stripe en background.

Capa 31: el plan premium se cobra POR USUARIO. La suscripción de Stripe
tiene una cantidad igual al número de miembros del equipo. Cuando entra
alguien nuevo a un equipo premium (`redimir` en el lobby), hay que subir
esa cantidad en Stripe.

La llamada vive acá —no en el contenedor `api`— porque el join ocurre en
el server WebSocket y `stripe_client` es stdlib pura, compartible. Se
extrajo de `sync.py` (modularización 2026-05-23) para aislar la
preocupación de billing del loop principal del server: cualquier cambio
en cómo se cobra entra acá sin tocar `sync.py`.

Best-effort: cualquier fallo se loguea y se traga — el cobro nunca debe
afectar la colaboración. Como la cantidad que se fija es ABSOLUTA
(= miembros actuales), el próximo ajuste corrige sola la inconsistencia.
"""

from __future__ import annotations

import asyncio
import logging
from functools import partial

from .. import stripe_client

logger = logging.getLogger(__name__)


def disparar_ajuste(
    coro,
    tareas_fondo: set[asyncio.Task],
) -> None:
    """Crea la tarea de fondo registrándola en `tareas_fondo` para que el
    GC no la elimine con "Task was destroyed but it is pending" si falla.

    El caller decide si crear la coroutina (la guardia por `stripe_secret`
    vive en el caller para evitar crear `coro` y luego no awaitarla, que
    dispararía `RuntimeWarning: coroutine was never awaited` en tests)."""
    tarea = asyncio.create_task(coro)
    tareas_fondo.add(tarea)
    tarea.add_done_callback(tareas_fondo.discard)


async def ajustar_asientos(
    *,
    team_id: str,
    stripe_secret: str,
    teams,
    asientos_locks: dict[str, asyncio.Lock],
) -> None:
    """Deja la suscripción de Stripe del equipo en tantos asientos como
    miembros tenga (cobro por usuario).

    Solo actúa si el equipo es premium Y tiene una suscripción real de
    Stripe; un equipo free, o uno premium puesto a mano por el operador
    (sin suscripción), no se tocan. El lock por equipo serializa dos
    altas casi simultáneas: la segunda tarea relee el conteo ya
    actualizado, así el POST a Stripe usa el número correcto.

    Best-effort: cualquier excepción se loguea y se traga.
    """
    try:
        lock = asientos_locks.get(team_id)
        if lock is None:
            lock = asientos_locks[team_id] = asyncio.Lock()
        async with lock:
            if await teams.plan(team_id) != "premium":
                return
            sub = await teams.suscripcion(team_id)
            if not sub:
                return
            n = await teams.contar_miembros(team_id)
            loop = asyncio.get_running_loop()
            # `functools.partial` para pasar `team_id` como kwarg de
            # contexto (solo afecta logs): `run_in_executor` no acepta
            # kwargs directos.
            await loop.run_in_executor(
                None,
                partial(
                    stripe_client.actualizar_cantidad,
                    stripe_secret, sub, n, team_id=team_id,
                ),
            )
    except Exception:  # noqa: BLE001 - best-effort, nunca propaga
        logger.exception(
            "ajuste de asientos falló para el equipo %s", team_id
        )
