"""Capa de servicio de la API de operador — pura, sin HTTP.

Funciones async sobre los stores (duck-typed: cualquier objeto con la
superficie async correcta — `MemTeamStore` en tests, `PgTeamStore` en
deploy). Acá vive la lógica y las reglas; `app.py` solo traduce HTTP<->esto.
Así se prueba el 100% del comportamiento en sandbox sin Postgres ni HTTP.

Convención de errores (la cáscara HTTP las mapea):
- `ValueError`  -> 400 (entrada inválida, p.ej. plan inexistente)
- retorno `None` -> 404 (no existe)
- retorno con datos -> 200
"""

from __future__ import annotations

from ..plans import PLANES


async def listar_usuarios(users) -> list[str]:
    """Todos los usuarios de la plataforma (operador)."""
    return await users.usuarios()


async def listar_teams(teams) -> list[dict]:
    """Todos los equipos con plan y #miembros."""
    return await teams.todos()


async def detalle_team(teams, team_id: str) -> dict | None:
    """Equipo + sus miembros, o None si no existe."""
    e = await teams.equipo(team_id)
    if e is None:
        return None
    return {**e, "miembros": await teams.miembros(team_id)}


async def cambiar_plan(teams, team_id: str, plan: str) -> dict | None:
    """Setea el plan del equipo (la acción de cobro manual: alguien pagó ->
    premium). Valida el plan contra PLANES (no se inventan planes). None si
    el equipo no existe; devuelve el detalle actualizado si OK.
    """
    if plan not in PLANES:
        raise ValueError(
            f"plan inválido: {plan!r} (válidos: {sorted(PLANES)})"
        )
    if await teams.equipo(team_id) is None:
        return None
    await teams.set_plan(team_id, plan)
    return await detalle_team(teams, team_id)
