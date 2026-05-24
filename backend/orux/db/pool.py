"""Pool de conexiones a Postgres + aplicación idempotente del esquema.

Pieza fina a propósito: un pool de asyncpg y wrappers. Las reglas del
dominio NO viven acá (viven en los stores). `apply_schema` corre
`schema.sql` (todo `IF NOT EXISTS`) al conectar: sin Alembic todavía
—una herramienta de migraciones entra cuando un cambio de esquema real lo
exija, misma regla de dependencias del proyecto—.

Hardening (auditoría):
- BACKEND-AUDIT-0174 / -0208: `command_timeout` por query y
  `max_inactive_connection_lifetime`. Sin esto un query lento agotaba el
  pool (10 conexiones máx) y el server entero se quedaba sin DB.
- BACKEND-AUDIT-0176: el esquema se aplica dentro de una transacción
  (parcial-on-failure pasa a rollback completo; ya es idempotente, así que
  esto es defensa en profundidad).
- BACKEND-AUDIT-0194: si `_aplicar_schema` falla, cerramos el pool antes
  de propagar (sin esto el pool quedaba colgado).
- BACKEND-AUDIT-0175: tamaños configurables por env.
"""

from __future__ import annotations

import logging
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

from .._env import _env_int

logger = logging.getLogger(__name__)

_SCHEMA = Path(__file__).with_name("schema.sql")


class Database:
    """Envuelve un pool de asyncpg. `conectar` es el único punto que importa
    asyncpg (perezoso): sin DSN nadie llama esto y el server sigue sin DB."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def conectar(cls, dsn: str) -> "Database":
        # Import perezoso: que `import orux.db` no exija asyncpg instalado
        # (en el sandbox no lo está; los tests no llaman acá).
        import asyncpg  # noqa: PLC0415

        pool_min = _env_int("ORUX_DB_POOL_MIN", 1, 1, 100)
        pool_max = _env_int("ORUX_DB_POOL_MAX", 10, 1, 200)
        cmd_to = _env_int("ORUX_DB_CMD_TIMEOUT", 30, 1, 600)
        idle = _env_int("ORUX_DB_IDLE_SEC", 300, 30, 3600)
        # Loguear sin el DSN: tiene credenciales. Solo los parámetros del
        # pool, que son útiles para diagnosticar saturación.
        logger.info(
            "Postgres: conectando pool min=%d max=%d cmd_timeout=%ds idle=%ds",
            pool_min, pool_max, cmd_to, idle,
        )
        t0 = time.monotonic()
        try:
            pool = await asyncpg.create_pool(
                dsn,
                min_size=pool_min,
                max_size=pool_max,
                command_timeout=cmd_to,
                max_inactive_connection_lifetime=idle,
            )
        except Exception:
            # Sin contexto operacional, el operador no sabe si falló por DSN
            # malformado, por DB caída, o por límites del pool. NO loguear el
            # DSN: trae credenciales (BACKEND-AUDIT-0291).
            logger.exception(
                "Postgres: create_pool falló (pool_min=%d, pool_max=%d, "
                "cmd_timeout=%ds, idle=%ds, elapsed=%.0fms)",
                pool_min, pool_max, cmd_to, idle,
                (time.monotonic() - t0) * 1000.0,
            )
            raise
        db = cls(pool)
        try:
            await db._aplicar_schema()
        except Exception:
            # Si la migración falla, no dejar el pool huérfano (resource leak).
            # Best-effort el cierre: si pool.close() también explota (DB caída
            # durante schema), no enmascarar la excepción original.
            logger.exception(
                "Postgres: _aplicar_schema falló (schema=%s) — cerrando pool",
                _SCHEMA,
            )
            try:
                await pool.close()
            except Exception:  # noqa: BLE001
                logger.exception("Postgres: pool.close() también falló")
            raise
        logger.info(
            "Postgres: pool listo y esquema aplicado en %.0f ms",
            (time.monotonic() - t0) * 1000.0,
        )
        return db

    async def _aplicar_schema(self) -> None:
        sql = _SCHEMA.read_text(encoding="utf-8")
        async with self._pool.acquire() as con:
            # asyncpg ejecuta múltiples sentencias en una si no hay args
            # (protocolo simple), y schema.sql es idempotente: arrancar dos
            # veces no rompe nada. Aun así corremos dentro de transacción
            # para que un fallo a mitad haga rollback (BACKEND-AUDIT-0176).
            async with con.transaction():
                await con.execute(sql)

    async def fetch(self, sql: str, *args: Any) -> list[Any]:
        async with self._pool.acquire() as con:
            return await con.fetch(sql, *args)

    async def fetchrow(self, sql: str, *args: Any) -> Any | None:
        async with self._pool.acquire() as con:
            return await con.fetchrow(sql, *args)

    async def fetchval(self, sql: str, *args: Any) -> Any:
        async with self._pool.acquire() as con:
            return await con.fetchval(sql, *args)

    async def execute(self, sql: str, *args: Any) -> str:
        async with self._pool.acquire() as con:
            return await con.execute(sql, *args)

    @asynccontextmanager
    async def tx(self):
        """Conexión dentro de una transacción, para operaciones de varias
        sentencias que deben ser atómicas (crear equipo, redimir código)."""
        async with self._pool.acquire() as con:
            async with con.transaction():
                yield con

    async def cerrar(self) -> None:
        logger.info("Postgres: cerrando pool")
        await self._pool.close()

    async def ping(self) -> bool:
        """Healthcheck real (BACKEND-AUDIT-0285): `SELECT 1` contra el pool.
        Lo usa el healthcheck del contenedor; sin esto el HC reportaba 200
        aunque la DB estuviese caída."""
        try:
            val = await self.fetchval("SELECT 1")
            return val == 1
        except Exception as e:  # noqa: BLE001 - el HC nunca propaga
            logger.warning("Postgres: ping falló (%r)", e)
            return False
