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
from laidea.state import DiskStorage


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


@pytest_asyncio.fixture
async def servidor():
    """Como `server_port` pero cede (SyncServer, puerto).

    Útil cuando el test necesita pre-sembrar el workspace: un archivo con
    contenido y SIN dueño. Ese estado es real, no artificial: es exactamente
    lo que hay tras hidratar de disco al arrancar (capa 3), porque el
    ownership es efímero y no se persiste.
    """
    sync_server = SyncServer()
    ws_server = await serve(sync_server.handle, "localhost", 0)
    port = ws_server.sockets[0].getsockname()[1]
    try:
        yield sync_server, port
    finally:
        ws_server.close()
        await ws_server.wait_closed()


async def handshake(ws) -> dict:
    """Consume init + welcome + ownership (handshake completo). Devuelve el welcome.

    Casi todos los tests no estudian el handshake, solo necesitan pasarlo para
    llegar al comportamiento que sí prueban. Centralizarlo aquí evita que cada
    test conozca el detalle de cuántos mensajes manda el servidor al conectar
    (init capa 1, welcome capa 2, ownership capa 4).
    """
    init = json.loads(await ws.recv())
    assert init["type"] == "init"
    welcome = json.loads(await ws.recv())
    assert welcome["type"] == "welcome"
    ownership = json.loads(await ws.recv())
    assert ownership["type"] == "ownership"
    return welcome


async def recv_tipo(ws, tipo: str, timeout: float = 2):
    """Lee descartando mensajes de otros tipos hasta encontrar `tipo`.

    Capa 4: crear un archivo hace dueño al creador y difunde un `ownership`
    a todos. Ese mensaje legítimo puede intercalarse con lo que un test de
    capa 1 espera, así que filtramos por tipo en vez de asumir orden exacto.
    """
    while True:
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=timeout))
        if msg["type"] == tipo:
            return msg


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
    # Contrato vigente: el servidor NUNCA le hace eco a A de su propio update
    # (le saltaría el cursor). Capa 4: como A está *creando* x.py, sí recibe
    # un `ownership` (queda dueño automáticamente) — eso es correcto y nuevo.
    # Lo que NO debe llegarle jamás es un `update` con su propio texto.
    async with connect(f"ws://localhost:{server_port}") as a:
        wa = await handshake(a)
        await a.send(json.dumps({"type": "update", "path": "x.py", "content": "yo"}))
        own = json.loads(await asyncio.wait_for(a.recv(), timeout=2))
        assert own == {
            "type": "ownership",
            "owners": {"x.py": wa["you"]["client_id"]},
        }
        # Después de eso, silencio: ni eco del update ni nada más.
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

        # B debe recibir el update de A para main.py (filtrando los `ownership`
        # que la creación de archivos difunde ahora a todos).
        msg_b = await recv_tipo(b, "update")
        assert msg_b == {"type": "update", "path": "main.py", "content": "A edita main"}

        # A debe recibir el update de B para auth.py
        msg_a = await recv_tipo(a, "update")
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


# --- Capa 3: persistencia end-to-end ---


async def test_server_reiniciado_sirve_lo_persistido(tmp_path) -> None:
    # El ciclo completo que justifica la capa 3: un server con storage recibe
    # una edición, "se reinicia" (server nuevo sobre la misma carpeta) y un
    # cliente que conecta ve el archivo ya en su init, sin que nadie lo reenvíe.
    storage_a = DiskStorage(tmp_path)
    srv_a = SyncServer(storage=storage_a)
    ws_a = await serve(srv_a.handle, "localhost", 0)
    port_a = ws_a.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port_a}") as c:
            await handshake(c)
            await c.send(
                json.dumps({"type": "update", "path": "main.py", "content": "x = 1"})
            )
            await asyncio.sleep(0.05)  # dar tiempo a persistir
    finally:
        ws_a.close()
        await ws_a.wait_closed()

    # Server nuevo, mismo directorio: simula reinicio del proceso.
    srv_b = SyncServer(storage=DiskStorage(tmp_path))
    ws_b = await serve(srv_b.handle, "localhost", 0)
    port_b = ws_b.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port_b}") as c:
            init = json.loads(await c.recv())
            assert init == {"type": "init", "files": {"main.py": "x = 1"}}
    finally:
        ws_b.close()
        await ws_b.wait_closed()


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


# --- Capa 4: ownership + edición tentativa ---


async def _drenar_ownership(ws) -> dict:
    """Lee el siguiente mensaje esperando que sea un ownership; lo devuelve."""
    msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
    assert msg["type"] == "ownership", f"esperaba ownership, llegó {msg}"
    return msg


async def test_ownership_vacio_en_el_handshake(server_port: int) -> None:
    # Tercer mensaje del handshake (capa 4): el mapa de ownership, vacío al
    # arrancar. init (capa 1) -> welcome (capa 2) -> ownership (capa 4).
    async with connect(f"ws://localhost:{server_port}") as a:
        assert json.loads(await a.recv())["type"] == "init"
        assert json.loads(await a.recv())["type"] == "welcome"
        assert json.loads(await a.recv()) == {"type": "ownership", "owners": {}}


async def test_claim_difunde_el_mapa_a_todos(server_port: int) -> None:
    # Reclamar dueño difunde el mapa entero a todos, incluido quien reclamó
    # (su UI confirma que quedó como dueño).
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        wa = await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "claim", "path": "main.py"}))
        esperado = {"type": "ownership", "owners": {"main.py": wa["you"]["client_id"]}}
        assert await _drenar_ownership(a) == esperado
        assert await _drenar_ownership(b) == esperado


async def test_edit_de_no_dueno_es_tentativo(server_port: int) -> None:
    # El corazón de la capa: si B edita un archivo cuyo dueño es A, el cambio
    # NO se aplica ni se difunde — le llega a A como propuesta.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        wb = await handshake(b)
        await a.send(json.dumps({"type": "claim", "path": "main.py"}))
        await _drenar_ownership(a)
        await _drenar_ownership(b)

        await b.send(json.dumps({"type": "update", "path": "main.py", "content": "hola de B"}))

        prop = json.loads(await asyncio.wait_for(a.recv(), timeout=2))
        assert prop["type"] == "proposal"
        assert prop["proposal"]["author_id"] == wb["you"]["client_id"]
        assert prop["proposal"]["path"] == "main.py"
        assert prop["proposal"]["content"] == "hola de B"

        # B no recibe nada (su cambio no se difundió).
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)

        # El workspace autoritativo no cambió: un cliente nuevo no ve main.py.
        async with connect(f"ws://localhost:{server_port}") as c:
            assert json.loads(await c.recv()) == {"type": "init", "files": {}}


async def test_crear_archivo_hace_dueno_al_creador(server_port: int) -> None:
    # El fix del bug: crear un archivo (primer update sobre un path nuevo) hace
    # dueño al creador automáticamente, sin botón. Antes nacía sin dueño.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        wa = await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "update", "path": "nuevo.py", "content": "hola"}))

        # B ve el archivo y, enseguida, el mapa de ownership con el creador.
        assert await recv_tipo(b, "update") == {
            "type": "update", "path": "nuevo.py", "content": "hola",
        }
        esperado = {"type": "ownership", "owners": {"nuevo.py": wa["you"]["client_id"]}}
        assert await recv_tipo(b, "ownership") == esperado
        # El propio creador recibe el ownership (su UI pinta "tuyo" sin pedir).
        assert await recv_tipo(a, "ownership") == esperado

        # Y como ya es suyo: si B lo edita, es tentativo (propuesta), no se aplica.
        await b.send(json.dumps({"type": "update", "path": "nuevo.py", "content": "B mete mano"}))
        prop = await recv_tipo(a, "proposal")
        assert prop["proposal"]["path"] == "nuevo.py"
        assert prop["proposal"]["content"] == "B mete mano"


async def test_aprobar_propuesta_aplica_y_converge(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        wb = await handshake(b)
        await a.send(json.dumps({"type": "claim", "path": "main.py"}))
        await _drenar_ownership(a)
        await _drenar_ownership(b)
        await b.send(json.dumps({"type": "update", "path": "main.py", "content": "v de B"}))
        prop = json.loads(await asyncio.wait_for(a.recv(), timeout=2))
        pid = prop["proposal"]["id"]

        await a.send(json.dumps({"type": "resolve", "proposal_id": pid, "accept": True}))

        # Converge TODO el mundo, incluido el dueño que aprobó.
        esperado = {"type": "update", "path": "main.py", "content": "v de B"}
        assert json.loads(await asyncio.wait_for(a.recv(), timeout=2)) == esperado
        assert json.loads(await asyncio.wait_for(b.recv(), timeout=2)) == esperado
        async with connect(f"ws://localhost:{server_port}") as c:
            assert json.loads(await c.recv()) == {
                "type": "init",
                "files": {"main.py": "v de B"},
            }


async def test_rechazar_propuesta_revierte_al_autor(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "claim", "path": "main.py"}))
        await _drenar_ownership(a)
        await _drenar_ownership(b)

        # El dueño escribe contenido autoritativo (se aplica directo).
        await a.send(json.dumps({"type": "update", "path": "main.py", "content": "v1 del dueño"}))
        assert json.loads(await asyncio.wait_for(b.recv(), timeout=2)) == {
            "type": "update", "path": "main.py", "content": "v1 del dueño",
        }

        # B propone otra cosa -> tentativo.
        await b.send(json.dumps({"type": "update", "path": "main.py", "content": "v2 de B"}))
        prop = json.loads(await asyncio.wait_for(a.recv(), timeout=2))
        pid = prop["proposal"]["id"]

        # A rechaza: a B se le revierte al contenido autoritativo.
        await a.send(json.dumps({"type": "resolve", "proposal_id": pid, "accept": False}))
        assert json.loads(await asyncio.wait_for(b.recv(), timeout=2)) == {
            "type": "update", "path": "main.py", "content": "v1 del dueño",
        }


async def test_solo_el_dueno_puede_resolver(server_port: int) -> None:
    # Un no-dueño que arma el id determinista de la propuesta y manda resolve
    # no debe poder aplicar nada.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        wb = await handshake(b)
        await a.send(json.dumps({"type": "claim", "path": "main.py"}))
        await _drenar_ownership(a)
        await _drenar_ownership(b)
        await b.send(json.dumps({"type": "update", "path": "main.py", "content": "intento"}))
        await asyncio.wait_for(a.recv(), timeout=2)  # la propuesta le llega a A

        # B (autor, no dueño) intenta auto-aprobarse con el id determinista.
        pid = f"main.py::{wb['you']['client_id']}"
        await b.send(json.dumps({"type": "resolve", "proposal_id": pid, "accept": True}))

        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)
        async with connect(f"ws://localhost:{server_port}") as c:
            assert json.loads(await c.recv()) == {"type": "init", "files": {}}


# --- Identidad estable mínima (token, sin auth) ---


async def test_mismo_token_misma_identidad(server_port: int) -> None:
    # Reconectar con el mismo token devuelve la MISMA identidad: es lo que
    # hace que recargar la página no pierda el ownership.
    tok = "tok-estable"
    async with connect(f"ws://localhost:{server_port}/?token={tok}") as a:
        w1 = await handshake(a)
    async with connect(f"ws://localhost:{server_port}/?token={tok}") as a2:
        w2 = await handshake(a2)
    assert w2["you"]["client_id"] == w1["you"]["client_id"]
    assert w2["you"]["name"] == w1["you"]["name"]
    assert w2["you"]["color"] == w1["you"]["color"]


async def test_sin_token_identidad_fresca(server_port: int) -> None:
    # Sin token (cliente viejo / test) seguimos dando identidad anónima nueva
    # cada vez: no rompemos el comportamiento previo.
    async with connect(f"ws://localhost:{server_port}") as a:
        w1 = await handshake(a)
    async with connect(f"ws://localhost:{server_port}") as b:
        w2 = await handshake(b)
    assert w1["you"]["client_id"] != w2["you"]["client_id"]


async def test_ownership_sobrevive_reconexion(server_port: int) -> None:
    # El fix de fondo: A reclama, "recarga la página" (se desconecta y vuelve
    # con el mismo token) y SIGUE siendo dueño. Antes el ownership se liberaba
    # al desconectar y se perdía en el hueco.
    tok = "tok-dueno"
    async with connect(f"ws://localhost:{server_port}") as b:
        await handshake(b)
        async with connect(f"ws://localhost:{server_port}/?token={tok}") as a:
            wa = await handshake(a)
            await a.send(json.dumps({"type": "claim", "path": "x.py"}))
            await _drenar_ownership(a)
            assert await _drenar_ownership(b) == {
                "type": "ownership", "owners": {"x.py": wa["you"]["client_id"]},
            }
        # A se desconectó: B NO debe recibir un mapa vacío (ya no se libera).
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)

        # A vuelve con el mismo token: misma identidad y sigue siendo dueño.
        async with connect(f"ws://localhost:{server_port}/?token={tok}") as a2:
            assert json.loads(await a2.recv())["type"] == "init"
            welcome = json.loads(await a2.recv())
            assert welcome["you"]["client_id"] == wa["you"]["client_id"]
            own = json.loads(await a2.recv())
            assert own == {
                "type": "ownership", "owners": {"x.py": wa["you"]["client_id"]},
            }
            # Prueba fuerte: B (no dueño) edita x.py -> es tentativo y la
            # propuesta le llega a A2. Solo pasa si A2 sigue siendo el dueño.
            await b.send(json.dumps({"type": "update", "path": "x.py", "content": "B intenta"}))
            prop = await recv_tipo(a2, "proposal")
            assert prop["proposal"]["path"] == "x.py"
            assert prop["proposal"]["content"] == "B intenta"


# --- Capa 5: prevención de colisiones por línea ---


async def test_no_puedes_pisar_la_linea_de_otro(servidor) -> None:
    srv, port = servidor
    # Archivo con contenido y SIN dueño: el estado real tras hidratar de disco.
    srv.workspace.update("shared.py", "l1\nl2\nl3")
    async with connect(f"ws://localhost:{port}") as b, connect(
        f"ws://localhost:{port}"
    ) as c:
        await handshake(b)
        await handshake(c)

        # B se para en la línea 2 de shared.py.
        await b.send(json.dumps({"type": "presence", "path": "shared.py", "line": 2}))
        await asyncio.sleep(0.05)

        # C intenta modificar la línea 2 -> rechazado, le vuelve lo autoritativo.
        await c.send(
            json.dumps({"type": "update", "path": "shared.py", "content": "l1\nC PISA\nl3"})
        )
        rebote = await recv_tipo(c, "update")
        assert rebote == {"type": "update", "path": "shared.py", "content": "l1\nl2\nl3"}

        # B (el que ocupaba la línea) no recibe el cambio de C: no se aplicó.
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)

        # El workspace no cambió: un cliente nuevo ve el contenido original.
        async with connect(f"ws://localhost:{port}") as d:
            assert json.loads(await d.recv()) == {
                "type": "init", "files": {"shared.py": "l1\nl2\nl3"},
            }


async def test_editar_otra_linea_si_se_aplica(servidor) -> None:
    srv, port = servidor
    srv.workspace.update("shared.py", "l1\nl2\nl3")
    async with connect(f"ws://localhost:{port}") as b, connect(
        f"ws://localhost:{port}"
    ) as c:
        await handshake(b)
        await handshake(c)
        await b.send(json.dumps({"type": "presence", "path": "shared.py", "line": 2}))
        await asyncio.sleep(0.05)

        # C edita la línea 1 (B está en la 2): no hay colisión, se aplica.
        await c.send(
            json.dumps({"type": "update", "path": "shared.py", "content": "C1\nl2\nl3"})
        )
        assert await recv_tipo(b, "update") == {
            "type": "update", "path": "shared.py", "content": "C1\nl2\nl3",
        }


async def test_el_dueno_pisa_sin_lock(server_port: int) -> None:
    # "El owner tiene preferencia": el dueño puede escribir una línea que otro
    # presente está ocupando; el lock no le aplica.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        await handshake(b)
        # A crea (y por lo tanto es dueño de) owned.py.
        await a.send(
            json.dumps({"type": "update", "path": "owned.py", "content": "l1\nl2"})
        )
        assert await recv_tipo(b, "update") == {
            "type": "update", "path": "owned.py", "content": "l1\nl2",
        }
        await recv_tipo(b, "ownership")  # A quedó dueño
        await recv_tipo(a, "ownership")

        # B se para en la línea 1.
        await b.send(json.dumps({"type": "presence", "path": "owned.py", "line": 1}))
        await asyncio.sleep(0.05)

        # A (dueño) pisa esa misma línea 1: se aplica igual (preferencia).
        await a.send(
            json.dumps({"type": "update", "path": "owned.py", "content": "DUENO\nl2"})
        )
        assert await recv_tipo(b, "update") == {
            "type": "update", "path": "owned.py", "content": "DUENO\nl2",
        }
