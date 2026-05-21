"""Punto de entrada: `python -m orux.server` o `orux-server`.

Aquí —y solo aquí— se cablea la persistencia real (capa 3). El `SyncServer`
no sabe de directorios por sí mismo: recibe un `DiskStorage` inyectado. Eso
mantiene los tests arrancando en memoria y deja la decisión de "dónde se
guarda" en un único lugar visible.

**Por qué el directorio por defecto está FUERA del repo** (`~/.orux/...`):
desde capa 14 el frontend es React+Vite (un único contenedor multi-stage,
no se sirve más con Live Server desde dentro del repo). Mantener el estado
de runtime FUERA del árbol del repo sigue siendo correcto: evita que
herramientas locales (linters, formatters, watchers de IDE) crucen con el
workspace persistido, y la ruta es explícita para ops (`~/.orux/...`).
La nota histórica sobre Live Server quedó en `CLAUDE.md` (capa 14).

Cuando hay integración con Git, esta capa decide su propia ubicación
dentro del repo del usuario; ese es su problema, no el del runtime.

Se puede sobreescribir con la variable de entorno `ORUX_DATA`.
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

# Todo el estado de ejecución vive bajo ~/.orux, FUERA del árbol del
# proyecto a propósito (ver más abajo). El workspace en un subdir; usuarios,
# ownership y el secreto de firma como archivos hermanos.
BASE_POR_DEFECTO = Path.home() / ".orux"


def _secreto(base: Path) -> str:
    """Secreto para firmar tokens de sesión, estable entre reinicios.

    Prioridad: `ORUX_SESSION_SECRET` (env) > archivo `~/.orux/secret`.

    El env existe para GitHub OAuth: el callback corre en OTRO proceso (el
    contenedor `api`/Starlette) y tiene que firmar el token de sesión con el
    MISMO secreto que este server WS verifica. Compartir un archivo entre
    contenedores sería frágil; una variable de entorno inyectada a ambos es
    explícita y robusta. Sin el env se mantiene el comportamiento histórico
    (archivo): backward-compatible, y OAuth simplemente queda deshabilitado
    (cerrado por defecto), nunca a medias.

    El archivo se guarda en `~/.orux/secret` y se genera la primera vez.
    Estable = los tokens de sesión guardados en los clientes siguen valiendo
    tras reiniciar el server (no obliga a re-loguear a todos). Si alguien
    borra el archivo, simplemente todos re-loguean una vez.
    """
    env = os.environ.get("ORUX_SESSION_SECRET", "").strip()
    f = base / "secret"
    if env and f.exists():
        try:
            del_archivo = f.read_text(encoding="utf-8").strip()
            if del_archivo and del_archivo != env:
                # BACKEND-AUDIT-0290: la divergencia env vs archivo invalida
                # TODOS los tokens vivos (cada uno firmó con uno distinto).
                # Loguear ALTO para que se note en ops.
                logging.getLogger(__name__).warning(
                    "ORUX_SESSION_SECRET difiere del archivo %s: los tokens "
                    "firmados antes de este boot dejaron de valer", f,
                )
        except OSError:
            pass
    if env:
        return env
    if f.exists():
        try:
            return f.read_text(encoding="utf-8").strip()
        except OSError as e:
            # Existe pero no se puede leer (permisos): morir con un mensaje
            # accionable, no con un traceback crudo de bajo nivel.
            raise SystemExit(
                f"no se pudo leer el secreto de firma {f}: {e}"
            ) from e
    # Directorio 0700 también (BACKEND-AUDIT-0267): el archivo es 0600 pero
    # sin dir restrictivo otro usuario puede listarlo y ver QUE existe.
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(base, 0o700)
    except OSError:
        pass
    s = token_hex(32)
    # El secreto firma TODOS los tokens de sesión: quien lo lea forja la
    # sesión de cualquier usuario. Se crea 0600 de forma atómica (no
    # write_text+chmod, que deja una ventana world-readable).
    try:
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # Race con otro proceso que también está arrancando (BACKEND-AUDIT-0287):
        # leemos lo que el ganador escribió en vez de explotar.
        return f.read_text(encoding="utf-8").strip()
    try:
        os.write(fd, s.encode("utf-8"))
    finally:
        os.close(fd)
    return s


async def _amain() -> None:
    log = logging.getLogger(__name__)
    env = os.environ.get("ORUX_DATA")
    base = Path(env) if env else BASE_POR_DEFECTO
    base.mkdir(parents=True, exist_ok=True)
    secret = _secreto(base)
    host = os.environ.get("ORUX_HOST", "localhost")
    port = int(os.environ.get("ORUX_PORT", "8765"))
    dsn = os.environ.get("ORUX_DB_DSN", "").strip()

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
        # producción DEBE setear ORUX_DB_DSN (docker-compose ya lo hace).
        ws = base / "workspace"
        server = SyncServer(
            storage=DiskStorage(ws),
            users=UserStore(base / "users.json"),
            ownership=Ownership(base / "ownership.json"),
            secret=secret,
            git=GitRepo(ws),
        )
        log.warning(
            "sin ORUX_DB_DSN: equipos EFÍMEROS (memoria). Sólo dev. "
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
