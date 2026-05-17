"""Cáscara ASGI (starlette) de la API de operador — capa 23.

Solo traduce HTTP <-> `service.py` (donde vive la lógica, ya testeada en
sandbox). starlette se importa acá a propósito: este módulo solo lo carga
uvicorn en el deploy; el sandbox (sin internet/sin starlette) NUNCA lo
importa — los tests prueban `service.py`, no esto. Mismo patrón que
pyright/asyncpg/tree-sitter: la cáscara de I/O se verifica en el VPS.

Montado en `/api/v1` (lo pidió el usuario; versionar el path ahora es
gratis). NO es API pública: token de OPERADOR de plataforma (vos), rol
distinto del admin-de-equipo de capa 12/15.

Seguridad (una vez): el operador es una CUENTA ya registrada
(`LAIDEA_ADMIN_USER`) que entra con su usuario+contraseña normales y
recibe un token de SESIÓN firmado (HMAC; secreto `LAIDEA_ADMIN_TOKEN` que
NUNCA sale del server — solo firma/verifica). Antes el cliente mandaba el
secreto crudo en cada request; ahora no transmite ningún secreto. Sin
`LAIDEA_ADMIN_USER` o sin `LAIDEA_ADMIN_TOKEN` la API queda CERRADA (503),
nunca abierta. La lógica (PBKDF2 + firmar/validar) vive en `service.py` y
se prueba 100% en sandbox; acá solo HTTP. Los stores viven en `app.state`
(deploy: Postgres en startup; tests: inyectados) — UN set de handlers.
"""

from __future__ import annotations

import contextlib
import os

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

from ..db.pool import Database
from ..db.stores import PgUserStore
from ..teams import PgTeamStore
from . import service

# Quién es el operador (una cuenta registrada) y el secreto de FIRMA de sus
# tokens de sesión (nunca se manda al cliente). Faltando cualquiera: 503.
_ADMIN_USER = os.environ.get("LAIDEA_ADMIN_USER", "")
_SECRET = os.environ.get("LAIDEA_ADMIN_TOKEN", "")


def _gate(req: Request) -> JSONResponse | None:
    """None = pasa. Sin configurar: cerrado (503). Token de sesión inválido
    o no es el operador: 401. La validación (firma HMAC + que el usuario
    SEA el operador) la hace `service.operador_de_token` (pura, testeada)."""
    if not _ADMIN_USER or not _SECRET:
        return JSONResponse(
            {"error": "API de operador no configurada (falta "
                      "LAIDEA_ADMIN_USER / LAIDEA_ADMIN_TOKEN)"},
            status_code=503,
        )
    cab = req.headers.get("authorization", "")
    pre = "Bearer "
    tok = cab[len(pre):] if cab.startswith(pre) else ""
    if service.operador_de_token(tok, _ADMIN_USER, _SECRET) is not None:
        return None
    return JSONResponse({"error": "no autorizado"}, status_code=401)


async def _login(req: Request) -> JSONResponse:
    """POST {username, password} -> {token}. La compuerta real: verifica
    credenciales (PBKDF2 vía el store) y que sea el operador; si OK emite
    un token de sesión firmado. 401 genérico si algo falla (no filtra qué
    cuenta es el operador). 503 si no está configurado."""
    if not _ADMIN_USER or not _SECRET:
        return JSONResponse(
            {"error": "API de operador no configurada"}, status_code=503
        )
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001 - body no-JSON
        return JSONResponse({"error": "body JSON inválido"},
                            status_code=400)
    token = await service.login_operador(
        req.app.state.users, _ADMIN_USER, _SECRET,
        str(body.get("username", "")), str(body.get("password", "")),
    )
    if token is None:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    return JSONResponse({"token": token})


async def _health(_req: Request) -> JSONResponse:
    return JSONResponse({"ok": True})


async def _usuarios(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    return JSONResponse(await service.listar_usuarios(req.app.state.users))


async def _teams(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    return JSONResponse(await service.listar_teams(req.app.state.teams))


async def _detalle(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    d = await service.detalle_team(req.app.state.teams,
                                   req.path_params["tid"])
    if d is None:
        return JSONResponse({"error": "equipo inexistente"},
                            status_code=404)
    return JSONResponse(d)


async def _plan(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001 - body no-JSON
        return JSONResponse({"error": "body JSON inválido"},
                            status_code=400)
    try:
        d = await service.cambiar_plan(
            req.app.state.teams, req.path_params["tid"],
            str(body.get("plan", "")),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if d is None:
        return JSONResponse({"error": "equipo inexistente"},
                            status_code=404)
    return JSONResponse(d)


_RUTAS = [
    Route("/api/v1/health", _health),
    Route("/api/v1/login", _login, methods=["POST"]),
    Route("/api/v1/users", _usuarios),
    Route("/api/v1/teams", _teams),
    Route("/api/v1/teams/{tid}", _detalle),
    Route("/api/v1/teams/{tid}/plan", _plan, methods=["POST"]),
]


def crear_app(users, teams) -> Starlette:
    """App con stores inyectados directo (DI; útil para tests con starlette
    instalado). El deploy usa `app` (Postgres en startup)."""
    a = Starlette(routes=_RUTAS)
    a.state.users = users
    a.state.teams = teams
    return a


# --- App de deploy: stores Postgres desde env (uvicorn carga esto) -------
#
# Starlette >=0.36 quitó on_startup/on_shutdown: el ciclo de vida va por un
# `lifespan` (async context manager). Conectamos Postgres al entrar y lo
# cerramos al salir; los stores quedan en app.state (un solo set de
# handlers los lee de ahí).


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette):
    dsn = os.environ.get("LAIDEA_DB_DSN", "")
    if not dsn:
        raise RuntimeError("LAIDEA_DB_DSN requerido para la API de operador")
    db = await Database.conectar(dsn)
    app.state.users = PgUserStore(db)
    app.state.teams = PgTeamStore(db)
    try:
        yield
    finally:
        await db.cerrar()


app = Starlette(routes=_RUTAS, lifespan=_lifespan)
