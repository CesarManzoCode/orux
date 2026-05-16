"""Pool de conexiones a Postgres + aplicación idempotente del esquema.

Pieza fina a propósito: un pool de asyncpg y wrappers. Las reglas del
dominio NO viven acá (viven en los stores). `apply_schema` corre
`schema.sql` (todo `IF NOT EXISTS`) al conectar: sin Alembic todavía
—una herramienta de migraciones entra cuando un cambio de esquema real lo
exija, misma regla de dependencias del proyecto—.
"""

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any

_SCHEMA = Path(__file__).with_name("schema.sql")


class Database:
    """Envuelve un pool de asyncpg. `conectar` es el único punto que importa
    asyncpg (perezoso): sin DSN nadie llama esto y el server sigue sin DB."""

    def __init__(self, pool: Any) -> None:
        self._pool = pool

    @classmethod
    async def conectar(cls, dsn: str) -> "Database":
        # Import perezoso: que `import laidea.db` no exija asyncpg instalado
        # (en el sandbox no lo está; los tests no llaman acá).
        import asyncpg  # noqa: PLC0415

        pool = await asyncpg.create_pool(dsn, min_size=1, max_size=10)
        db = cls(pool)
        await db._aplicar_schema()
        return db

    async def _aplicar_schema(self) -> None:
        sql = _SCHEMA.read_text(encoding="utf-8")
        async with self._pool.acquire() as con:
            # asyncpg ejecuta múltiples sentencias en una si no hay args
            # (protocolo simple), y schema.sql es idempotente: arrancar dos
            # veces no rompe nada.
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
        await self._pool.close()
