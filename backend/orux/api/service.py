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

from ..identity.store import normalizar
from ..identity.tokens import crear_token, usuario_de_token
from ..plans import PLANES


# --- Auth del operador por CUENTA (no por token estático) ----------------
#
# Antes: un único `ORUX_ADMIN_TOKEN` que el cliente MANDABA en cada
# request (un secreto compartido viajando por la red, sin identidad, sin
# rotación por cuenta). Ahora: el operador es una CUENTA ya registrada
# (env `ORUX_ADMIN_USER`); entra con su usuario+contraseña normales
# (verificadas contra el store con PBKDF2, igual que el login del IDE,
# capa 7) y recibe un token de SESIÓN firmado con HMAC. El secreto de
# firma (`ORUX_ADMIN_TOKEN`, reusado y resignificado) NUNCA sale del
# server: solo firma/verifica; el cliente jamás lo ve ni lo transmite.
#
# Reusa las primitivas ya endurecidas de la capa 7 (`passwords` PBKDF2 +
# `tokens` HMAC): cero criptografía nueva. Deuda consciente heredada de
# capa 7 (anotada una vez): el token de sesión no expira todavía; rotar
# `ORUX_ADMIN_TOKEN` invalida todos. Suficiente para una consola de un
# solo operador; expiración = pieza chica futura (el payload ya es dict).


async def login_operador(
    users, admin_user: str, secret: str, username: str, password: str
) -> str | None:
    """Login del operador. Devuelve un token de sesión firmado, o None si:
    no está configurado (sin admin_user/secret), el usuario no ES el
    operador designado, o la contraseña no verifica (PBKDF2 vía el store —
    `await` como el WS de capa 7). Falla SIEMPRE hacia "no autorizado":
    no dice si falló el usuario o la contraseña (no filtra qué cuenta es
    el operador)."""
    if not admin_user or not secret:
        return None
    if normalizar(username) != normalizar(admin_user):
        return None
    if not await users.verificar(username, password):
        return None
    return crear_token(normalizar(username), secret)


def operador_de_token(
    token: str, admin_user: str, secret: str
) -> str | None:
    """Valida el Bearer: token firmado por ESTE server (HMAC) Y cuyo usuario
    ES el operador designado. None = no autorizado. Puro/sync (verificar
    una firma no toca I/O): el gate HTTP lo usa tal cual."""
    if not admin_user or not secret:
        return None
    u = usuario_de_token(token, secret)
    if u is None or normalizar(u) != normalizar(admin_user):
        return None
    return u


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
