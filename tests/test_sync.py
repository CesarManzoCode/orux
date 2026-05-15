"""Tests de integración del servidor de sincronización.

Estos tests levantan un servidor de verdad en un puerto efímero y conectan
clientes WebSocket reales contra él. Son más lentos que los tests unitarios
pero son los únicos que de verdad validan que el sistema completo funciona
end-to-end: protocolo + estado + servidor + red.

El fixture `server_port` arranca un servidor fresco por cada test. Es importante
que cada test tenga su servidor propio: si compartiéramos uno, el estado de un
test contaminaría al siguiente.
"""

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
    # Puerto 0 significa "asígname uno libre". Nos lo devuelve el sistema.
    ws_server = await serve(sync_server.handle, "localhost", 0)
    port = ws_server.sockets[0].getsockname()[1]
    try:
        yield port
    finally:
        ws_server.close()
        await ws_server.wait_closed()


async def test_initial_state_is_empty(server_port: int) -> None:
    # Cliente solo, sin nadie más conectado. Debe recibir init con files vacío.
    async with connect(f"ws://localhost:{server_port}") as ws:
        msg = json.loads(await ws.recv())
        assert msg == {"type": "init", "files": {}}


async def test_edit_propagates_to_other_client(server_port: int) -> None:
    # El test central: si A edita, B debe ver el cambio en tiempo real.
    # Si esto falla, no hay producto.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await a.recv()  # init de A
        await b.recv()  # init de B
        await a.send(json.dumps({"type": "update", "path": "main.py", "content": "x = 1"}))
        msg = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert msg == {"type": "update", "path": "main.py", "content": "x = 1"}


async def test_late_joiner_gets_current_state(server_port: int) -> None:
    # Un cliente que llega después debe recibir TODO el workspace en su init,
    # no solo lo que cambie a partir de ese momento. Sin esto, alguien que abra
    # el editor a media tarde no sabría qué hay editado.
    async with connect(f"ws://localhost:{server_port}") as a:
        await a.recv()
        await a.send(json.dumps({"type": "update", "path": "a.py", "content": "uno"}))
        await a.send(json.dumps({"type": "update", "path": "b.py", "content": "dos"}))
        await asyncio.sleep(0.05)  # darle tiempo al servidor a aplicar
        async with connect(f"ws://localhost:{server_port}") as late:
            msg = json.loads(await late.recv())
            assert msg == {"type": "init", "files": {"a.py": "uno", "b.py": "dos"}}


async def test_sender_does_not_receive_echo(server_port: int) -> None:
    # Si el servidor le devuelve a A lo que A acaba de mandar, el cursor de A
    # saltaría y la UX sería horrible. El test verifica que NO recibimos eco.
    async with connect(f"ws://localhost:{server_port}") as a:
        await a.recv()
        await a.send(json.dumps({"type": "update", "path": "x.py", "content": "yo"}))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(a.recv(), timeout=0.3)


async def test_edits_to_different_files_dont_interfere(server_port: int) -> None:
    # Test específico de la capa 1: si A edita main.py, B (que tiene abierto
    # auth.py) debe poder seguir editando auth.py sin perder sus cambios y
    # recibir el cambio de A solo para main.py.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await a.recv()
        await b.recv()
        await a.send(json.dumps({"type": "update", "path": "main.py", "content": "A edita main"}))
        await b.send(json.dumps({"type": "update", "path": "auth.py", "content": "B edita auth"}))

        # B debe recibir el update de A para main.py
        msg_b = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert msg_b == {"type": "update", "path": "main.py", "content": "A edita main"}

        # A debe recibir el update de B para auth.py
        msg_a = json.loads(await asyncio.wait_for(a.recv(), timeout=2))
        assert msg_a == {"type": "update", "path": "auth.py", "content": "B edita auth"}

        # Verificamos que un tercer cliente que entre vea ambos archivos sanos.
        async with connect(f"ws://localhost:{server_port}") as c:
            init_c = json.loads(await c.recv())
            assert init_c == {
                "type": "init",
                "files": {"main.py": "A edita main", "auth.py": "B edita auth"},
            }
