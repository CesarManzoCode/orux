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
(`ORUX_ADMIN_USER`) que entra con su usuario+contraseña normales y
recibe un token de SESIÓN firmado (HMAC; secreto `ORUX_ADMIN_TOKEN` que
NUNCA sale del server — solo firma/verifica). Antes el cliente mandaba el
secreto crudo en cada request; ahora no transmite ningún secreto. Sin
`ORUX_ADMIN_USER` o sin `ORUX_ADMIN_TOKEN` la API queda CERRADA (503),
nunca abierta. La lógica (PBKDF2 + firmar/validar) vive en `service.py` y
se prueba 100% en sandbox; acá solo HTTP. Los stores viven en `app.state`
(deploy: Postgres en startup; tests: inyectados) — UN set de handlers.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import urllib.error
import urllib.parse
import urllib.request

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse
from starlette.routing import Route

from ..db.pool import Database
from ..db.stores import PgUserStore
from ..identity import (
    crear_token,
    firmar_state,
    identidad_github,
    url_autorizacion,
    validar_state,
)
from ..identity.oauth import URL_PERFIL, URL_TOKEN
from ..teams import PgTeamStore
from . import service

logger = logging.getLogger(__name__)

# Quién es el operador (una cuenta registrada) y el secreto de FIRMA de sus
# tokens de sesión (nunca se manda al cliente). Faltando cualquiera: 503.
_ADMIN_USER = os.environ.get("ORUX_ADMIN_USER", "")
_SECRET = os.environ.get("ORUX_ADMIN_TOKEN", "")

# --- GitHub OAuth (capa nueva, superficie PÚBLICA, no la de operador) -----
#
# Cerrado por defecto: faltando cualquier pieza, /oauth/github/* responde
# 503 y NUNCA inicia un flujo a medias (mismo principio que la consola de
# operador). `_SESSION_SECRET` es el MISMO que verifica el server WS
# (ORUX_SESSION_SECRET inyectado a ambos contenedores): el token que se
# emite acá lo acepta `SessionMessage` tal cual, sin tocar el protocolo.
_GH_CLIENT_ID = os.environ.get("ORUX_GITHUB_CLIENT_ID", "")
_GH_CLIENT_SECRET = os.environ.get("ORUX_GITHUB_CLIENT_SECRET", "")
# URL EXACTA registrada en la OAuth App de GitHub. Explícita a propósito:
# derivarla del header Host sería spoofeable (open redirect / robo de code).
_GH_REDIRECT = os.environ.get("ORUX_OAUTH_REDIRECT", "")
_SESSION_SECRET = os.environ.get("ORUX_SESSION_SECRET", "")
# A dónde vuelve el navegador con el token ya emitido. El front (otra
# sesión) lo lee de `?session=` y manda `SessionMessage`, igual que el
# auto-login con `orux_session`. Default razonable: el SPA en /app/.
_APP_URL = os.environ.get("ORUX_APP_URL", "/app/")


def _oauth_ok() -> bool:
    return bool(
        _GH_CLIENT_ID and _GH_CLIENT_SECRET
        and _GH_REDIRECT and _SESSION_SECRET
    )


def _volver(error: str = "", token: str = ""):
    """Redirige el navegador de vuelta al SPA. Con token (éxito) o con un
    código de error legible (el front decide qué mostrar). 302."""
    par = {"session": token} if token else {"oauth_error": error}
    sep = "&" if "?" in _APP_URL else "?"
    return RedirectResponse(
        f"{_APP_URL}{sep}{urllib.parse.urlencode(par)}", status_code=302
    )


def _intercambiar(code: str) -> dict:
    """Bloqueante (urllib, stdlib — cero deps): canjea `code` por un token y
    lee el perfil de GitHub. Vive en la cáscara y se corre en el threadpool;
    se ejercita en el VPS (sandbox sin internet), igual que toda la I/O de
    `api/app.py`. Timeouts cortos: un GitHub colgado no cuelga al worker."""
    datos = urllib.parse.urlencode({
        "client_id": _GH_CLIENT_ID,
        "client_secret": _GH_CLIENT_SECRET,
        "code": code,
        "redirect_uri": _GH_REDIRECT,
    }).encode("ascii")
    r1 = urllib.request.Request(
        URL_TOKEN, data=datos, headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(r1, timeout=10) as resp:
        tok = json.loads(resp.read())["access_token"]
    r2 = urllib.request.Request(
        URL_PERFIL,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "orux",
        },
    )
    with urllib.request.urlopen(r2, timeout=10) as resp:
        return json.loads(resp.read())


async def _gh_login(_req: Request):
    """Arranca el flujo: 302 a GitHub con un `state` CSRF firmado (stateless,
    se valida en el callback). Sin configurar: 503, no a medias."""
    if not _oauth_ok():
        return JSONResponse(
            {"error": "GitHub OAuth no configurado"}, status_code=503
        )
    state = firmar_state(_SESSION_SECRET)
    return RedirectResponse(
        url_autorizacion(_GH_CLIENT_ID, _GH_REDIRECT, state),
        status_code=302,
    )


async def _gh_callback(req: Request):
    """GitHub vuelve acá. Valida `state`, canjea `code`, deriva la identidad
    `gh:<login>`, asegura la cuenta (sin password) y emite el MISMO token de
    sesión de la capa 7. Cualquier fallo -> vuelve al SPA con un error
    legible, nunca un 500 crudo (esto lo ve un humano en el navegador)."""
    if not _oauth_ok():
        return JSONResponse(
            {"error": "GitHub OAuth no configurado"}, status_code=503
        )
    if req.query_params.get("error"):
        # El usuario canceló el consentimiento en GitHub.
        return _volver(error="cancelado")
    code = req.query_params.get("code", "")
    state = req.query_params.get("state", "")
    if not code or not validar_state(state, _SESSION_SECRET):
        # state ausente/falso/vencido: posible CSRF o link viejo.
        return _volver(error="state")
    from starlette.concurrency import run_in_threadpool

    try:
        perfil = await run_in_threadpool(_intercambiar, code)
        usuario = identidad_github(perfil)
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        logger.warning("OAuth GitHub falló: %r", e)
        return _volver(error="github")
    await req.app.state.users.asegurar_externo(usuario)
    token = crear_token(usuario, _SESSION_SECRET)
    logger.info("OAuth GitHub OK: %s", usuario)
    return _volver(token=token)


def _gate(req: Request) -> JSONResponse | None:
    """None = pasa. Sin configurar: cerrado (503). Token de sesión inválido
    o no es el operador: 401. La validación (firma HMAC + que el usuario
    SEA el operador) la hace `service.operador_de_token` (pura, testeada)."""
    if not _ADMIN_USER or not _SECRET:
        return JSONResponse(
            {"error": "API de operador no configurada (falta "
                      "ORUX_ADMIN_USER / ORUX_ADMIN_TOKEN)"},
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
    # GitHub OAuth: superficie PÚBLICA (sin _gate; no es la API de
    # operador). Caddy proxya /oauth/* a este contenedor.
    Route("/oauth/github/login", _gh_login),
    Route("/oauth/github/callback", _gh_callback),
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
    dsn = os.environ.get("ORUX_DB_DSN", "")
    if not dsn:
        raise RuntimeError("ORUX_DB_DSN requerido para la API de operador")
    db = await Database.conectar(dsn)
    app.state.users = PgUserStore(db)
    app.state.teams = PgTeamStore(db)
    try:
        yield
    finally:
        await db.cerrar()


app = Starlette(routes=_RUTAS, lifespan=_lifespan)
