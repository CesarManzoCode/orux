"""Capa 17 paso 1: el núcleo del cliente LSP, probado SIN un server real.

Disciplina del proyecto (igual que Postgres/tree-sitter): el transporte es
abstracto, así la lógica —framing JSON-RPC, handshake, casar respuesta por
id, drenar lo ajeno, degradar si el stream muere— se verifica 100% en
sandbox contra un server FALSO en memoria. El subproceso pyright real es el
único I/O y se valida en el VPS.
"""

from __future__ import annotations

import json

import pytest

import re

from laidea.analysis import impacto, motivos
from laidea.analysis.modelo import cambios_que_importan_modelo
from laidea.analysis.lsp import (
    ClienteLSP,
    ErrorLSP,
    SesionLSP,
    arrancar_pyright,
    _leer_mensaje,
    enmarcar,
    path_a_uri,
    paths_que_referencian,
    simbolos_de_pyright,
    uri_a_path,
)


class _ServidorFalso:
    """Transporte que ADEMÁS actúa de server LSP: al recibir un request
    encola su respuesta para que el cliente la lea. Reactivo => sin hilos.
    `guion` mapea método -> result. Puede inyectar notificaciones espontáneas
    (diagnósticos) antes de responder, para probar que se drenan."""

    def __init__(self, guion: dict, ruido: bool = False) -> None:
        self.guion = guion
        self.ruido = ruido
        self._in = b""
        self._out = b""
        self.recibidos: list[dict] = []
        self.cerrado = False

    # --- lado server: parsea lo que el cliente escribe y responde ---------
    def escribir(self, datos: bytes) -> None:
        self._in += datos
        while True:
            msg = self._consumir()
            if msg is None:
                return
            self.recibidos.append(msg)
            if "id" not in msg:
                continue  # notificación: el server no responde
            if self.ruido:
                # diagnóstico espontáneo ANTES de la respuesta real
                self._out += enmarcar(
                    {
                        "jsonrpc": "2.0",
                        "method": "textDocument/publishDiagnostics",
                        "params": {"uri": "x", "diagnostics": []},
                    }
                )
            metodo = msg.get("method")
            if metodo in self.guion:
                self._out += enmarcar(
                    {"jsonrpc": "2.0", "id": msg["id"],
                     "result": self.guion[metodo]}
                )
            else:
                self._out += enmarcar(
                    {"jsonrpc": "2.0", "id": msg["id"],
                     "error": {"code": -32601, "message": "sin guion"}}
                )

    def _consumir(self) -> dict | None:
        if b"\r\n\r\n" not in self._in:
            return None
        cab, _, resto = self._in.partition(b"\r\n\r\n")
        largo = 0
        for ln in cab.split(b"\r\n"):
            if ln.lower().startswith(b"content-length:"):
                largo = int(ln.split(b":", 1)[1].strip())
        if len(resto) < largo:
            return None
        cuerpo, self._in = resto[:largo], resto[largo:]
        return json.loads(cuerpo.decode("utf-8"))

    # --- lado cliente: le entrega lo encolado ----------------------------
    def leer(self, n: int) -> bytes:
        if self.cerrado:
            return b""
        trozo, self._out = self._out[:n], self._out[n:]
        return trozo


def test_enmarcar_y_leer_son_inversos() -> None:
    msg = {"jsonrpc": "2.0", "id": 1, "method": "ping", "params": {"a": 1}}
    t = _ServidorFalso({})
    t._out = enmarcar(msg)
    assert _leer_mensaje(t) == msg


def test_handshake_y_request_casa_por_id() -> None:
    srv = _ServidorFalso({"initialize": {"capabilities": {}},
                          "textDocument/documentSymbol": [{"name": "f"}]})
    c = ClienteLSP(srv)
    c.iniciar("file:///ws")
    assert c.document_symbol("file:///a.py") == [{"name": "f"}]
    # el server vio: initialize, initialized(notif), documentSymbol
    metodos = [m.get("method") for m in srv.recibidos]
    assert metodos == ["initialize", "initialized",
                        "textDocument/documentSymbol"]


def test_notificaciones_no_esperan_respuesta_ni_desincronizan() -> None:
    srv = _ServidorFalso({"initialize": {}, "textDocument/references": []})
    c = ClienteLSP(srv)
    c.iniciar("file:///ws")
    c.abrir("file:///a.py", "x = 1")            # notif
    c.cambiar("file:///a.py", "x = 2", 2)       # notif
    assert c.referencias("file:///a.py", 0, 0) == []  # sigue alineado


def test_drena_ruido_del_server_antes_de_la_respuesta() -> None:
    srv = _ServidorFalso({"initialize": {}, "textDocument/documentSymbol":
                          [{"name": "g"}]}, ruido=True)
    c = ClienteLSP(srv)
    c.iniciar("file:///ws")
    # Aunque el server mande diagnósticos espontáneos, casa la respuesta.
    assert c.document_symbol("file:///a.py") == [{"name": "g"}]


def test_error_jsonrpc_se_vuelve_ErrorLSP() -> None:
    c = ClienteLSP(_ServidorFalso({"initialize": {}}))
    c.iniciar("file:///ws")
    with pytest.raises(ErrorLSP):
        c.document_symbol("file:///a.py")  # método sin guion => error


def test_stream_muerto_degrada_con_ErrorLSP() -> None:
    srv = _ServidorFalso({"initialize": {}})
    c = ClienteLSP(srv)
    c.iniciar("file:///ws")
    srv.cerrado = True  # el subproceso pyright murió
    with pytest.raises(ErrorLSP):
        c.document_symbol("file:///a.py")


# --- Mapeo pyright -> modelo (puro; payloads con forma real de pyright) ---


def test_uri_path_ida_y_vuelta_y_fuera_de_workspace() -> None:
    u = path_a_uri("/data/ws/eq1", "sub/models.py")
    assert u == "file:///data/ws/eq1/sub/models.py"
    assert uri_a_path("/data/ws/eq1", u) == "sub/models.py"
    # stdlib / dependencia: fuera del workspace => None (no hay a quién avisar)
    assert uri_a_path("/data/ws/eq1", "file:///usr/lib/python3/os.py") is None


def test_simbolos_de_pyright_funcion_clase_tipo() -> None:
    fuente = (
        "def saluda(a, b):\n"
        "    return a + b\n"
        "class Caja:\n"
        "    def __init__(self, x):\n"
        "        self.x = x\n"
        "    def abrir(self):\n"
        "        pass\n"
        "    def _interno(self):\n"
        "        pass\n"
    )
    doc = [
        {"name": "saluda", "kind": 12, "detail": "(a, b)",
         "range": {"start": {"line": 0, "character": 0},
                   "end": {"line": 1, "character": 16}}},
        {"name": "Caja", "kind": 5,
         "range": {"start": {"line": 2, "character": 0},
                   "end": {"line": 8, "character": 12}},
         "children": [
             {"name": "__init__", "kind": 9, "detail": "(self, x)"},
             {"name": "abrir", "kind": 6},
             {"name": "_interno", "kind": 6},
         ]},
        {"name": "Color", "kind": 10,
         "range": {"start": {"line": 9, "character": 0},
                   "end": {"line": 9, "character": 5}}},
    ]
    syms = simbolos_de_pyright(doc, fuente)
    assert syms["saluda"].tipo == "funcion"
    assert syms["saluda"].firma == "(a, b)"
    assert syms["saluda"].detallado is True
    assert syms["saluda"].fuente.startswith("def saluda(a, b):")
    assert syms["Caja"].tipo == "clase"
    assert syms["Caja"].init == "(self, x)"
    assert syms["Caja"].superficie == frozenset({"abrir()"})  # sin _interno
    assert syms["Color"].tipo == "tipo"


def test_simbolos_de_pyright_alimenta_el_modelo_fino() -> None:
    # El valor real: con pyright, cambiar la firma avisa; cambiar el cuerpo
    # no. Mismo modelo de capa 16, ahora con datos type-aware.
    rng = {"start": {"line": 0, "character": 0},
           "end": {"line": 1, "character": 12}}
    antes = simbolos_de_pyright(
        [{"name": "f", "kind": 12, "detail": "(a)", "range": rng}],
        "def f(a):\n    return 1\n",
    )
    # Si la firma cambia, el fuente también (texto real coherente).
    firma = simbolos_de_pyright(
        [{"name": "f", "kind": 12, "detail": "(a, b)", "range": rng}],
        "def f(a, b):\n    return 1\n",
    )
    cuerpo = simbolos_de_pyright(
        [{"name": "f", "kind": 12, "detail": "(a)", "range": rng}],
        "def f(a):\n    return 2\n",
    )
    assert cambios_que_importan_modelo(antes, firma) == {
        "f": "cambió la firma de «f»: (a) → (a, b) — revisá las llamadas"
    }
    assert cambios_que_importan_modelo(antes, cuerpo) == {}  # cuerpo: silencio


def test_paths_que_referencian_resolucion_real() -> None:
    raiz = "/data/ws/eq1"
    refs = [
        {"uri": path_a_uri(raiz, "auth.py"),
         "range": {"start": {"line": 3, "character": 4}}},
        {"uri": path_a_uri(raiz, "billing.py"), "range": {}},
        {"uri": path_a_uri(raiz, "models.py"), "range": {}},  # el propio
        {"uri": "file:///usr/lib/python3/typing.py", "range": {}},  # stdlib
    ]
    assert paths_que_referencian(refs, raiz, "models.py") == {
        "auth.py", "billing.py"
    }
    assert paths_que_referencian(None, raiz, "models.py") == set()


# --- Integración end-to-end con un pyright FALSO (sesión + dispatcher) ----


class _PyrightFalso:
    """Server LSP falso con estado: recuerda el texto de cada uri (didOpen/
    didChange) y, en documentSymbol, lo "parsea" (mínimo: `def f(sig):`)
    como lo haría pyright. references devuelve un set fijo de ubicaciones =
    resolución cross-módulo simulada. Sirve para probar TODA la cadena
    sesión->dispatcher sin un pyright real."""

    _DEF = re.compile(r"^def ([A-Za-z_]\w*)\(([^)]*)\):", re.M)

    def __init__(self, refs_uris: list[str]) -> None:
        self._refs = refs_uris
        self._txt: dict[str, str] = {}
        self._in = b""
        self._out = b""
        self.cerrado = False

    def escribir(self, datos: bytes) -> None:
        self._in += datos
        while b"\r\n\r\n" in self._in:
            cab, _, resto = self._in.partition(b"\r\n\r\n")
            n = 0
            for ln in cab.split(b"\r\n"):
                if ln.lower().startswith(b"content-length:"):
                    n = int(ln.split(b":", 1)[1].strip())
            if len(resto) < n:
                break
            cuerpo, self._in = resto[:n], resto[n:]
            self._despachar(json.loads(cuerpo.decode()))

    def _responder(self, mid, result) -> None:
        self._out += enmarcar({"jsonrpc": "2.0", "id": mid,
                               "result": result})

    def _despachar(self, msg: dict) -> None:
        m = msg.get("method")
        p = msg.get("params", {})
        if m == "initialize":
            self._responder(msg["id"], {"capabilities": {}})
        elif m == "textDocument/didOpen":
            td = p["textDocument"]
            self._txt[td["uri"]] = td["text"]
        elif m == "textDocument/didChange":
            self._txt[p["textDocument"]["uri"]] = p["contentChanges"][0]["text"]
        elif m == "textDocument/documentSymbol":
            uri = p["textDocument"]["uri"]
            texto = self._txt.get(uri, "")
            syms = []
            for mm in self._DEF.finditer(texto):
                nom, sig = mm.group(1), mm.group(2)
                ln = texto[: mm.start()].count("\n")
                syms.append({
                    "name": nom, "kind": 12, "detail": f"({sig})",
                    "range": {"start": {"line": ln, "character": 0},
                              "end": {"line": ln, "character": mm.end() - mm.start()}},
                    "selectionRange": {"start": {"line": ln, "character": 4},
                                       "end": {"line": ln, "character": 5}},
                })
            self._responder(msg["id"], syms)
        elif m == "textDocument/references":
            self._responder(msg["id"], [{"uri": u, "range": {}}
                                        for u in self._refs])
        elif m == "shutdown":
            self._responder(msg["id"], None)

    def leer(self, n: int) -> bytes:
        if self.cerrado:
            return b""
        t, self._out = self._out[:n], self._out[n:]
        return t


def _sesion(raiz: str, refs_paths: list[str]) -> SesionLSP:
    srv = _PyrightFalso([path_a_uri(raiz, p) for p in refs_paths])
    c = ClienteLSP(srv)
    c.iniciar(path_a_uri(raiz, ""))
    return SesionLSP(c, raiz)


def test_dispatcher_usa_fan_out_real_de_pyright() -> None:
    raiz = "/data/ws/eq1"
    ws = {
        "models.py": "def crea(a):\n    return a\n",
        "auth.py": "x = 1\n",       # NO contiene el token 'crea'
        "billing.py": "y = 2\n",    # NO contiene el token 'crea'
    }
    # pyright dice (resolución real) que crea() se usa en auth.py y billing.py
    # aunque el token no aparezca: el token-scan de capa 16 NO los hallaría.
    ses = _sesion(raiz, ["auth.py", "billing.py", "models.py"])
    viejo = ws["models.py"]
    nuevo = "def crea(a, b):\n    return a\n"   # cambió la firma

    assert motivos("models.py", viejo, nuevo, ses) == {
        "crea": "cambió la firma de «crea»: (a) → (a, b) — revisá las llamadas"
    }
    af = impacto({**ws, "models.py": nuevo}, "models.py", viejo, nuevo, ses)
    assert af == {"crea": ["auth.py", "billing.py"]}  # fan-out real, no token


def test_sesion_lsp_caida_degrada_a_capa16() -> None:
    raiz = "/data/ws/eq1"
    viejo = "def crea(a):\n    return a\n"
    nuevo = "def crea(a, b):\n    return a\n"
    ws = {"models.py": nuevo, "auth.py": "from models import crea\ncrea(1)\n"}

    ses = _sesion(raiz, ["auth.py"])
    ses._c._t.cerrado = True  # pyright murió a mitad de sesión

    # Debe DEGRADAR a capa 16 (ast + token-scan), no romper: mismo resultado
    # que sin sesión.
    assert motivos("models.py", viejo, nuevo, ses) == motivos(
        "models.py", viejo, nuevo
    )
    assert impacto(ws, "models.py", viejo, nuevo, ses) == impacto(
        ws, "models.py", viejo, nuevo
    )
    # y el de capa 16 sí encuentra auth.py por el token (sanity)
    assert impacto(ws, "models.py", viejo, nuevo) == {"crea": ["auth.py"]}


class _TsserverFalso(_PyrightFalso):
    """Igual que el pyright falso pero 'parsea' `function NAME(` (TS/JS).
    Sirve para probar el MISMO cliente LSP universal con otro lenguaje:
    capa 18 = enchufar, no re-arquitecturar."""

    _DEF = re.compile(r"^(?:export\s+)?function ([A-Za-z_]\w*)\(([^)]*)\)",
                       re.M)


def test_jsts_usa_fan_out_real_via_tsserver_falso() -> None:
    raiz = "/data/ws/eq1"
    ws = {
        "models.ts": "export function crea(a) { return a }\n",
        "auth.ts": "y = 1\n",        # NO contiene el token 'crea'
        "reportes.ts": "z = 2\n",    # NO contiene el token 'crea'
    }
    srv = _TsserverFalso([path_a_uri(raiz, p) for p in ("auth.ts",)])
    c = ClienteLSP(srv)
    c.iniciar(path_a_uri(raiz, ""))
    ses = SesionLSP(c, raiz)

    viejo = ws["models.ts"]
    nuevo = "export function crea(a, b) { return a }\n"  # cambió la firma

    # Detección = jerarquía capa 16 (en sandbox, regex JS): hay aviso.
    assert motivos("models.ts", viejo, nuevo, ses) != {}
    # Fan-out = tsserver real: solo auth.ts, aunque el token no esté ahí.
    af = impacto({**ws, "models.ts": nuevo}, "models.ts", viejo, nuevo, ses)
    assert af == {"crea": ["auth.ts"]}


def test_arrancar_pyright_sin_binario_degrada_a_None() -> None:
    # En el sandbox no hay `pyright-langserver`: el contrato es devolver
    # None (nunca explotar) para que la jerarquía caiga a capa 16. Si algún
    # día el sandbox tuviera pyright, devolvería una SesionLSP — ambas son
    # contractualmente válidas; lo que NO se permite es propagar excepción.
    ses = arrancar_pyright("/tmp")
    assert ses is None or isinstance(ses, SesionLSP)
