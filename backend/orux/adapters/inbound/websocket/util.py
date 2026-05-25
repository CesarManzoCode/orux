"""Utilidades del server WS sin estado del `SyncServer`.

Lo que vive acá: funciones puras o casi-puras que `sync.py` necesita pero
que NO dependen de los atributos de instancia del server. Sacarlas de
`sync.py` reduce su tamaño y deja claro qué es lógica del server vs.
qué son helpers reutilizables.

- `autor_git(usuario)`: deriva (nombre, email) para commits.
- `_UsuariosAsync` + `wrap_users`: adapta un `UserStore` síncrono a una
  superficie async, para que el server haga siempre `await users.X()`.
- `ip_cliente(websocket)`: extrae la IP real (vía `X-Forwarded-For` cuando
  hay proxy, fallback al socket).
"""

from __future__ import annotations

import inspect
import logging

from websockets.asyncio.server import ServerConnection

from orux._net import ip_proxy_confiable
from orux.identity import UserStore

logger = logging.getLogger(__name__)


def autor_git(usuario: str) -> tuple[str, str]:
    """Identidad de commit a partir del usuario autenticado (capa 7).

    Si el usuario parece un email lo usamos como email y el nombre es la
    parte antes de la @. Si no, nombre = usuario y email sintético
    `usuario@orux.local` (git exige un email; no tenemos uno real y no lo
    inventamos bonito a propósito — es honesto que sea sintético).
    """
    if "@" in usuario:
        return usuario.split("@", 1)[0], usuario
    return usuario, f"{usuario}@orux.local"


class _UsuariosAsync:
    """Envuelve un `UserStore` síncrono (en memoria/JSON, tests) en una
    superficie async, para que el server haga SIEMPRE `await self.users.X()`
    sin importar si detrás hay JSON (tests) o Postgres (deploy). Si ya es
    async (PgUserStore) el server lo usa tal cual, sin envolver."""

    def __init__(self, base) -> None:
        self._b = base

    async def existe(self, u: str) -> bool:
        return self._b.existe(u)

    async def registrar(self, u: str, p: str) -> str:
        return self._b.registrar(u, p)

    async def verificar(self, u: str, p: str) -> bool:
        return self._b.verificar(u, p)

    async def usuarios(self) -> list[str]:
        """Lista de nombres registrados. Lo usa el cap de registro
        (BACKEND-AUDIT-0224)."""
        listar = getattr(self._b, "usuarios", None)
        return listar() if callable(listar) else []

    async def epoch(self, u: str) -> int:
        """Contador de sesiones del usuario (BACKEND-AUDIT-0002). 0 si el
        store no lo soporta (compat con stores legacy)."""
        ep = getattr(self._b, "epoch", None)
        if ep is None:
            return 0
        try:
            return int(ep(u))
        except (TypeError, ValueError):
            return 0


def wrap_users(users):
    """Adapta `users` (síncrono o async) a la interfaz async que usa el
    server. Si ya expone `existe` como coroutine, se devuelve tal cual."""
    base = users if users is not None else UserStore()
    # PgUserStore ya es async (existe es coroutine): usar tal cual.
    if inspect.iscoroutinefunction(getattr(base, "existe", None)):
        return base
    return _UsuariosAsync(base)


def ip_cliente(websocket: ServerConnection) -> str:
    """IP del cliente para rate-limit / logging. En el deploy la conexión
    TCP llega desde Caddy y la IP real del usuario va en `X-Forwarded-For`
    que Caddy agrega. En dev/tests sin proxy: dirección del socket.

    BACKEND-AUDIT M-04: confiamos en XFF SOLO cuando el peer TCP es un
    proxy de confianza (red privada / loopback de Docker compose). Antes
    cualquier conexión que mandara XFF podía pisar la IP usada para los
    buckets — un atacante con acceso directo al contenedor (mal config,
    pod vecino comprometido, port forward olvidado) rotaba el XFF y
    evadía el rate-limit de login/registro. Ahora ese atacante queda
    fijado a la IP del socket (su propia IP).

    Defensivo: ante cualquier fallo devuelve "desconocida" — nunca rompe
    el flujo de auth.
    """
    socket_ip = ""
    try:
        addr = websocket.remote_address
        if addr:
            socket_ip = str(addr[0])
    except Exception as e:  # noqa: BLE001
        logger.debug("remote_address ilegible: %r", e)
    try:
        req = getattr(websocket, "request", None)
        if req is not None and ip_proxy_confiable(socket_ip):
            xff = req.headers.get("X-Forwarded-For", "")
            if xff:
                return xff.split(",")[0].strip()
    except Exception as e:  # noqa: BLE001 - diagnóstico opcional
        logger.debug("X-Forwarded-For ilegible: %r", e)
    return socket_ip or "desconocida"
