"""Composition root: único lugar donde se cablea el grafo de la app.

`build_server(config)` recibe una `AppConfig` con todo lo que viene de afuera
(env vars: DSN, secrets, paths, puerto) y devuelve un `SyncServer` listo
para correr. Decide qué adapter usar para cada Port según la presencia o
ausencia de cada pieza de config (DSN ⇒ Postgres, etc.).

Sacar este cableado de `__main__.py` permite:
- testear el grafo end-to-end con configs alternativas;
- reusar el cableado desde un futuro CLI / scripts / migraciones;
- ver de un vistazo qué adapter cumple cada Port en cada entorno.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Awaitable, Callable

from .adapters.json import JsonOwnershipStore, JsonUserStore
from .git import GitRepo
from .ports import (
    OwnershipStorePort,
    ProposalsStorePort,
    TeamStorePort,
    UserStorePort,
)
from .server.config import DEFAULT_WS_PORT
from .server.runtime import TeamRuntime
from .server.sync import SyncServer
from .state import DiskStorage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class AppConfig:
    """Toda la config externa que necesita el grafo. `base_dir` es el
    directorio raíz del estado (~/.orux por defecto); `dsn` opcional
    elige Postgres vs JSON local."""

    base_dir: Path
    secret: str
    dsn: str = ""
    host: str = "localhost"
    port: int = DEFAULT_WS_PORT

    @classmethod
    def desde_env(cls, base_dir: Path, secret: str) -> "AppConfig":
        return cls(
            base_dir=base_dir,
            secret=secret,
            dsn=os.environ.get("ORUX_DB_DSN", "").strip(),
            host=os.environ.get("ORUX_HOST", "localhost"),
            port=int(os.environ.get("ORUX_PORT", str(DEFAULT_WS_PORT))),
        )


async def build_server(config: AppConfig) -> SyncServer:
    """Construye el SyncServer cableando los adapters según `config`.

    Dos modos:
    - **Con DSN** (producción): metadatos en Postgres (`PgUserStore`,
      `PgTeamStore`, `PgOwnershipStore`, `PgProposalsStore`); el workspace
      de cada equipo es su propio repo git en `base_dir/ws/<team_id>/`.
    - **Sin DSN** (dev): JSON local single-team (`JsonUserStore`,
      `JsonOwnershipStore`); workspace único en `base_dir/workspace/`.
    """
    if config.dsn:
        return await _build_postgres(config)
    return _build_dev_json(config)


async def _build_postgres(config: AppConfig) -> SyncServer:
    # Imports lazy: solo cargamos asyncpg si hay DSN (evita peso en dev).
    from .db import Database
    from .db.stores import (
        PgOwnershipStore,
        PgProposalsStore,
        PgUserStore,
    )
    from .teams import PgTeamStore

    db = await Database.conectar(config.dsn)
    logger.info("Postgres conectado; esquema aplicado")

    ws_root = config.base_dir / "ws"
    ws_root.mkdir(parents=True, exist_ok=True)

    users: UserStorePort = PgUserStore(db)
    teams: TeamStorePort = PgTeamStore(db)
    ownership_store: OwnershipStorePort = PgOwnershipStore(db)
    proposals_store: ProposalsStorePort = PgProposalsStore(db)

    def _runtime_factory(team_id: str) -> TeamRuntime:
        d = ws_root / team_id
        return TeamRuntime(
            team_id=team_id, storage=DiskStorage(d), git=GitRepo(d),
        )

    server = SyncServer(
        users=users,
        teams=teams,
        ownership_store=ownership_store,
        proposals_store=proposals_store,
        runtime_factory=_runtime_factory,
        secret=config.secret,
    )
    logger.info(
        "estado: Postgres (users/teams/ownership/proposals) + "
        "ws por equipo en %s", ws_root,
    )
    return server


def _build_dev_json(config: AppConfig) -> SyncServer:
    ws = config.base_dir / "workspace"
    users: UserStorePort = JsonUserStore(config.base_dir / "users.json")
    ownership_store: OwnershipStorePort = JsonOwnershipStore(
        config.base_dir / "ownership.json",
    )
    server = SyncServer(
        storage=DiskStorage(ws),
        users=users,
        ownership_store=ownership_store,
        secret=config.secret,
        git=GitRepo(ws),
    )
    logger.warning(
        "sin ORUX_DB_DSN: equipos EFÍMEROS (memoria). Sólo dev. "
        "estado en %s", config.base_dir,
    )
    return server


# Helper opcional para tests/migraciones que necesitan el factory
# (no usado por __main__.py todavía).
RuntimeFactory = Callable[[str], TeamRuntime | Awaitable[TeamRuntime]]
