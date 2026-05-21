"""Fixtures y helpers compartidos por los tests de integración.

Esto resuelve BACKEND-AUDIT-0297 (helpers críticos duplicados en test_sync y
test_robustez) y BACKEND-AUDIT-0298 (test_sync monolítico). El conftest no
parte test_sync.py — eso lo decide el dev del equipo cuando quiera; sólo
centraliza el contrato común para que cualquier archivo nuevo de tests no
recopie 100 LOC de boilerplate.

Lo que vive acá:
- `autenticar(ws, ...)`: pasa la compuerta de capa 7 (register/login).
- `entrar_equipo(ws)`: pasa el gate de capa 15 (create/redeem/select team).
- `handshake(ws, ...)`: auth + team + consumir init/welcome/ownership/admin_info.
- `recv_tipo(ws, tipo, ...)`: lee descartando otros tipos.
- `server_port` fixture: SyncServer en memoria sobre puerto efímero.

Lo que NO vive acá (todavía):
- helpers específicos de un dominio chico (git seed, oauth fake): viven con
  sus tests para no enredar este conftest.
- el helper `_coord_limpio` autouse: lo dejamos en test_sync.py porque solo
  él (y archivos hermanos que importen directo) usan el coordinador.

Marcadores definidos:
- `slow`: tests que toman >1s (sleeps, retries reales).
- `integration`: tests que levantan un server real.
"""

from __future__ import annotations

import asyncio
import itertools
import json
from typing import Any

import pytest
import pytest_asyncio
from websockets.asyncio.server import serve

from orux.server.sync import SyncServer


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "slow: tests que toman más de 1s",
    )
    config.addinivalue_line(
        "markers", "integration: tests que levantan un server real",
    )


# Contador global de usuarios. Cada test tiene su propio server con UserStore
# en memoria; un nombre único en el módulo solo necesita ser único POR TEST.
_user_seq = itertools.count(1)


def usuario_nuevo() -> str:
    """Nombre de usuario único dentro de esta sesión de pytest."""
    return f"user{next(_user_seq)}"


# Default de password para tests: pasa el mínimo de 8 chars + se mantiene
# legible para debugging. Si un test quiere validar el límite de pwd, pasa
# otra.
PWD_TEST = "pw-test12"


@pytest_asyncio.fixture
async def server_port():
    """Levanta un SyncServer en memoria en un puerto libre; lo cierra al
    terminar el test. Estado limpio por test."""
    sync_server = SyncServer()
    ws_server = await serve(sync_server.handle, "localhost", 0)
    port = ws_server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        ws_server.close()
        await ws_server.wait_closed()


@pytest_asyncio.fixture
async def servidor():
    """Como `server_port` pero cede (SyncServer, puerto). Útil cuando el
    test necesita inspeccionar el estado interno del server tras el flujo."""
    sync_server = SyncServer()
    ws_server = await serve(sync_server.handle, "localhost", 0)
    port = ws_server.sockets[0].getsockname()[1]
    try:
        yield sync_server, port
    finally:
        ws_server.close()
        await ws_server.wait_closed()


async def autenticar(ws, *, user: str | None = None, password: str = PWD_TEST,
                     registrar: bool = True):
    """Pasa la compuerta de auth (capa 7). Devuelve (usuario, auth_ok dict).

    - `user=None`: registra un usuario único nuevo.
    - `user` dado + `registrar=True`: lo registra.
    - `user` dado + `registrar=False`: hace login.
    """
    if user is None:
        user = usuario_nuevo()
    tipo = "register" if registrar else "login"
    await ws.send(json.dumps({
        "type": tipo, "username": user, "password": password,
    }))
    authok = json.loads(await ws.recv())
    assert authok["type"] == "auth_ok", f"auth falló: {authok}"
    return user, authok


async def recv_tipo(ws, tipo: str, timeout: float = 2) -> dict[str, Any]:
    """Lee descartando mensajes de otros tipos hasta encontrar `tipo`. Útil
    cuando un test no quiere depender del orden exacto del stream del
    server (broadcasts intercalados, p. ej.)."""
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if msg["type"] == tipo:
            return msg


# Coordinador de equipos por test_sync. Vive acá para que test_robustez
# (u otro hermano) pueda reusarlo si lo necesita. El autouse de limpieza lo
# emite test_sync para no acoplar conftest a su flujo específico.
_coord_equipos: dict[int, dict] = {}


def _coord_clear() -> None:
    _coord_equipos.clear()


def _puerto(ws) -> int | str:
    try:
        return ws.remote_address[1]
    except Exception:  # pragma: no cover
        return "default"


async def entrar_equipo(ws) -> None:
    """Pasa el gate de equipo (capa 15). Primer cliente del server: crea el
    equipo. Siguientes: el admin (primer cliente) emite un código de un
    solo uso y este se une. Deja la conexión en `team_ready`."""
    lobby = json.loads(await ws.recv())
    assert lobby["type"] == "lobby", f"esperaba lobby, llegó {lobby}"
    port = _puerto(ws)
    if lobby["teams"]:
        await ws.send(json.dumps(
            {"type": "select_team", "team_id": lobby["teams"][0]["id"]},
        ))
    else:
        coord = _coord_equipos.get(port)
        if coord is None:
            await ws.send(json.dumps(
                {"type": "create_team", "nombre": f"eq-{port}"},
            ))
            _coord_equipos[port] = {"ws": ws}
        else:
            admin_ws = coord["ws"]
            await admin_ws.send(json.dumps({"type": "create_invite"}))
            ic = await recv_tipo(admin_ws, "invite_created")
            await ws.send(json.dumps(
                {"type": "redeem_invite", "code": ic["code"]},
            ))
    tr = json.loads(await ws.recv())
    assert tr["type"] == "team_ready", f"esperaba team_ready, llegó {tr}"


async def handshake(ws, *, user: str | None = None, password: str = PWD_TEST,
                    registrar: bool = True) -> dict:
    """autenticar + gate de equipo + consumir init/welcome/ownership/
    admin_info. Devuelve el welcome.

    `git_status` (si hay git) viene DESPUÉS y lo leen los tests de git
    ellos mismos (vía `recv_tipo`).
    """
    await autenticar(ws, user=user, password=password, registrar=registrar)
    await entrar_equipo(ws)
    init = json.loads(await ws.recv())
    assert init["type"] == "init", f"esperaba init, llegó {init}"
    welcome = json.loads(await ws.recv())
    assert welcome["type"] == "welcome", f"esperaba welcome, llegó {welcome}"
    ownership = json.loads(await ws.recv())
    assert ownership["type"] == "ownership", f"esperaba ownership, llegó {ownership}"
    admin_info = json.loads(await ws.recv())
    assert admin_info["type"] == "admin_info", f"esperaba admin_info, llegó {admin_info}"
    return welcome


@pytest.fixture(autouse=True)
def _coord_limpio_global():
    """Resetea el coordinador de equipos entre tests. Lo cubre tanto
    test_sync como cualquier test que importe estos helpers — antes vivía
    duplicado en test_sync.py."""
    _coord_clear()
    yield
    _coord_clear()
