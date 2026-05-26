"""Cliente LSP — núcleo de la capa 17 (Tier 0, el análisis más profundo).

Por qué LSP: hasta capa 16 el análisis era heurístico — Python-`ast` aísla
interfaz pero NO resuelve cross-módulo (sigue siendo "¿qué archivo tiene el
token X?"). Un language server (pyright) mantiene un índice semántico real:
sabe quién *importa y usa de verdad* un símbolo. Eso mata los falsos
positivos = la confianza que hace que alguien cambie su IDE. orux habla UN
solo protocolo (LSP) y enchufa el server que haya; el primero, pyright.

**Sync y bloqueante a propósito.** La interfaz de los tiers (capa 16) es
sync y ya se invoca dentro de `asyncio.to_thread` (`_notificar_impacto`).
Hacer I/O bloqueante contra el subproceso pyright DENTRO de ese hilo no
bloquea el event loop (está en un worker). Así el tier LSP respeta la misma
interfaz Protocol que ast/tree-sitter/regex, sin ripple ni async colándose
en la jerarquía.

**Disciplina sandbox (igual que Postgres/tree-sitter).** El transporte es
abstracto: la lógica (framing JSON-RPC, handshake, request/response por id)
se prueba 100% en sandbox contra un server LSP FALSO en memoria; el
subproceso pyright real es el único I/O y se verifica en el VPS.

Esta primera pieza es el núcleo transport-agnóstico + el server falso. El
mapeo pyright→modelo y el ciclo de vida del demonio son pasos siguientes.
"""

from __future__ import annotations

import json
import logging
import os
import select
import subprocess
import tempfile
import threading
from typing import Protocol

from .modelo import Simbolo

logger = logging.getLogger(__name__)


class Transporte(Protocol):
    """Stream bidireccional de bytes. Real = stdio del subproceso pyright;
    falso = tubo en memoria (tests). El cliente no sabe cuál es."""

    def escribir(self, datos: bytes) -> None: ...

    def leer(self, n: int) -> bytes:
        """Exactamente n bytes (o menos solo si el stream se cerró)."""
        ...


def enmarcar(mensaje: dict) -> bytes:
    """Mensaje JSON-RPC -> bytes con cabecera LSP (`Content-Length`).

    El cuerpo es UTF-8; la cabecera ASCII y termina en \\r\\n\\r\\n. Es el
    sobre exacto que esperan pyright/tsserver/cualquier server LSP.
    """
    cuerpo = json.dumps(mensaje, separators=(",", ":")).encode("utf-8")
    cabecera = f"Content-Length: {len(cuerpo)}\r\n\r\n".encode("ascii")
    return cabecera + cuerpo


def _leer_mensaje(transporte: Transporte) -> dict | None:
    """Lee un mensaje LSP enmarcado del transporte. None si el stream murió.

    Parsea las cabeceras línea a línea (solo nos importa `Content-Length`),
    luego lee exactamente esos bytes de cuerpo. Robusto a cabeceras extra.
    """
    cab = b""
    while b"\r\n\r\n" not in cab:
        ch = transporte.leer(1)
        if not ch:
            return None  # stream cerrado (server murió): el caller degrada
        cab += ch
    largo = 0
    for linea in cab.split(b"\r\n"):
        if linea.lower().startswith(b"content-length:"):
            largo = int(linea.split(b":", 1)[1].strip())
    cuerpo = b""
    while len(cuerpo) < largo:
        trozo = transporte.leer(largo - len(cuerpo))
        if not trozo:
            return None
        cuerpo += trozo
    try:
        return json.loads(cuerpo.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None  # basura: tratar como server roto, no explotar


class ErrorLSP(RuntimeError):
    """El server respondió un error JSON-RPC, o murió. El tier lo captura y
    degrada al siguiente (tree-sitter): nunca propaga al server de orux."""


class ClienteLSP:
    """Cliente JSON-RPC mínimo para LSP. Sync; serializa por un id creciente.

    Solo lo que el análisis necesita: handshake, sincronizar documentos y
    pedir symbols/references. No implementa todo LSP a propósito (capa real
    pero mínima); lo que falte se agrega cuando un caso real lo pida.
    """

    def __init__(self, transporte: Transporte) -> None:
        self._t = transporte
        self._id = 0
        self._vivo = True

    # -- envío -------------------------------------------------------------

    def _enviar(self, mensaje: dict) -> None:
        if not self._vivo:
            raise ErrorLSP("cliente LSP cerrado")
        try:
            self._t.escribir(enmarcar(mensaje))
        except Exception as e:  # noqa: BLE001 - subproceso muerto => degradar
            self._vivo = False
            raise ErrorLSP(f"escritura LSP falló: {e}") from e

    def notificar(self, metodo: str, params: dict) -> None:
        """Notificación JSON-RPC (sin id, sin respuesta): didOpen/didChange."""
        self._enviar({"jsonrpc": "2.0", "method": metodo, "params": params})

    def pedir(self, metodo: str, params: dict) -> object:
        """Request JSON-RPC: envía y BLOQUEA hasta la respuesta de este id.

        Las notificaciones del server (diagnósticos, logs) y respuestas de
        otros ids que lleguen mientras tanto se descartan: solo nos importa
        el resultado de ESTA pregunta (el análisis es pregunta→respuesta).
        """
        self._id += 1
        mio = self._id
        self._enviar(
            {"jsonrpc": "2.0", "id": mio, "method": metodo, "params": params}
        )
        while True:
            msg = _leer_mensaje(self._t)
            if msg is None:
                self._vivo = False
                raise ErrorLSP("server LSP cerró el stream")
            if msg.get("id") == mio:
                if "error" in msg:
                    raise ErrorLSP(str(msg["error"]))
                return msg.get("result")
            # otra cosa (notificación / id ajeno): drenar y seguir esperando

    # -- ciclo LSP mínimo --------------------------------------------------

    def iniciar(self, root_uri: str) -> None:
        """Handshake LSP: initialize (request) + initialized (notif)."""
        self.pedir(
            "initialize",
            {
                "processId": None,
                "rootUri": root_uri,
                "capabilities": {
                    "textDocument": {
                        "documentSymbol": {
                            "hierarchicalDocumentSymbolSupport": True
                        },
                        "references": {},
                    }
                },
            },
        )
        self.notificar("initialized", {})

    def abrir(self, uri: str, texto: str, lenguaje: str = "python") -> None:
        self.notificar(
            "textDocument/didOpen",
            {
                "textDocument": {
                    "uri": uri,
                    "languageId": lenguaje,
                    "version": 1,
                    "text": texto,
                }
            },
        )

    def cambiar(self, uri: str, texto: str, version: int) -> None:
        # Sincronización full (no incremental): mínimo y correcto. El
        # incremental es optimización futura (capa de latencia propia).
        self.notificar(
            "textDocument/didChange",
            {
                "textDocument": {"uri": uri, "version": version},
                "contentChanges": [{"text": texto}],
            },
        )

    def document_symbol(self, uri: str) -> object:
        return self.pedir(
            "textDocument/documentSymbol", {"textDocument": {"uri": uri}}
        )

    def referencias(self, uri: str, linea: int, caracter: int) -> object:
        return self.pedir(
            "textDocument/references",
            {
                "textDocument": {"uri": uri},
                "position": {"line": linea, "character": caracter},
                "context": {"includeDeclaration": False},
            },
        )

    def cerrar(self) -> None:
        if not self._vivo:
            return
        # BACKEND-AUDIT-0130: `shutdown` puede colgar hasta el timeout si el
        # server LSP está colgado. Hacemos solo `exit` notify y matamos —el
        # eviction de capa 17 debe ser barata, no 15s × N lenguajes.
        try:
            self.notificar("exit", {})
        except ErrorLSP:
            pass  # ya estaba muerto: no es error que importe
        self._vivo = False
        cerrar_t = getattr(self._t, "cerrar", None)
        if cerrar_t is not None:
            cerrar_t()  # mata el subproceso (no aplica al transporte falso)


# --- Mapeo pyright -> modelo común (puro, 100% sandbox-testeable) ----------
#
# pyright responde en términos de LSP (DocumentSymbol, Location). Acá se
# traduce a lo que la jerarquía ya entiende: el `Simbolo` de capa 16 y, lo
# nuevo y central, el conjunto REAL de archivos que usan un símbolo (no "los
# que tienen el token" — pyright resolvió imports de verdad). El modelo y
# `cambios_que_importan_modelo` NO cambian: solo se rellenan mejor.

# LSP SymbolKind (los que nos importan para Python).
_K_CLASS = 5
_K_METHOD = 6
_K_PROPERTY = 7
_K_FIELD = 8
_K_CONSTRUCTOR = 9
_K_ENUM = 10
_K_INTERFACE = 11
_K_FUNCTION = 12
_K_VARIABLE = 13


def path_a_uri(raiz: str, path: str) -> str:
    """`models.py` -> `file:///<raiz>/models.py`. Esquema único y estable
    para que `references` (que vuelve en URIs) se mapee de vuelta a paths
    del workspace. BACKEND-AUDIT-0111: percent-encode los caracteres
    especiales del path (espacios, %, #, ?) para no romper la URI."""
    from urllib.parse import quote
    seguro = quote(path.lstrip("/"), safe="/")
    return "file://" + raiz.rstrip("/") + "/" + seguro


def uri_a_path(raiz: str, uri: str) -> str | None:
    """Inverso. None si el URI cae fuera del workspace (dependencia de libs,
    stdlib: no es un archivo de equipo, no se avisa de él). BACKEND-AUDIT-0111:
    rechaza paths con `..` para evitar resolver fuera del workspace después."""
    from urllib.parse import unquote
    pref = "file://" + raiz.rstrip("/") + "/"
    if not uri.startswith(pref):
        return None
    rel = unquote(uri[len(pref):])
    # Anti-traversal: ningún componente puede ser `..` ni vacío.
    if not rel or any(seg in ("", "..") for seg in rel.split("/")):
        return None
    return rel


def _rebanar(texto: str, rango: dict) -> str:
    """Subcadena del fuente según un `range` LSP (líneas/cols 0-based). Es el
    `fuente` del Simbolo: si cambia ALGO del símbolo, cambia => sirve de
    early-out; no decide QUÉ cambió (eso lo dan firma/superficie)."""
    lineas = texto.splitlines(keepends=True)
    a, b = rango["start"], rango["end"]
    if a["line"] >= len(lineas):
        return ""
    if a["line"] == b["line"]:
        return lineas[a["line"]][a["character"]:b["character"]]
    trozo = [lineas[a["line"]][a["character"]:]]
    trozo += lineas[a["line"] + 1:b["line"]]
    if b["line"] < len(lineas):
        trozo.append(lineas[b["line"]][:b["character"]])
    return "".join(trozo)


def _superficie(hijos: list[dict]) -> tuple[str, frozenset[str]]:
    """(firma de __init__, {miembros públicos}) desde los children de una
    clase. Mismo criterio que `_superficie_clase` de python.py para que el
    mensaje del modelo sea consistente: público = no empieza con `_`."""
    init = ""
    pub: set[str] = set()
    for h in hijos:
        nom = h.get("name", "")
        k = h.get("kind")
        if nom == "__init__" or k == _K_CONSTRUCTOR:
            init = h.get("detail") or "()"
            continue
        if nom.startswith("_"):
            continue
        if k == _K_METHOD:
            pub.add(nom + "()")
        elif k in (_K_PROPERTY, _K_FIELD, _K_VARIABLE):
            pub.add(nom)
    return init, frozenset(pub)


def simbolos_de_pyright(
    doc_symbols: object, fuente: str
) -> dict[str, Simbolo]:
    """`textDocument/documentSymbol` (jerárquico) -> {nombre: Simbolo}.

    Solo nivel módulo (igual que toda la capa 6+): funciones, clases y
    enum/interface. detallado=True — pyright es type-aware, da el aviso fino
    sin la coletilla "sin parser". `detail` de pyright es la firma
    normalizada (independiente del cuerpo): justo lo que queremos comparar.
    """
    if not isinstance(doc_symbols, list):
        return {}
    out: dict[str, Simbolo] = {}
    for s in doc_symbols:
        if not isinstance(s, dict):
            continue
        nom = s.get("name", "")
        k = s.get("kind")
        if not nom:
            continue
        rng = s.get("range", {})
        fte = _rebanar(fuente, rng) if rng else nom
        if k == _K_FUNCTION:
            out[nom] = Simbolo(
                nombre=nom, tipo="funcion", fuente=fte,
                firma=s.get("detail") or "()", detallado=True,
            )
        elif k == _K_CLASS:
            init, sup = _superficie(s.get("children") or [])
            out[nom] = Simbolo(
                nombre=nom, tipo="clase", fuente=fte,
                init=init, superficie=sup, detallado=True,
            )
        elif k in (_K_ENUM, _K_INTERFACE):
            out[nom] = Simbolo(
                nombre=nom, tipo="tipo", fuente=fte, detallado=True,
            )
    return out


def _posicion_nombre(doc_symbols: object, nombre: str) -> tuple[int, int] | None:
    """Posición (línea, col) del NOMBRE de un símbolo top, para preguntarle a
    pyright `references` ahí. Prefiere `selectionRange` (el rango del
    identificador) sobre `range` (todo el símbolo)."""
    if not isinstance(doc_symbols, list):
        return None
    for s in doc_symbols:
        if isinstance(s, dict) and s.get("name") == nombre:
            r = s.get("selectionRange") or s.get("range") or {}
            ini = r.get("start")
            if ini:
                return ini["line"], ini["character"]
    return None


class SesionLSP:
    """Una sesión de análisis contra UN workspace, vía un `ClienteLSP` ya
    conectado. Encapsula sincronizar documentos y traducir a modelo/fan-out.

    El subproceso pyright real (spawn + tibio por equipo + reciclado) es el
    paso siguiente; ESTA clase es pura lógica de protocolo y se prueba 100%
    con el server falso. Cualquier `ErrorLSP` (server muerto/lento/roto) se
    traga y devuelve None: el tier degrada solo a tree-sitter/ast.
    """

    def __init__(self, cliente: ClienteLSP, raiz: str) -> None:
        self._c = cliente
        self._raiz = raiz
        self._ver: dict[str, int] = {}
        # El análisis corre en hilos worker (asyncio.to_thread), y un equipo
        # teclea concurrente: varias llamadas pueden pegarle a ESTA sesión a
        # la vez. ClienteLSP no es reentrante (casa respuesta por id); el
        # lock serializa el acceso a pyright por equipo.
        self._lock = threading.Lock()

    def disponible(self) -> bool:
        return self._c._vivo

    def _sync(self, uri: str, texto: str, lang_id: str) -> None:
        if uri not in self._ver:
            self._c.abrir(uri, texto, lang_id)
            self._ver[uri] = 1
        else:
            self._ver[uri] += 1
            self._c.cambiar(uri, texto, self._ver[uri])

    def simbolos(self, path: str, fuente: str) -> dict[str, Simbolo] | None:
        uri = path_a_uri(self._raiz, path)
        with self._lock:
            try:
                self._sync(uri, fuente, _language_id(path))
                ds = self._c.document_symbol(uri)
            except ErrorLSP:
                return None
        return simbolos_de_pyright(ds, fuente)

    def fan_out(
        self, workspace: dict[str, str], path: str, nuevo: str,
        syms: list[str],
    ) -> dict[str, set[str]] | None:
        """{símbolo: set de OTROS paths que lo usan de verdad} o None si el
        server falló (=> degradar). Sincroniza TODO el workspace para que
        pyright resuelva imports cross-módulo (ése es el salto)."""
        with self._lock:
            try:
                for p, txt in workspace.items():
                    self._sync(
                        path_a_uri(self._raiz, p), txt, _language_id(p)
                    )
                uri = path_a_uri(self._raiz, path)
                self._sync(uri, nuevo, _language_id(path))
                ds = self._c.document_symbol(uri)
                out: dict[str, set[str]] = {}
                for s in syms:
                    pos = _posicion_nombre(ds, s)
                    if pos is None:
                        out[s] = set()
                        continue
                    refs = self._c.referencias(uri, pos[0], pos[1])
                    out[s] = paths_que_referencian(refs, self._raiz, path)
                return out
            except ErrorLSP:
                return None

    def cerrar(self) -> None:
        """Mata la sesión y su subproceso. Se llama al reciclar el equipo
        (capa 15: clone destructivo) o al disponerlo."""
        with self._lock:
            self._c.cerrar()


def paths_que_referencian(
    refs: object, raiz: str, path_propio: str
) -> set[str]:
    """`textDocument/references` -> set de OTROS paths del workspace que usan
    el símbolo. ESTE es el salto: resolución real de pyright, no "archivos
    con el token". Se excluye el propio archivo y lo que cae fuera del
    workspace (stdlib/deps: no hay dueño a quién avisar)."""
    if not isinstance(refs, list):
        return set()
    out: set[str] = set()
    for loc in refs:
        if not isinstance(loc, dict):
            continue
        p = uri_a_path(raiz, loc.get("uri", ""))
        if p is not None and p != path_propio:
            out.add(p)
    return out


# --- Subproceso pyright real: el ÚNICO I/O (verificado en VPS, no sandbox) -


class _TransporteProceso:
    """Transporte sobre stdin/stdout de un subproceso. Lectura con timeout:
    un pyright colgado NO debe congelar el hilo de análisis para siempre
    (modo producto). Si se vence o el proceso muere, leer() devuelve b"" y
    el ClienteLSP lo convierte en ErrorLSP => el tier degrada."""

    def __init__(self, proc: subprocess.Popen, timeout: float) -> None:
        self._p = proc
        self._timeout = timeout
        self._of = proc.stdout.fileno()

    def escribir(self, datos: bytes) -> None:
        self._p.stdin.write(datos)
        self._p.stdin.flush()

    def leer(self, n: int) -> bytes:
        if self._p.poll() is not None:
            return b""  # el proceso murió
        listos, _, _ = select.select([self._of], [], [], self._timeout)
        if not listos:
            # Re-sondeo: si el proceso murió ENTRE el poll inicial y el
            # select (segfault, OOM, SIGTERM externo), `select` retorna
            # vacío indistinguible de un timeout real. Loguear el `returncode`
            # deja claro cuál fue y ayuda a operadores que ven análisis
            # degradado sin causa visible.
            rc = self._p.poll()
            if rc is not None:
                logger.warning(
                    "LSP pid=%s murió durante read (returncode=%s) — "
                    "se reportará como degradación",
                    self._p.pid, rc,
                )
            return b""  # timeout o crash: degradar
        return os.read(self._of, n)

    def cerrar(self) -> None:
        # Cerramos stdin para que el server vea EOF (algunos terminan limpios).
        try:
            if self._p.stdin is not None:
                self._p.stdin.close()
        except OSError as e:
            logger.debug("cerrar stdin LSP pid=%s: %r", self._p.pid, e)
        try:
            self._p.kill()
        except Exception as e:  # noqa: BLE001 - ya estaba muerto
            logger.debug("kill LSP pid=%s: %r", self._p.pid, e)
        # `wait(timeout)` cosecha el zombie (BACKEND-AUDIT-0107): sin esto
        # cada LSP que matamos deja una entrada zombie en Linux hasta el cosecha
        # global del padre. 2s es generoso (kill ya disparó).
        try:
            self._p.wait(timeout=2.0)
        except subprocess.TimeoutExpired:
            logger.warning(
                "LSP pid=%s no terminó tras 2s post-kill (zombie posible)",
                self._p.pid,
            )
        except Exception as e:  # noqa: BLE001
            logger.debug("wait LSP pid=%s: %r", self._p.pid, e)
        # Cerrar stdout/stderr/stdin para no fugar FDs.
        for h in (self._p.stdout, self._p.stderr, self._p.stdin):
            try:
                if h is not None:
                    h.close()
            except OSError as e:
                logger.debug(
                    "cerrar FD LSP pid=%s: %r", self._p.pid, e,
                )


# Servidor LSP por clave de lenguaje (la misma que usa `tiers`): lista de
# comandos candidatos a probar en orden. pyright-python expone
# `pyright-langserver` y a veces `pyright-python-langserver`. tsserver es
# `typescript-language-server --stdio` (npm). El cliente es UNIVERSAL: sumar
# un lenguaje es agregar una fila acá + su languageId abajo. Nada más.
def _scrubear_stderr(texto: str) -> str:
    """Remueve patrones tipo ORUX_GIT_TOKEN=... y otros valores que parezcan
    secrets antes de loguear (BACKEND-AUDIT-0243). Best-effort; el patrón es
    `<VAR>=<valor>` para vars con prefijo ORUX_ o que contengan TOKEN/SECRET/
    PASSWORD/KEY."""
    import re as _re
    pat = _re.compile(
        r"(ORUX_\w+|[A-Z_]*(?:TOKEN|SECRET|PASSWORD|KEY|DSN))=\S+",
        _re.IGNORECASE,
    )
    return pat.sub(r"\1=***", texto)


_SERVIDORES: dict[str, tuple[list[str], ...]] = {
    "py": (
        ["pyright-langserver", "--stdio"],
        ["pyright-python-langserver", "--stdio"],
    ),
    "jsts": (
        ["typescript-language-server", "--stdio"],
    ),
    # Capa 20: ambos hablan LSP por stdio sin args. `gopls serve` es el
    # alias explícito por si la versión lo necesita.
    "go": (
        ["gopls"],
        ["gopls", "serve"],
    ),
    "rust": (
        ["rust-analyzer"],
    ),
}

# Extensión -> languageId LSP. Importa porque tsserver trata distinto .ts
# de .tsx (y .js de .jsx); pyright ignora esto pero cuesta cero ser exacto.
_LANG_ID = {
    "py": "python", "pyi": "python",
    "ts": "typescript", "mts": "typescript", "cts": "typescript",
    "tsx": "typescriptreact",
    "js": "javascript", "mjs": "javascript", "cjs": "javascript",
    "jsx": "javascriptreact",
    "go": "go",
    "rs": "rust",
}


def _language_id(path: str) -> str:
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else ""
    return _LANG_ID.get(ext, "plaintext")


def arrancar_lsp(
    lang: str, raiz: str, timeout: float = 15.0
) -> SesionLSP | None:
    """Arranca el language server de `lang` ("py" -> pyright, "jsts" ->
    tsserver) sobre `raiz` y hace el handshake. Devuelve la sesión lista, o
    None ante CUALQUIER fallo (binario ausente —caso del sandbox—, spawn,
    handshake). None => la jerarquía cae sola a tree-sitter/ast: nunca
    rompe, nunca propaga.

    Modo producto: ante fallo se LOGUEA la razón exacta + la cola de stderr
    del server. Sin esto, un server que no arranca en el VPS es invisible:
    el análisis "funciona" pero degradado y nadie sabe por qué. stderr va a
    un archivo temporal (no a un pipe: un pipe sin leer se llena y CUELGA el
    server en el camino feliz)."""
    cmds = _SERVIDORES.get(lang)
    if not cmds:
        return None
    ultimo = ""
    for cmd in cmds:
        # Try/finally externo: garantiza `err.close()` en TODOS los caminos
        # — incluso si `Popen` levanta algo distinto de FileNotFoundError/
        # OSError (MemoryError, KeyboardInterrupt) o si la rama `return`
        # exitosa no debería cerrar `err` PERO `err` sigue siendo nuestro
        # FD propio (el subproceso ya lo dup-ó internamente con `stderr=err`,
        # así que cerrar el handle nuestro no afecta al hijo).
        err = tempfile.TemporaryFile()
        try:
            try:
                # `start_new_session=True` aísla el LSP en su propio process
                # group (BACKEND-AUDIT-0145): si el padre cae con SIGKILL, el
                # session leader puede ser SIGTERM-eado en bloque al matar el
                # process group, sin dejar huerfanos. `subprocess.DEVNULL`
                # para stderr era una opción para evitar el crecimiento del
                # temp, pero perdemos los logs de error que sí queremos; el
                # barrido de `cerrar()` cierra el FD a tiempo.
                proc = subprocess.Popen(
                    cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=err, bufsize=0, start_new_session=True,
                )
            except (FileNotFoundError, OSError) as e:
                ultimo = f"{cmd[0]}: no se pudo ejecutar ({e})"
                continue
            try:
                cliente = ClienteLSP(_TransporteProceso(proc, timeout))
                cliente.iniciar("file://" + raiz.rstrip("/"))
                logger.info(
                    "LSP %s arrancado (%s) sobre %s", lang, cmd[0], raiz
                )
                return SesionLSP(cliente, raiz)
            except Exception as e:  # noqa: BLE001 - handshake falló
                try:
                    proc.kill()
                except Exception as ek:  # noqa: BLE001
                    logger.debug(
                        "kill LSP %s tras handshake fallido: %r", lang, ek,
                    )
                try:
                    err.seek(0)
                    cola = (
                        err.read()[-800:].decode("utf-8", "replace").strip()
                    )
                    # BACKEND-AUDIT-0243: scrubear posibles secrets
                    # ORUX_GIT_TOKEN u otros si el LSP dumpea su env por error.
                    cola = _scrubear_stderr(cola)
                except Exception as ee:  # noqa: BLE001
                    logger.debug("lectura de stderr LSP %s: %r", lang, ee)
                    cola = ""
                ultimo = (
                    f"{cmd[0]}: handshake falló ({type(e).__name__}: {e})"
                    + (f" | stderr: {cola}" if cola else
                       " | stderr vacío (suele ser cache/red en el 1er uso)")
                )
        finally:
            err.close()
    logger.warning(
        "LSP %s NO disponible -> el análisis degrada a tree-sitter/ast. "
        "Razón: %s", lang, ultimo or "binario no encontrado en PATH",
    )
    return None


def arrancar_pyright(
    raiz: str, timeout: float = 15.0
) -> SesionLSP | None:
    """Compat: pyright = el LSP del lenguaje "py". Se mantiene mientras
    `sync.py` no migre a la sesión por-lenguaje (capa 18 paso 3)."""
    return arrancar_lsp("py", raiz, timeout)
