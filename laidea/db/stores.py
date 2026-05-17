"""Adaptadores Postgres de usuarios y ownership. MISMA semántica que sus
contrapartes en memoria; el server no sabe con cuál habla. NO importan
asyncpg (sólo usan el `Database` inyectado): `import` seguro en el sandbox.
Se ejercitan de verdad en el VPS (paso 3b), no acá.
"""

from __future__ import annotations

from ..identity.passwords import hash_password, verificar_password
from ..identity.store import normalizar


class PgUserStore:
    """Usuarios en Postgres. Async (igual que PgTeamStore): el server hace
    `await`. Misma forma que `identity.UserStore` (existe/registrar/
    verificar), normalizando el usuario igual."""

    def __init__(self, db) -> None:
        self._db = db  # laidea.db.Database

    async def existe(self, username: str) -> bool:
        return bool(await self._db.fetchval(
            "SELECT 1 FROM users WHERE username=$1", normalizar(username)
        ))

    async def usuarios(self) -> list[str]:
        """Capa 23: todos los usuarios (consola de operador)."""
        rows = await self._db.fetch(
            "SELECT username FROM users ORDER BY username"
        )
        return [r["username"] for r in rows]

    async def registrar(self, username: str, password: str) -> str:
        u = normalizar(username)
        if not u:
            raise ValueError("usuario inválido")
        if await self.existe(u):
            raise ValueError("ese usuario ya existe")
        await self._db.execute(
            "INSERT INTO users (username, password_hash) VALUES ($1,$2)",
            u, hash_password(password),  # valida password vacía
        )
        return u

    async def verificar(self, username: str, password: str) -> bool:
        reg = await self._db.fetchval(
            "SELECT password_hash FROM users WHERE username=$1",
            normalizar(username),
        )
        if reg is None:
            return False
        return verificar_password(password, reg)


class PgOwnershipStore:
    """Persistencia de ownership POR EQUIPO en Postgres. No es el `Ownership`
    del hot path (ese sigue siendo el mapa en memoria del runtime, síncrono);
    esto sólo lo CARGA al abrir el equipo y lo GUARDA tras cada cambio.
    Mantener el mapa autoritativo en memoria y escribir-a-través evita volver
    async todo el bucle de mensajes (decisión de diseño ya acordada, no atajo).
    """

    def __init__(self, db) -> None:
        self._db = db

    async def cargar(self, team_id: str) -> dict[str, str]:
        rows = await self._db.fetch(
            "SELECT path, owner FROM ownership WHERE team_id=$1", team_id
        )
        return {r["path"]: r["owner"] for r in rows}

    async def guardar(self, team_id: str, owners: dict[str, str]) -> None:
        # Reemplazo completo del set del equipo: el mapa en memoria es la
        # verdad; lo volcamos entero (es chico — 2-50 personas, un repo).
        async with self._db.tx() as con:
            await con.execute(
                "DELETE FROM ownership WHERE team_id=$1", team_id
            )
            if owners:
                await con.executemany(
                    "INSERT INTO ownership (team_id, path, owner) "
                    "VALUES ($1,$2,$3)",
                    [(team_id, p, o) for p, o in owners.items()],
                )
