"""Punto de entrada: `python -m laidea.server` o `laidea-server`.

Aquí —y solo aquí— se cablea la persistencia real (capa 3). El `SyncServer`
no sabe de directorios por sí mismo: recibe un `DiskStorage` inyectado. Eso
mantiene los tests arrancando en memoria y deja la decisión de "dónde se
guarda" en un único lugar visible.

**Por qué el directorio por defecto está FUERA del repo** (`~/.laidea/...`):
en desarrollo el cliente se sirve con un servidor estático que vigila la
carpeta del proyecto y recarga el navegador ante cualquier cambio de archivo
(p. ej. Live Server). Si la persistencia escribiera dentro del repo, cada vez
que alguien crea un archivo o se aprueba un cambio, el watcher recargaría la
página, se caería el WebSocket y el cliente volvería con otra identidad —
perdiendo su ownership. Sacar el estado de ejecución del árbol vigilado mata
ese ciclo de raíz, sin depender de configurar el editor de cada quien.

Cuando llegue la integración con Git (capa final) esa capa decidirá su propia
ubicación dentro del repo del usuario; ese es su problema, no el del runtime.

Se puede sobreescribir con la variable de entorno `LAIDEA_DATA`. Si la
apuntas dentro del repo, acuérdate de excluirla del watcher (en `.gitignore`
ya está `workspace_data/`).
"""

from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path
from secrets import token_hex

from ..git import GitRepo
from ..identity import UserStore
from ..state import DiskStorage, Ownership
from .sync import SyncServer, TeamRuntime

# Todo el estado de ejecución vive bajo ~/.laidea, FUERA del árbol del
# proyecto a propósito (ver más abajo). El workspace en un subdir; usuarios,
# ownership y el secreto de firma como archivos hermanos.
BASE_POR_DEFECTO = Path.home() / ".laidea"


def _secreto(base: Path) -> str:
    """Secreto para firmar tokens de sesión, estable entre reinicios.

    Se guarda en `~/.laidea/secret` y se genera la primera vez. Estable =
    los tokens de sesión guardados en los clientes siguen valiendo tras
    reiniciar el server (no obliga a re-loguear a todos). Si alguien borra el
    archivo, simplemente todos re-loguean una vez.
    """
    f = base / "secret"
    if f.exists():
        return f.read_text(encoding="utf-8").strip()
    base.mkdir(parents=True, exist_ok=True)
    s = token_hex(32)
    f.write_text(s, encoding="utf-8")
    return s


async def _amain() -> None:
    log = logging.getLogger(__name__)
    env = os.environ.get("LAIDEA_DATA")
    base = Path(env) if env else BASE_POR_DEFECTO
    base.mkdir(parents=True, exist_ok=True)
    secret = _secreto(base)
    host = os.environ.get("LAIDEA_HOST", "localhost")
    port = int(os.environ.get("LAIDEA_PORT", "8765"))
    dsn = os.environ.get("LAIDEA_DB_DSN", "").strip()

    if dsn:
        # Capa 15 (sistema real): metadatos en Postgres; el workspace de
        # CADA equipo es su propio repo git en disco, en /data/ws/<team_id>.
        # Así un equipo no ve al otro ni en la DB ni en el filesystem, y
        # sigue valiendo "git clone basta" (cada carpeta es un repo de
        # verdad). Los equipos/usuarios sobreviven a reiniciar (Postgres).
        from ..db import Database
        from ..db.stores import PgOwnershipStore, PgUserStore
        from ..teams import PgTeamStore

        db = await Database.conectar(dsn)
        log.info("Postgres conectado; esquema aplicado")
        ws_root = base / "ws"
        ws_root.mkdir(parents=True, exist_ok=True)

        def _runtime(team_id: str) -> TeamRuntime:
            d = ws_root / team_id
            return TeamRuntime(
                team_id=team_id,
                storage=DiskStorage(d),
                git=GitRepo(d),
            )

        server = SyncServer(
            users=PgUserStore(db),
            teams=PgTeamStore(db),
            ownership_store=PgOwnershipStore(db),
            runtime_factory=_runtime,
            secret=secret,
        )
        log.info("estado: Postgres (users/teams/ownership) + ws por equipo en %s", ws_root)
    else:
        # Sin DSN: modo en memoria/JSON de un solo equipo implícito (dev /
        # arranque sin DB). Los equipos NO sobreviven a reiniciar — por eso
        # producción DEBE setear LAIDEA_DB_DSN (docker-compose ya lo hace).
        ws = base / "workspace"
        server = SyncServer(
            storage=DiskStorage(ws),
            users=UserStore(base / "users.json"),
            ownership=Ownership(base / "ownership.json"),
            secret=secret,
            git=GitRepo(ws),
        )
        log.warning(
            "sin LAIDEA_DB_DSN: equipos EFÍMEROS (memoria). Sólo dev. "
            "estado en %s", base,
        )

    await server.run(host=host, port=port)


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    asyncio.run(_amain())


if __name__ == "__main__":
    main()
