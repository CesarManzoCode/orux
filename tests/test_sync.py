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
import itertools
import json

import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from laidea.git import GitRepo
from laidea.server.sync import SyncServer
from laidea.state import DiskStorage

# Capa 7: la app está cerrada. Cada test necesita usuarios; este contador da
# nombres únicos para que dos clientes de un test sean identidades distintas.
# Cada test tiene su server (UserStore en memoria), así que repetir entre
# tests es inocuo.
_user_seq = itertools.count(1)


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


async def autenticar(ws, *, user=None, password="pw", registrar=True):
    """Pasa la compuerta de auth (capa 7). Devuelve (usuario, auth_ok dict).

    - `user=None`: registra un usuario único nuevo (caso común: clientes
      distintos = identidades distintas).
    - `user` dado + `registrar=True`: lo registra. `registrar=False`: hace
      login (para tests de reconexión con la MISMA identidad).

    Deja la conexión justo antes del `init`: lo que el server manda después
    de `auth_ok` es el handshake normal.
    """
    if user is None:
        user = f"user{next(_user_seq)}"
    tipo = "register" if registrar else "login"
    await ws.send(
        json.dumps({"type": tipo, "username": user, "password": password})
    )
    authok = json.loads(await ws.recv())
    assert authok["type"] == "auth_ok", f"auth falló: {authok}"
    return user, authok


async def handshake(ws, *, user=None, password="pw", registrar=True) -> dict:
    """autenticar + consumir init+welcome+ownership. Devuelve el welcome.

    Capa 7: ahora hay un paso de auth ANTES del handshake. La mayoría de los
    tests solo necesitan "estar dentro como alguien"; este helper lo resuelve.
    `welcome["you"]["client_id"]` es el usuario (la identidad ya es real).
    """
    await autenticar(ws, user=user, password=password, registrar=registrar)
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
        await autenticar(ws)  # capa 7: la app está cerrada
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
            await autenticar(late)
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
            await autenticar(c)
            init_c = json.loads(await c.recv())
            assert init_c == {
                "type": "init",
                "files": {"main.py": "A edita main", "auth.py": "B edita auth"},
            }


# --- Capa 2: presencia ---


async def test_welcome_lleva_identidad_real(server_port: int) -> None:
    # Capa 7: la identidad ES el usuario autenticado (no anónimo). El welcome
    # la trae derivada del usuario; el cliente no la elige. peers vacío solo.
    async with connect(f"ws://localhost:{server_port}") as a:
        welcome = await handshake(a, user="joaquin")
        yo = welcome["you"]
        assert yo["client_id"] == "joaquin"
        assert yo["name"] == "joaquin"
        assert yo["color"].startswith("#")
        assert yo["path"] is None  # conectado pero todavía no presente
        assert welcome["peers"] == []


async def test_distinct_users_get_distinct_ids(server_port: int) -> None:
    # Dos usuarios distintos => identidades distintas.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        wa = await handshake(a, user="ana")
        wb = await handshake(b, user="beto")
        assert wa["you"]["client_id"] == "ana"
        assert wb["you"]["client_id"] == "beto"


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
            await autenticar(c)
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
        await autenticar(a)
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
            await autenticar(c)
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
            await autenticar(c)
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
            await autenticar(c)
            assert json.loads(await c.recv()) == {"type": "init", "files": {}}


# --- Capa 7: identidad real (login obligatorio) ---


async def test_app_cerrada_sin_login(server_port: int) -> None:
    # Mandar un mensaje de app antes de autenticarse NO entra: auth_error y
    # nunca un init. La app está cerrada.
    async with connect(f"ws://localhost:{server_port}") as ws:
        await ws.send(json.dumps({"type": "update", "path": "x.py", "content": "hola"}))
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "auth_error"


async def test_login_password_incorrecta(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a:
        await autenticar(a, user="ana", password="buena")  # registra ana
    async with connect(f"ws://localhost:{server_port}") as b:
        await b.send(json.dumps({"type": "login", "username": "ana", "password": "mala"}))
        msg = json.loads(await asyncio.wait_for(b.recv(), timeout=2))
        assert msg["type"] == "auth_error"
        # Y se puede reintentar en la MISMA conexión con la buena.
        await b.send(json.dumps({"type": "login", "username": "ana", "password": "buena"}))
        assert json.loads(await asyncio.wait_for(b.recv(), timeout=2))["type"] == "auth_ok"


async def test_registrar_duplicado_falla(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a:
        await autenticar(a, user="ana")
    async with connect(f"ws://localhost:{server_port}") as b:
        await b.send(json.dumps({"type": "register", "username": "ana", "password": "x"}))
        assert json.loads(await asyncio.wait_for(b.recv(), timeout=2))["type"] == "auth_error"


async def test_mismo_usuario_misma_identidad(server_port: int) -> None:
    # Loguearse de nuevo (otra conexión/navegador) devuelve la MISMA identidad.
    async with connect(f"ws://localhost:{server_port}") as a:
        w1 = await handshake(a, user="ana")
    async with connect(f"ws://localhost:{server_port}") as a2:
        w2 = await handshake(a2, user="ana", registrar=False)  # login
    assert w2["you"]["client_id"] == w1["you"]["client_id"] == "ana"
    assert w2["you"]["color"] == w1["you"]["color"]


async def test_session_token_auto_login(server_port: int) -> None:
    # El auth_ok trae un token firmado; presentarlo (session) reloguea sin
    # contraseña. Es lo que hace que recargar no moleste.
    async with connect(f"ws://localhost:{server_port}") as a:
        _, authok = await autenticar(a, user="ana")
        token = authok["token"]
    async with connect(f"ws://localhost:{server_port}") as a2:
        await a2.send(json.dumps({"type": "session", "token": token}))
        ok = json.loads(await asyncio.wait_for(a2.recv(), timeout=2))
        assert ok["type"] == "auth_ok" and ok["username"] == "ana"


async def test_session_token_invalido_se_rechaza(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as ws:
        await ws.send(json.dumps({"type": "session", "token": "falso.dead"}))
        assert json.loads(await asyncio.wait_for(ws.recv(), timeout=2))["type"] == "auth_error"


async def test_ownership_sobrevive_reconexion(server_port: int) -> None:
    # El fix de fondo, ahora con identidad real: ana reclama, "recarga"
    # (se desconecta y vuelve a loguearse) y SIGUE siendo dueña.
    async with connect(f"ws://localhost:{server_port}") as b:
        await handshake(b, user="beto")
        async with connect(f"ws://localhost:{server_port}") as a:
            await handshake(a, user="ana")
            await a.send(json.dumps({"type": "claim", "path": "x.py"}))
            await _drenar_ownership(a)
            assert await _drenar_ownership(b) == {
                "type": "ownership", "owners": {"x.py": "ana"},
            }
        # A se desconectó: B NO recibe un mapa vacío (el ownership no se libera).
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)

        # ana vuelve (login): misma identidad y sigue siendo dueña.
        async with connect(f"ws://localhost:{server_port}") as a2:
            await autenticar(a2, user="ana", registrar=False)
            assert json.loads(await a2.recv())["type"] == "init"
            welcome = json.loads(await a2.recv())
            assert welcome["you"]["client_id"] == "ana"
            own = json.loads(await a2.recv())
            assert own == {"type": "ownership", "owners": {"x.py": "ana"}}
            # Prueba fuerte: beto (no dueño) edita x.py -> tentativo, la
            # propuesta le llega a ana. Solo pasa si ana sigue siendo dueña.
            await b.send(json.dumps({"type": "update", "path": "x.py", "content": "beto intenta"}))
            prop = await recv_tipo(a2, "proposal")
            assert prop["proposal"]["path"] == "x.py"
            assert prop["proposal"]["content"] == "beto intenta"


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
            await autenticar(d)
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


# --- Capa 6: análisis semántico de impacto ---


_MODELS_V1 = "class Usuario:\n    pass\n"
_MODELS_V2 = "class Usuario:\n    def __init__(self):\n        self.activo = True\n"
_AUTH = "from models import Usuario\n\n\ndef login():\n    return Usuario()\n"


async def test_impacto_avisa_al_dueno_del_afectado(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        wa = await handshake(a)
        await handshake(b)
        # A crea models.py (queda dueño).
        await a.send(json.dumps({"type": "update", "path": "models.py", "content": _MODELS_V1}))
        await recv_tipo(b, "update")
        await recv_tipo(a, "ownership")
        await recv_tipo(b, "ownership")
        # B crea auth.py que usa Usuario (queda dueño).
        await b.send(json.dumps({"type": "update", "path": "auth.py", "content": _AUTH}))
        await recv_tipo(a, "update")
        await recv_tipo(a, "ownership")
        await recv_tipo(b, "ownership")

        # A modifica la clase Usuario -> B (dueño de auth.py) debe enterarse solo.
        await a.send(json.dumps({"type": "update", "path": "models.py", "content": _MODELS_V2}))
        aviso = await recv_tipo(b, "impact")
        assert aviso == {
            "type": "impact",
            "source_path": "models.py",
            "author_name": wa["you"]["name"],
            "affected_path": "auth.py",
            "symbols": ["Usuario"],
        }


async def test_no_avisa_si_el_codigo_no_parsea(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "update", "path": "models.py", "content": _MODELS_V1}))
        await recv_tipo(b, "update")
        await recv_tipo(a, "ownership")
        await recv_tipo(b, "ownership")
        await b.send(json.dumps({"type": "update", "path": "auth.py", "content": _AUTH}))
        await recv_tipo(a, "update")
        await recv_tipo(a, "ownership")
        await recv_tipo(b, "ownership")

        # A deja models.py a medio escribir (SyntaxError): NO debe avisar nada.
        await a.send(json.dumps({"type": "update", "path": "models.py", "content": "class Usuario(:\n"}))
        await recv_tipo(b, "update")  # el update sí se difunde igual
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)


async def test_impacto_tambien_al_aprobar_propuesta(server_port: int) -> None:
    # El aviso de impacto también sale por la vía "propuesta aprobada", con el
    # nombre del AUTOR de la propuesta, no del dueño que aprobó.
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b, connect(f"ws://localhost:{server_port}") as c:
        await handshake(a)
        await handshake(b)
        wc = await handshake(c)
        # A dueño de models.py, B dueño de auth.py (usa Usuario).
        await a.send(json.dumps({"type": "update", "path": "models.py", "content": _MODELS_V1}))
        await recv_tipo(b, "update"); await recv_tipo(c, "update")
        await recv_tipo(a, "ownership"); await recv_tipo(b, "ownership"); await recv_tipo(c, "ownership")
        await b.send(json.dumps({"type": "update", "path": "auth.py", "content": _AUTH}))
        await recv_tipo(a, "update"); await recv_tipo(c, "update")
        await recv_tipo(a, "ownership"); await recv_tipo(b, "ownership"); await recv_tipo(c, "ownership")

        # C edita models.py (de A) -> tentativo. A recibe propuesta.
        await c.send(json.dumps({"type": "update", "path": "models.py", "content": _MODELS_V2}))
        prop = await recv_tipo(a, "proposal")
        # A aprueba. El cambio se aplica; B (dueño de auth.py) recibe el impacto
        # atribuido a C (el autor), no a A.
        await a.send(json.dumps({"type": "resolve", "proposal_id": prop["proposal"]["id"], "accept": True}))
        aviso = await recv_tipo(b, "impact")
        assert aviso["source_path"] == "models.py"
        assert aviso["affected_path"] == "auth.py"
        assert aviso["symbols"] == ["Usuario"]
        assert aviso["author_name"] == wc["you"]["name"]


# --- Capa 8: integración con Git (solo lectura) ---


async def test_git_status_en_handshake_y_refresh(tmp_path) -> None:
    # El workspace es un repo git real: tras el handshake llega git_status, y
    # al editar (persiste en el repo) un git_refresh refleja el cambio.
    ws_dir = tmp_path / "workspace"
    srv = SyncServer(storage=DiskStorage(ws_dir), git=GitRepo(ws_dir))
    s = await serve(srv.handle, "localhost", 0)
    port = s.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port}") as c:
            await handshake(c)  # init/welcome/ownership
            gs = await recv_tipo(c, "git_status")
            assert gs["available"] is True
            assert isinstance(gs["branch"], str) and gs["branch"]
            assert gs["changes"] == 0
            assert gs["commits"] == []

            # Editar crea el archivo en el repo -> aparece como sin commitear.
            await c.send(
                json.dumps({"type": "update", "path": "main.py", "content": "x = 1"})
            )
            await asyncio.sleep(0.05)  # dar tiempo a persistir
            await c.send(json.dumps({"type": "git_refresh"}))
            gs2 = await recv_tipo(c, "git_status")
            assert gs2["available"] is True
            assert gs2["changes"] >= 1
    finally:
        s.close()
        await s.wait_closed()


async def test_sin_git_no_se_manda_git_status(server_port: int) -> None:
    # Fixture por defecto: git=None. El handshake NO debe traer git_status
    # (contrato: los tests sin git no cambian su coreografía).
    async with connect(f"ws://localhost:{server_port}") as c:
        await handshake(c)
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(c.recv(), timeout=0.3)


# --- Capa 9: eliminar archivos ---


async def test_borrar_archivo_se_difunde_a_todos(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "update", "path": "x.py", "content": "hola"}))
        await recv_tipo(b, "update")            # B ve el archivo
        await recv_tipo(a, "ownership")          # A queda dueño (al crear)
        await recv_tipo(b, "ownership")

        await a.send(json.dumps({"type": "delete", "path": "x.py"}))
        # Va a TODOS, incluido A.
        assert await recv_tipo(a, "delete") == {"type": "delete", "path": "x.py"}
        assert await recv_tipo(b, "delete") == {"type": "delete", "path": "x.py"}
        # Ownership de x.py liberado: el mapa nuevo no lo tiene.
        assert await recv_tipo(a, "ownership") == {"type": "ownership", "owners": {}}
        # Un cliente nuevo no ve x.py.
        async with connect(f"ws://localhost:{server_port}") as c:
            await autenticar(c)
            assert json.loads(await c.recv()) == {"type": "init", "files": {}}


async def test_no_dueno_no_puede_borrar_archivo_ajeno(server_port: int) -> None:
    async with connect(f"ws://localhost:{server_port}") as a, connect(
        f"ws://localhost:{server_port}"
    ) as b:
        await handshake(a)
        await handshake(b)
        await a.send(json.dumps({"type": "update", "path": "x.py", "content": "de A"}))
        await recv_tipo(b, "update")
        await recv_tipo(a, "ownership")
        await recv_tipo(b, "ownership")

        # B (no dueño) intenta borrar x.py -> ignorado, nadie recibe delete.
        await b.send(json.dumps({"type": "delete", "path": "x.py"}))
        with pytest.raises(asyncio.TimeoutError):
            await asyncio.wait_for(b.recv(), timeout=0.3)
        # Sigue existiendo para un cliente nuevo.
        async with connect(f"ws://localhost:{server_port}") as c:
            await autenticar(c)
            assert json.loads(await c.recv()) == {
                "type": "init", "files": {"x.py": "de A"},
            }


# --- Capa 9b: commit desde la web ---


async def test_commit_desde_la_web(tmp_path) -> None:
    ws_dir = tmp_path / "workspace"
    srv = SyncServer(storage=DiskStorage(ws_dir), git=GitRepo(ws_dir))
    s = await serve(srv.handle, "localhost", 0)
    port = s.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port}") as c:
            await handshake(c, user="ana@team.com")
            await recv_tipo(c, "git_status")
            await c.send(json.dumps({"type": "update", "path": "main.py", "content": "x = 1"}))
            await asyncio.sleep(0.05)
            await c.send(json.dumps({"type": "commit", "message": "primer commit"}))
            res = await recv_tipo(c, "git_result")
            assert res["ok"] is True
            gs = await recv_tipo(c, "git_status")
            assert gs["changes"] == 0
            assert "primer commit" in gs["commits"][0]
    finally:
        s.close()
        await s.wait_closed()


async def test_commit_sin_mensaje_falla(tmp_path) -> None:
    ws_dir = tmp_path / "workspace"
    srv = SyncServer(storage=DiskStorage(ws_dir), git=GitRepo(ws_dir))
    s = await serve(srv.handle, "localhost", 0)
    port = s.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port}") as c:
            await handshake(c)
            await recv_tipo(c, "git_status")
            await c.send(json.dumps({"type": "commit", "message": "   "}))
            res = await recv_tipo(c, "git_result")
            assert res["ok"] is False
    finally:
        s.close()
        await s.wait_closed()


# --- Capa 10: clone / push (escalón mínimo) ---

import subprocess as _sp


def _remoto_bare(tmp_path):
    """Repo bare local con un commit = 'el repo del equipo' (sin red)."""
    remoto = tmp_path / "equipo.git"
    _sp.run(["git", "init", "--bare", "-q", str(remoto)], check=True)
    seed = tmp_path / "seed"
    _sp.run(["git", "clone", "-q", str(remoto), str(seed)], check=True)
    (seed / "hola.py").write_text("print('del remoto')\n", encoding="utf-8")
    _sp.run(["git", "-C", str(seed), "add", "-A"], check=True)
    _sp.run(["git", "-C", str(seed), "-c", "user.email=a@b", "-c",
             "user.name=a", "commit", "-q", "-m", "inicial"], check=True)
    _sp.run(["git", "-C", str(seed), "push", "-q", "origin", "HEAD"], check=True)
    return remoto


async def test_clone_reemplaza_y_reinicia_a_todos(tmp_path) -> None:
    remoto = _remoto_bare(tmp_path)
    ws = tmp_path / "ws"
    srv = SyncServer(storage=DiskStorage(ws), git=GitRepo(ws))
    s = await serve(srv.handle, "localhost", 0)
    port = s.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port}") as a, connect(
            f"ws://localhost:{port}"
        ) as b:
            await handshake(a); await recv_tipo(a, "git_status")
            await handshake(b); await recv_tipo(b, "git_status")
            # A deja basura vieja en el workspace.
            await a.send(json.dumps({"type": "update", "path": "viejo.py", "content": "basura"}))
            await recv_tipo(b, "update")

            await a.send(json.dumps({
                "type": "clone", "url": str(remoto),
                "username": "u", "token": "SECRETO"}))

            # El re-init llega ANTES que el git_result; hay que leerlo primero
            # o recv_tipo("git_result") se comería el init.
            for cl in (a, b):
                init = await recv_tipo(cl, "init")
                assert init["files"] == {"hola.py": "print('del remoto')\n"}
            res = await recv_tipo(a, "git_result")
            assert res["ok"] is True, res
            # Un cliente nuevo también ve solo lo clonado.
            async with connect(f"ws://localhost:{port}") as c:
                await autenticar(c)
                assert json.loads(await c.recv()) == {
                    "type": "init", "files": {"hola.py": "print('del remoto')\n"}}
    finally:
        s.close(); await s.wait_closed()


async def test_clone_que_falla_no_destruye(tmp_path) -> None:
    ws = tmp_path / "ws"
    srv = SyncServer(storage=DiskStorage(ws), git=GitRepo(ws))
    s = await serve(srv.handle, "localhost", 0)
    port = s.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port}") as a:
            await handshake(a); await recv_tipo(a, "git_status")
            await a.send(json.dumps({"type": "update", "path": "importante.py", "content": "no borrar"}))
            await asyncio.sleep(0.05)
            await a.send(json.dumps({
                "type": "clone", "url": str(tmp_path / "no-existe.git"),
                "username": "u", "token": "t"}))
            res = await recv_tipo(a, "git_result")
            assert res["ok"] is False
            async with connect(f"ws://localhost:{port}") as c:
                await autenticar(c)
                assert json.loads(await c.recv()) == {
                    "type": "init", "files": {"importante.py": "no borrar"}}
    finally:
        s.close(); await s.wait_closed()


async def test_push_desde_la_web(tmp_path) -> None:
    remoto = _remoto_bare(tmp_path)
    ws = tmp_path / "ws"
    srv = SyncServer(storage=DiskStorage(ws), git=GitRepo(ws))
    s = await serve(srv.handle, "localhost", 0)
    port = s.sockets[0].getsockname()[1]
    try:
        async with connect(f"ws://localhost:{port}") as a:
            await handshake(a, user="ana@team.com"); await recv_tipo(a, "git_status")
            await a.send(json.dumps({
                "type": "clone", "url": str(remoto),
                "username": "u", "token": "t"}))
            await recv_tipo(a, "init")  # re-init del clone, antes del result
            assert (await recv_tipo(a, "git_result"))["ok"] is True
            await a.send(json.dumps({"type": "update", "path": "nuevo.py", "content": "x = 1"}))
            await asyncio.sleep(0.05)
            await a.send(json.dumps({"type": "commit", "message": "agrega nuevo"}))
            assert (await recv_tipo(a, "git_result"))["ok"] is True
            await a.send(json.dumps({"type": "push", "username": "u", "token": "t", "url": ""}))
            assert (await recv_tipo(a, "git_result"))["ok"] is True
        verif = tmp_path / "verif"
        _sp.run(["git", "clone", "-q", str(remoto), str(verif)], check=True)
        assert (verif / "nuevo.py").exists()
    finally:
        s.close(); await s.wait_closed()
