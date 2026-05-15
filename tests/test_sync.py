"""Tests de integración del servidor de sincronización.

Estos tests levantan un servidor de verdad en un puerto efímero y conectan
clientes WebSocket reales contra él. Son más lentos que los tests unitarios
pero son los únicos que de verdad validan que el sistema completo funciona
end-to-end: protocolo + estado + servidor + red.

El fixture `server_port` arranca un servidor fresco por cada test. Es importante
que cada test tenga su servidor propio: si compartiéramos uno, el estado de un
test contaminaría al siguiente.

Capa 2: al conectar, el servidor manda DOS mensajes de handshake: primero el
`init` (workspace, contrato de capa 1 intacto) y enseguida el `welcome`
(identidad de presencia + roster). El helper `handshake` consume ambos y
devuelve el welcome, para que cada test no tenga que repetir esa coreografía.
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


async def handshake(ws) -> dict:
    """Consume init + welcome (el handshake completo) y devuelve el welcome.

    Casi todos los tests no estudian el handshake, solo necesitan pasarlo para
    llegar al comportamiento que sí prueban. Centralizarlo aquí evita que cada
    test conozca el detalle de cuántos mensajes manda el servidor al conectar.
    """
    init = json.loads(await ws.recv())
    assert init["type"] == "init"
    welcome = json.loads(await ws.recv())
    assert welcome["type"] == "welcome"
    return welcome


# --- Contratos de capa 1 (siguen vigentes, solo se les sumó el welcome) ---


async def test_initial_state_is_empty(server_port: int) -> None:
    # Cliente solo, sin nadie más conectado. El PRIMER mensaje sigue siendo el
    # init con files vacío: ese contrato de capa 1 no cambió.
    async with connect(f"ws://localhost:{server_port}") as ws:
        msg = json.loads(await ws.recv())
        assert msg == {"type": "init", "files": {}}


async def test_edit_propagates_to_other_client(server_port: int) -> None:
    # El test central: si A edita, B debe ver el cambio en tiempo real.
    # Si esto falla, no hay producto.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "update", "path": "main.py", "content": "x = 1"}))
        msg = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert msg == {"type": "update", "path": "main.py", "content": "x = 1"}


async def test_late_joiner_gets_current_state(server_port: int) -> None:
    # Un cliente que llega después debe recibir TODO el workspace en su init,
    # no solo lo que cambie a partir de ese momento. Sin esto, alguien que abra
    # el editor a media tarde no sabría qué hay editado.
    async with connect(f"ws://localhost:{server_port}") as a:
        await handshake(a)
        await a.send(json.dumps({"type": "update", "path": "a.py", "content": "uno"}))
        await a.send(json.dumps({"type": "update", "path": "b.py", "content": "dos"}))
        await asyncio.sleep(0.05)  # darle tiempo al servidor a aplicar
        async with connect(f"ws://localhost:{server_port}") as late:
            msg = json.loads(await late.recv())
            assert msg == {"type": "init", "files": {"a.py": "uno", "b.py": "dos"}}


async def test_broadcast_always_includes_path(server_port: int) -> None:
    # Contrato del protocolo capa 1: todo UpdateMessage que el servidor manda
    # debe incluir `path`. Si esto se rompiera, los clientes nuevos crearían
    # archivos fantasma llamados "undefined" (bug histórico ya visto).
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "update", "path": "x.py", "content": "hola"}))
        msg = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert "path" in msg, f"broadcast no incluye path: {msg}"
        assert msg["path"] == "x.py"


async def test_sender_does_not_receive_echo(server_port: int) -> None:
    # Si el servidor le devuelve a A lo que A acaba de mandar, el cursor de A
    # saltaría y la UX sería horrible. El test verifica que NO recibimos eco.
    async with connect(f"ws://localhost:{server_port}") as a:
        await handshake(a)
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
        await handshake(a)
        await handshake(b)
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


# --- Capa 2: presencia ---


async def test_welcome_assigns_anonymous_identity(server_port: int) -> None:
    # Al conectar, el servidor te asigna identidad (id, nombre, color) y te la
    # manda en el welcome. El cliente no la elige. Sin nadie más, peers vacío.
    async with connect(f"ws://localhost:{server_port}") as a:
        welcome = await handshake(a)
        yo = welcome["you"]
        assert yo["client_id"]
        assert yo["name"].startswith("anónimo-")
        assert yo["color"].startswith("#")
        assert yo["path"] is None  # conectado pero todavía no presente
        assert welcome["peers"] == []


async def test_distinct_clients_get_distinct_ids(server_port: int) -> None:
    # Dos conexiones nunca comparten client_id: si lo hicieran, no podrías
    # distinguir quién está dónde.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        wa = await handshake(a)
        wb = await handshake(b)
        assert wa["you"]["client_id"] != wb["you"]["client_id"]


async def test_presence_propagates_with_path_and_line(server_port: int) -> None:
    # El corazón de la capa 2: si A se para en una línea de un archivo, B lo ve,
    # con la identidad confiable rellenada por el servidor (A solo mandó path+line).
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        wa = await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "presence", "path": "auth.py", "line": 14}))
        msg = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert msg == {
            "type": "presence",
            "client_id": wa["you"]["client_id"],
            "name": wa["you"]["name"],
            "color": wa["you"]["color"],
            "path": "auth.py",
            "line": 14,
        }


async def test_presence_no_echo_to_sender(server_port: int) -> None:
    # Igual que con los updates: no me devuelvas mi propia presencia.
    async with connect(f"ws://localhost:{server_port}") as a:
        await handshake(a)
        await a.send(json.dumps({"type": "presence", "path": "x.py", "line": 3}))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(a.recv(), timeout=0.3)


async def test_late_joiner_sees_present_peers(server_port: int) -> None:
    # Quien llega tarde debe ver de inmediato dónde está la gente, sin esperar
    # a que se muevan. Eso viaja en peers del welcome.
    async with connect(f"ws://localhost:{server_port}") as a:
        wa = await handshake(a)
        await a.send(json.dumps({"type": "presence", "path": "main.py", "line": 7}))
        await asyncio.sleep(0.05)
        async with connect(f"ws://localhost:{server_port}") as b:
            wb = await handshake(b)
            assert wb["peers"] == [
                {
                    "client_id": wa["you"]["client_id"],
                    "name": wa["you"]["name"],
                    "color": wa["you"]["color"],
                    "path": "main.py",
                    "line": 7,
                }
            ]


async def test_connected_but_not_present_is_not_in_roster(server_port: int) -> None:
    # Estar conectado no es estar presente: si A no abrió ningún archivo, no
    # aparece en el roster que recibe B.
    async with connect(f"ws://localhost:{server_port}") as a:
        await handshake(a)
        async with connect(f"ws://localhost:{server_port}") as b:
            wb = await handshake(b)
            assert wb["peers"] == []


async def test_leave_broadcast_on_disconnect(server_port: int) -> None:
    # Cuando alguien presente se va, los demás reciben un leave con su id para
    # despintarlo.
    async with connect(f"ws://localhost:{server_port}") as b:
        wb = await handshake(b)
        async with connect(f"ws://localhost:{server_port}") as a:
            wa = await handshake(a)
            await a.send(json.dumps({"type": "presence", "path": "x.py", "line": 1}))
            # b consume el presence de A para no confundirlo con el leave.
            presence = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
            assert presence["type"] == "presence"
        # Al salir del with, A se desconecta. B debe recibir el leave.
        msg = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert msg == {"type": "leave", "client_id": wa["you"]["client_id"]}
        assert wb  # (b siguió conectado todo el tiempo)


async def test_no_leave_if_never_present(server_port: int) -> None:
    # Si alguien se conecta y se va SIN abrir un archivo, nadie lo tenía
    # pintado: no debe generarse ningún leave (sería ruido).
    async with connect(f"ws://localhost:{server_port}") as b:
        await handshake(b)
        async with connect(f"ws://localhost:{server_port}") as a:
            await handshake(a)
            # a no manda presencia y se desconecta al cerrar el with.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)
