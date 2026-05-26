"""Audit log de intentos admin rechazados.

Antes, un member que intentaba `admin_assign` / `create_invite` se ignoraba
en silencio absoluto: el server NO dejaba rastro de quién intentó qué. Sin
ese rastro, un audit de compliance o un diagnóstico ("¿por qué Carlos cree
que puede invitar?") era imposible.

Ahora cada rechazo va al log con nivel WARNING: cliente_id, rol actual,
acción intentada y team_id. El comportamiento NO cambia (la acción sigue
ignorándose); solo se gana el rastro.
"""

from __future__ import annotations

import asyncio
import json
import logging

import pytest
from websockets.asyncio.client import connect

from tests.conftest import autenticar, entrar_equipo, handshake


pytestmark = pytest.mark.asyncio


async def test_admin_assign_de_no_admin_se_loguea_como_warning(
    server_port: int, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="orux.server.sync")
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a, user="lider")   # admin
        await handshake(b, user="colado")  # member
        await b.send(json.dumps({
            "type": "admin_assign", "path": "z.py", "username": "colado",
        }))
        # Damos margen al server para procesar el mensaje y emitir el log.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)

    # Hay al menos UN warning del audit con la info esperada.
    rechazos = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "admin-rechazado" in r.message
    ]
    assert rechazos, f"esperaba warning de audit; logs: {caplog.records}"
    msg = rechazos[0].message
    assert "colado" in msg
    assert "admin_assign" in msg
    assert "z.py" in msg


async def test_admin_assign_many_de_no_admin_se_loguea(
    server_port: int, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="orux.server.sync")
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a, user="lider")
        await handshake(b, user="colado")
        await b.send(json.dumps({
            "type": "admin_assign_many",
            "paths": ["a.py", "b.py", "c.py"],
            "username": "colado",
        }))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)

    rechazos = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "admin-rechazado" in r.message
    ]
    assert rechazos, (
        f"esperaba al menos un WARNING 'admin-rechazado'; "
        f"caplog tuvo {[r.message for r in caplog.records]}"
    )
    assert "admin_assign_many" in rechazos[0].message
    assert "n=3" in rechazos[0].message  # tamaño del lote


async def test_create_invite_de_no_admin_se_loguea(
    server_port: int, caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.WARNING, logger="orux.server.sync")
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a, user="lider")
        await handshake(b, user="colado")
        await b.send(json.dumps({"type": "create_invite"}))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)

    rechazos = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "admin-rechazado" in r.message
    ]
    assert rechazos, (
        f"esperaba al menos un WARNING 'admin-rechazado'; "
        f"caplog tuvo {[r.message for r in caplog.records]}"
    )
    assert "create_invite" in rechazos[0].message


async def test_admin_legitimo_no_genera_log_de_rechazo(
    server_port: int, caplog: pytest.LogCaptureFixture,
) -> None:
    """Un admin que opera normalmente NO debe inflar el audit. El log de
    rechazo es señal, no ruido."""
    caplog.set_level(logging.WARNING, logger="orux.server.sync")
    async with connect(f"ws://localhost:{server_port}") as a:
        await handshake(a, user="lider")
        await a.send(json.dumps({"type": "create_invite"}))
        # Espera el invite_created
        for _ in range(3):
            try:
                m = json.loads(
                    await asyncio.wait_for(a.recv(), timeout=1.0)
                )
                if m.get("type") == "invite_created":
                    break
            except asyncio.TimeoutError:
                break

    rechazos = [
        r for r in caplog.records
        if r.levelno == logging.WARNING and "admin-rechazado" in r.message
    ]
    assert rechazos == []
