"""Tests de las mejoras de robustez a nivel sistema (no features).

Cubren lo que la auditoría había DIFERIDO y ahora se cerró:

- M1: validación de path en la frontera del MENSAJE (no solo en disco) —
  un path peligroso no entra al estado en memoria ni se difunde.
- M1 seguridad: expiración de tokens de sesión.
- B-varios: escrituras JSON atómicas (no quedan `.tmp` ni archivos a
  medias) y guard de `aplicar_rename` con argumento degenerado.
- C/A: el lock de estado por equipo no rompe convergencia ni deadlockea.

Los tests de integración levantan un server real (mismo patrón que
test_sync) pero son self-contained: un solo cliente por test, server
fresco por test => sin coordinación de equipo entre tests.
"""

import asyncio
import json
import time

import pytest
import pytest_asyncio
from websockets.asyncio.client import connect
from websockets.asyncio.server import serve

from orux.adapters.json import JsonUserStore
from orux.analysis.rename import aplicar_rename
from orux.identity import crear_token, usuario_de_token
from orux.identity.store import UserStore
from orux.server.sync import SyncServer
from orux.state import DiskStorage, path_seguro

# --- Unitarios puros: path_seguro -----------------------------------------


@pytest.mark.parametrize(
    "malo",
    [
        "",                 # vacío
        "../etc/passwd",    # escape de directorio
        "a/../../x",        # escape enterrado
        "/etc/shadow",      # absoluto POSIX
        "C:\\Windows",      # absoluto Windows + backslash
        "a\\b",             # backslash (evasión/ambigüedad)
        "a//b",             # segmento vacío
        "a/./b",            # segmento "."
        "a/..",             # termina en ".."
        "x\x00.py",         # NUL
        "linea\nrota.py",   # control char
        ".",
        "..",
        None,               # ni siquiera un str
        123,
        # Sprint de pulido pre-mercado: caracteres ruidosos que el path_seguro
        # viejo dejaba pasar y aparecían como archivos absurdos en el árbol.
        "archivo<script>.py",     # HTML/inyección visual
        "a>b.py", "a|b.py", "a?b.py", "a*b.py", 'a"b.py',
        "linea\x7frota.py",       # DEL (chequeo era < 0x20, pasaba)
        "a​b.py",            # zero-width space
        "auth‮py.txt",       # bidi RTL override (suplantación)
        "x﻿.py",             # BOM dentro del path
        " a.py", "a.py ",         # espacios al borde de segmento
        "src/ a.py", "src/a.py ", # idem dentro de subcarpeta
        "a" * 81 + ".py",         # segmento muy largo
        "x/" * 17 + "y.py",       # profundidad excesiva
        "a" * 201,                # path total muy largo (era 1024)
        "CON.txt", "prn.py", "AUX.go", "Nul.tsx",  # reservados Windows
        "src/com1.py",            # reservado en subcarpeta
        "C:/Users",               # absoluto Windows sin barra inversa
    ],
)
def test_path_seguro_rechaza_lo_peligroso(malo):
    assert path_seguro(malo) is False


# --- Anti-abuso del registro: throttle por IP -----------------------------


def test_throttle_registro_corta_la_creacion_masiva(monkeypatch):
    """Una IP puede registrar hasta el tope; el intento siguiente se rechaza.
    Sin esto el registro público no tiene techo por IP."""
    monkeypatch.setenv("ORUX_REGISTRO_MAX_POR_IP", "3")
    server = SyncServer()
    assert server._throttle_registro("1.2.3.4") is True
    assert server._throttle_registro("1.2.3.4") is True
    assert server._throttle_registro("1.2.3.4") is True
    assert server._throttle_registro("1.2.3.4") is False  # 4to: superó el tope


def test_throttle_registro_es_por_ip(monkeypatch):
    """El cupo de una IP no afecta a otra — una NAT agotada y un bot en otra
    IP no comparten límite."""
    monkeypatch.setenv("ORUX_REGISTRO_MAX_POR_IP", "2")
    server = SyncServer()
    assert server._throttle_registro("ip-a") is True
    assert server._throttle_registro("ip-a") is True
    assert server._throttle_registro("ip-a") is False  # ip-a agotada
    assert server._throttle_registro("ip-b") is True   # ip-b: cupo propio
    assert server._throttle_registro("ip-b") is True
    assert server._throttle_registro("ip-b") is False


def test_ip_cliente_prefiere_x_forwarded_for():
    """Detrás de Caddy la IP real va en X-Forwarded-For; sin ese header
    (dev/tests) se cae a remote_address."""
    from orux.server.sync import _ip_cliente

    class _Req:
        headers = {"X-Forwarded-For": "203.0.113.7, 10.0.0.1"}

    class _ConProxy:
        request = _Req()
        remote_address = ("172.18.0.5", 40000)

    class _SinProxy:
        request = None
        remote_address = ("127.0.0.1", 51000)

    assert _ip_cliente(_ConProxy()) == "203.0.113.7"
    assert _ip_cliente(_SinProxy()) == "127.0.0.1"


def test_ip_cliente_ignora_xff_de_origen_no_confiable():
    """BACKEND-AUDIT M-04: si la conexión TCP viene de una IP pública
    (atacante directo al contenedor saltando a Caddy), su XFF NO se
    honra — vuelve la IP del socket. Sin esta defensa, el rate-limit
    de login era trivial de evadir rotando XFF."""
    from orux.server.sync import _ip_cliente

    class _Req:
        headers = {"X-Forwarded-For": "1.2.3.4"}

    class _Atacante:
        request = _Req()
        # IP pública (ej. otro pod expuesto, port-forward olvidado).
        remote_address = ("203.0.113.99", 40000)

    # Debe ignorar el XFF y reportar la IP real del socket.
    assert _ip_cliente(_Atacante()) == "203.0.113.99"


def test_ip_proxy_confiable_basico():
    """Helper compartido: privada/loopback = True; pública/basura = False."""
    from orux._net import ip_proxy_confiable

    # Privadas (Docker bridge, k8s, LAN).
    assert ip_proxy_confiable("172.18.0.5") is True
    assert ip_proxy_confiable("10.244.0.7") is True
    assert ip_proxy_confiable("192.168.1.10") is True
    # Loopback.
    assert ip_proxy_confiable("127.0.0.1") is True
    assert ip_proxy_confiable("::1") is True
    # IPv6 ULA.
    assert ip_proxy_confiable("fd00::1") is True
    # Públicas — NO confiar.
    assert ip_proxy_confiable("8.8.8.8") is False
    assert ip_proxy_confiable("203.0.113.5") is False
    # Basura — NO confiar y NO explotar.
    assert ip_proxy_confiable("") is False
    assert ip_proxy_confiable("unknown") is False
    assert ip_proxy_confiable(None) is False
    assert ip_proxy_confiable("not-an-ip") is False


def test_throttle_login_corta_la_fuerza_bruta(monkeypatch):
    """Una IP puede intentar login hasta el tope; el siguiente se rechaza.
    El backoff por-conexión se reinicia al reconectar — este tope no."""
    monkeypatch.setenv("ORUX_LOGIN_MAX_POR_IP", "3")
    server = SyncServer()
    assert server._throttle_login("9.9.9.9") is True
    assert server._throttle_login("9.9.9.9") is True
    assert server._throttle_login("9.9.9.9") is True
    assert server._throttle_login("9.9.9.9") is False


def test_throttle_login_y_registro_no_comparten_cupo(monkeypatch):
    """Login y registro tienen buckets separados — agotar uno no afecta al
    otro (acciones distintas, con ritmos legítimos distintos)."""
    monkeypatch.setenv("ORUX_LOGIN_MAX_POR_IP", "1")
    monkeypatch.setenv("ORUX_REGISTRO_MAX_POR_IP", "1")
    server = SyncServer()
    assert server._throttle_login("ip-x") is True
    assert server._throttle_login("ip-x") is False    # login agotado
    assert server._throttle_registro("ip-x") is True  # registro intacto
    assert server._throttle_registro("ip-x") is False


@pytest.mark.parametrize(
    "bueno",
    ["a.py", "src/auth.py", "a/b/c/d.ts", "Carpeta Con Espacios/x.go",
     "._oculto_pero_valido.py", "a..b.py",
     # Acentos y emoji en nombre de carpeta — son válidos (queremos
     # "café/main.py" del dev hispanohablante; el filesystem y git lo
     # soportan limpio si todos están en NFC).
     "café/main.py", "música/x.go"],
)
def test_path_seguro_acepta_paths_normales(bueno):
    assert path_seguro(bueno) is True


# --- Unitarios puros: expiración de tokens --------------------------------


def test_token_con_ttl_valido_dentro_de_ventana():
    t = crear_token("ana", "secreto", ttl_seg=3600)
    assert usuario_de_token(t, "secreto") == "ana"


def test_token_expirado_se_rechaza():
    # ttl negativo => exp en el pasado: ya caducó.
    t = crear_token("ana", "secreto", ttl_seg=-1)
    assert usuario_de_token(t, "secreto") is None


def test_token_legacy_sin_exp_rechazado_por_default(monkeypatch):
    # AUDITORIA-SEGURIDAD 2026-05-25 A-HTTP-02: tokens sin exp ya NO se
    # aceptan por default (ventana de sesiones eternas eliminada).
    monkeypatch.delenv("ORUX_ALLOW_NONEXPIRING_TOKENS", raising=False)
    t = crear_token("ana", "secreto")  # sin ttl
    assert usuario_de_token(t, "secreto") is None
    assert usuario_de_token(
        crear_token("ana", "secreto", ttl_seg=0), "secreto"
    ) is None


def test_token_legacy_sin_exp_aceptado_con_flag(monkeypatch):
    # El opt-out explícito existe para entornos en migración: con el flag
    # seteado, los tokens sin exp siguen valiendo (con warning).
    monkeypatch.setenv("ORUX_ALLOW_NONEXPIRING_TOKENS", "1")
    t = crear_token("ana", "secreto")
    assert usuario_de_token(t, "secreto") == "ana"


def test_ttl_chico_se_clampa_a_minimo():
    # AUDITORIA-SEGURIDAD 2026-05-25 A-HTTP-02: ttl < 1h se clampea a 3600s.
    # Un caller mal configurado no puede emitir un token de 10s que en la
    # práctica es eterno por la latencia de chequeo.
    import json
    import base64
    t = crear_token("ana", "secreto", ttl_seg=1)
    # Decode del payload para asegurar que el exp emitido refleja el clamp.
    payload_b64, _ = t.split(".", 1)
    payload = json.loads(
        base64.urlsafe_b64decode(payload_b64 + "=" * (-len(payload_b64) % 4))
    )
    import time
    assert payload["exp"] >= int(time.time()) + 3500


def test_token_exp_corrupto_es_invalido_fail_closed():
    # Un exp no numérico no debe interpretarse como "sin expiración".
    import base64

    payload = base64.urlsafe_b64encode(
        json.dumps({"user": "ana", "exp": "pronto"}).encode()
    ).decode().rstrip("=")
    import hmac
    from hashlib import sha256

    firma = hmac.new(b"secreto", payload.encode(), sha256).hexdigest()
    assert usuario_de_token(f"{payload}.{firma}", "secreto") is None


def test_token_firma_sigue_protegiendo_con_exp():
    t = crear_token("ana", "secreto", ttl_seg=3600)
    assert usuario_de_token(t, "otro-secreto") is None


# --- Unitarios: escrituras atómicas y guard de rename ---------------------


def test_diskstorage_guardar_no_deja_tmp(tmp_path):
    s = DiskStorage(tmp_path)
    s.guardar("src/a.py", "x = 1")
    assert (tmp_path / "src" / "a.py").read_text() == "x = 1"
    # Ningún temporal sobreviviente tras un guardado exitoso.
    assert not list(tmp_path.rglob("*.tmp"))


def test_diskstorage_cargar_ignora_tmp_de_crash(tmp_path):
    # Simula un crash duro: quedó un .tmp a medias junto al archivo bueno.
    (tmp_path / "real.py").write_text("ok")
    (tmp_path / "real.py.1234.tmp").write_text("a-medias")
    cargado = DiskStorage(tmp_path).cargar()
    assert cargado == {"real.py": "ok"}


async def test_userstore_guardar_es_atomico_y_relee(tmp_path):
    ruta = tmp_path / "users.json"
    s = JsonUserStore(ruta)
    await s.registrar("Joaquin", "passw0rd")
    assert not list(tmp_path.glob("*.tmp"))
    # Reabrir desde disco => el usuario está (no se perdió, no truncado).
    assert await JsonUserStore(ruta).verificar("joaquin", "passw0rd") is True


def test_aplicar_rename_guard_argumento_vacio():
    src = "self.x = obj.y.z\n"
    # viejo vacío: NO debe convertir el patrón en `\.\b` y pisar cada punto.
    assert aplicar_rename(src, "", "nuevo") == src
    assert aplicar_rename(src, "x", "") == src


# --- Integración: el server con las mejoras puestas -----------------------


@pytest_asyncio.fixture
async def srv(tmp_path):
    """SyncServer real con disco (para ver si un path malo tocó el disco)."""
    s = SyncServer(
        storage=DiskStorage(tmp_path),
        users=UserStore(),
        ownership=None,
    )
    ws = await serve(s.handle, "localhost", 0)
    port = ws.sockets[0].getsockname()[1]
    try:
        yield s, port, tmp_path
    finally:
        ws.close()
        await ws.wait_closed()


async def _entrar(ws, user="dev"):
    """auth + crear equipo + consumir handshake. Un cliente, server fresco."""
    await ws.send(json.dumps(
        {"type": "register", "username": user, "password": "passw0rd"}))
    assert json.loads(await ws.recv())["type"] == "auth_ok"
    assert json.loads(await ws.recv())["type"] == "lobby"
    await ws.send(json.dumps({"type": "create_team", "nombre": "eq"}))
    assert json.loads(await ws.recv())["type"] == "team_ready"
    for esperado in ("init", "welcome", "ownership", "admin_info"):
        assert json.loads(await ws.recv())["type"] == esperado


async def test_path_inseguro_no_entra_al_estado_ni_tumba_la_conexion(srv):
    s, port, root = srv
    async with connect(f"ws://localhost:{port}") as ws:
        await _entrar(ws)
        # Update con path de escape: NO debe difundirse ni persistirse.
        await ws.send(json.dumps(
            {"type": "update", "path": "../evil.py", "content": "PWN"}))
        # Y la conexión sigue viva: un update legítimo después funciona.
        await ws.send(json.dumps(
            {"type": "update", "path": "bueno.py", "content": "ok"}))
        # El server difunde el ownership del archivo creado legítimo: eso
        # confirma que procesó el 2º mensaje (no murió con el 1º).
        msg = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        assert msg["type"] == "ownership"
        assert "bueno.py" in msg["owners"]

    # El estado del equipo no tiene el path malicioso (ni memoria ni disco).
    rt = next(iter(s._runtimes.values()))
    snap = rt.workspace.snapshot()
    assert "../evil.py" not in snap and "bueno.py" in snap
    assert not (root / "evil.py").exists()
    # Tampoco quedó como ownership/fantasma.
    assert "../evil.py" not in rt.ownership.snapshot()


async def test_lock_de_estado_no_deadlockea_ni_pierde_convergencia(srv):
    """Smoke del lock por equipo: dos clientes editando en paralelo
    convergen y nadie se cuelga (si el lock deadlockeara, esto colgaría
    hasta el timeout)."""
    s, port, _ = srv
    async with connect(f"ws://localhost:{port}") as a:
        await _entrar(a, user="ana")
        # 2º cliente: se une por invitación del admin (a).
        async with connect(f"ws://localhost:{port}") as b:
            await b.send(json.dumps(
                {"type": "register", "username": "bb", "password": "passw0rd"}))
            assert json.loads(await b.recv())["type"] == "auth_ok"
            assert json.loads(await b.recv())["type"] == "lobby"
            await a.send(json.dumps({"type": "create_invite"}))
            ic = None
            while ic is None:
                m = json.loads(await asyncio.wait_for(a.recv(), timeout=2))
                if m["type"] == "invite_created":
                    ic = m
            await b.send(json.dumps(
                {"type": "redeem_invite", "code": ic["code"]}))
            assert json.loads(await b.recv())["type"] == "team_ready"
            for _ in range(4):
                await b.recv()  # init/welcome/ownership/admin_info

            # a crea f1 (queda dueño), b crea f2 (queda dueño): dos
            # read-modify-write concurrentes que el lock serializa.
            await asyncio.gather(
                a.send(json.dumps(
                    {"type": "update", "path": "f1.py", "content": "1"})),
                b.send(json.dumps(
                    {"type": "update", "path": "f2.py", "content": "2"})),
            )
            await asyncio.sleep(0.2)

    rt = next(iter(s._runtimes.values()))
    snap = rt.workspace.snapshot()
    assert snap.get("f1.py") == "1" and snap.get("f2.py") == "2"
    own = rt.ownership.snapshot()
    # El claim del creador ya NO corre tras un await sin protección:
    # ambos archivos quedan con dueño (la ventana A2 está cerrada).
    assert own.get("f1.py") == "ana" and own.get("f2.py") == "bb"


async def test_auth_backoff_no_rompe_el_login_correcto(srv):
    """El throttle castiga el fallo, no al usuario que acierta luego."""
    s, port, _ = srv
    async with connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(
            {"type": "register", "username": "neo", "password": "passw0rd"}))
        assert json.loads(await ws.recv())["type"] == "auth_ok"
    # Nueva conexión: una contraseña mala (recibe auth_error al instante),
    # y el login correcto después sigue funcionando.
    async with connect(f"ws://localhost:{port}") as ws:
        await ws.send(json.dumps(
            {"type": "login", "username": "neo", "password": "MALpwdXX"}))
        t0 = time.monotonic()
        err = json.loads(await asyncio.wait_for(ws.recv(), timeout=2))
        # El error llega rápido (el backoff es DESPUÉS de enviarlo).
        assert err["type"] == "auth_error"
        assert time.monotonic() - t0 < 1.0
        await ws.send(json.dumps(
            {"type": "login", "username": "neo", "password": "passw0rd"}))
        ok = json.loads(await asyncio.wait_for(ws.recv(), timeout=3))
        assert ok["type"] == "auth_ok"
