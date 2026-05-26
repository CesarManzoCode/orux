"""`JsonUserStore`: persistencia de usuarios en un archivo JSON.

Modo dev / tests sin Postgres. Encapsula la persistencia que vivía inline en
`identity.UserStore` antes del refactor hex. Implementa `UserStorePort`.

El estado en memoria sigue siendo la verdad en caliente; este store solo
hidrata al construir y escribe-a-través tras cada mutación. Async para
alinear con `PgUserStore` (asyncpg nativo); el IO sync se envuelve con
`to_thread` para no bloquear el loop.

Hardening conservado del original (BACKEND-AUDIT-001x, -002x):
- Tmp con pid: no colisiona entre corutinas.
- Permisos 0600 al crear (los hashes PBKDF2 no se exponen a otros usuarios
  del host); chmod defensivo si el archivo ya existía con permisos laxos.
- Validación estructural al cargar: registros mal formados se descartan en
  silencio en vez de explotar (un dev no debe debugger un users.json corrupto).
- Lock interno (`asyncio.Lock`) para tramos check-then-set (registrar,
  asegurar_externo, cambiar_password): cubre TOCTOU de dos requests
  concurrentes con el mismo usuario.
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from orux.identity.passwords import (
    MARCADOR_EXTERNO,
    hash_password,
    verificar_password,
)
from orux.identity.store import (
    _epoch_de_registro,
    _hash_de_registro,
    normalizar,
    validar_nuevo_usuario,
)


class JsonUserStore:
    """Implementa `UserStorePort` sobre un archivo JSON local.

    El estado en memoria (`_usuarios`) es la verdad caliente; cada mutación
    hace flush al disco. El lock cubre check-then-set para que dos requests
    concurrentes no pisen el registro.
    """

    def __init__(self, path: Path | str) -> None:
        self._path = Path(path)
        self._usuarios: dict[str, object] = self._cargar_inicial()
        self._lock = asyncio.Lock()

    def _cargar_inicial(self) -> dict[str, object]:
        if not self._path.exists():
            return {}
        try:
            cargado = json.loads(self._path.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            return {}
        if not isinstance(cargado, dict):
            return {}
        limpio: dict[str, object] = {}
        for k, v in cargado.items():
            if not isinstance(k, str):
                continue
            if isinstance(v, str) or (
                isinstance(v, dict) and isinstance(v.get("hash"), str)
            ):
                limpio[k] = v
        return limpio

    async def _flush(self) -> None:
        await asyncio.to_thread(self._flush_sync)

    def _flush_sync(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(
            f"{self._path.suffix}.{os.getpid()}.tmp"
        )
        fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(self._usuarios, f)
                # AUDITORIA-SEGURIDAD 2026-05-25 A-PERS-03: fsync antes del
                # rename atómico. Sin esto, un crash duro de la VM entre
                # el `json.dump` (que pasa a buffers del kernel) y la
                # flush real al disco podía dejar el archivo vacío tras
                # `os.replace`. `JsonOwnershipStore` ya tenía este patrón;
                # acá faltaba — sólo afecta dev local (producción usa
                # Postgres) pero el costo del fsync es despreciable.
                f.flush()
                os.fsync(f.fileno())
        except Exception:
            try:
                tmp.unlink()
            except OSError:
                pass
            raise
        os.replace(tmp, self._path)
        try:
            os.chmod(self._path, 0o600)
        except OSError:
            pass

    async def existe(self, username: str) -> bool:
        return normalizar(username) in self._usuarios

    async def usuarios(self) -> list[str]:
        return sorted(self._usuarios)

    def admin(self) -> str | None:
        """Compat con el modelo legacy capa 12 (pre-multi-team). Sync porque
        es lectura del dict en memoria; no está en `UserStorePort` (la
        producción multi-team usa rol DENTRO del equipo, no esto)."""
        return next(iter(self._usuarios), None)

    async def registrar(self, username: str, password: str) -> str:
        u = validar_nuevo_usuario(username)
        async with self._lock:
            if u in self._usuarios:
                raise ValueError("ese usuario ya existe")
            self._usuarios[u] = {
                "hash": hash_password(password),
                "epoch": 0,
            }
            await self._flush()
        return u

    async def asegurar_externo(self, username: str) -> str:
        u = normalizar(username)
        if not u:
            raise ValueError("usuario inválido")
        # Las reglas de longitud/charset del externo se siguen aplicando en
        # la frontera (`identity.github`); acá solo idempotente.
        async with self._lock:
            if u not in self._usuarios:
                self._usuarios[u] = {"hash": MARCADOR_EXTERNO, "epoch": 0}
                await self._flush()
        return u

    async def verificar(self, username: str, password: str) -> bool:
        registro = self._usuarios.get(normalizar(username))
        h = _hash_de_registro(registro)
        if h is None:
            return False
        return verificar_password(password, h)

    async def epoch(self, username: str) -> int:
        return _epoch_de_registro(self._usuarios.get(normalizar(username)))

    async def revocar_sesiones(self, username: str) -> None:
        u = normalizar(username)
        async with self._lock:
            reg = self._usuarios.get(u)
            if reg is None:
                return
            h = _hash_de_registro(reg) or MARCADOR_EXTERNO
            self._usuarios[u] = {
                "hash": h, "epoch": _epoch_de_registro(reg) + 1,
            }
            await self._flush()

    async def borrar(self, username: str) -> bool:
        u = normalizar(username)
        async with self._lock:
            if u not in self._usuarios:
                return False
            del self._usuarios[u]
            await self._flush()
            return True
