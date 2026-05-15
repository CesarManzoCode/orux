"""Tests de integración del servidor de sincronización."""

import asyncio
import json

import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from laidea.server.sync import SyncServer


@pytest_asyncio.fixture
async def server_port():
    """Levanta un SyncServer en un puerto libre, lo cede al test y lo cierra al final."""
    sync_server = SyncServer()
    ws_server = await serve(sync_server.handle, "localhost", 0)
    port = ws_server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        ws_server.close()
        await ws_server.wait_closed()


async def test_initial_state_is_empty(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as ws:
        msg = json.loads(await ws.recv())
        assert msg == {"type": "init", "content": ""}


async def test_edit_propagates_to_other_client(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await a.recv()
        await b.recv()
        await a.send(json.dumps({"type": "update", "content": "hola desde A"}))
        msg = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert msg == {"type": "update", "content": "hola desde A"}


async def test_late_joiner_gets_current_state(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a:
        await a.recv()
        await a.send(json.dumps({"type": "update", "content": "estado actual"}))
        await asyncio.sleep(0.05)
        async with connect(f"ws://localhost:{server_port}") as late:
            msg = json.loads(await late.recv())
            assert msg == {"type": "init", "content": "estado actual"}


async def test_sender_does_not_receive_echo(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a:
        await a.recv()
        await a.send(json.dumps({"type": "update", "content": "no me lo devuelvas"}))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(a.recv(), timeout=0.3)
