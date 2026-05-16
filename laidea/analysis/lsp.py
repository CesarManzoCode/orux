"""Cliente LSP — núcleo de la capa 17 (Tier 0, el análisis más profundo).

Por qué LSP: hasta capa 16 el análisis era heurístico — Python-`ast` aísla
interfaz pero NO resuelve cross-módulo (sigue siendo "¿qué archivo tiene el
token X?"). Un language server (pyright) mantiene un índice semántico real:
sabe quién *importa y usa de verdad* un símbolo. Eso mata los falsos
positivos = la confianza que hace que alguien cambie su IDE. laidea habla UN
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
from typing import Protocol


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
    degrada al siguiente (tree-sitter): nunca propaga al server de laidea."""


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
        try:
            self.pedir("shutdown", {})
            self.notificar("exit", {})
        except ErrorLSP:
            pass  # ya estaba muerto: no es error que importe
        self._vivo = False
