"""Adaptadores Postgres de usuarios y ownership. MISMA semántica que sus
contrapartes en memoria; el server no sabe con cuál habla. NO importan
asyncpg (sólo usan el `Database` inyectado): `import` seguro en el sandbox.
Se ejercitan de verdad en el VPS (paso 3b), no acá.
"""

from __future__ import annotations

from ..identity.passwords import (
    MARCADOR_EXTERNO,
    hash_password,
    verificar_password,
)
from ..identity.store import normalizar, validar_nuevo_usuario


class PgUserStore:
    """Usuarios en Postgres. Async (igual que PgTeamStore): el server hace
    `await`. Misma forma que `identity.UserStore` (existe/registrar/
    verificar), normalizando el usuario igual."""

    def __init__(self, db) -> None:
        self._db = db  # orux.db.Database

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
        # `validar_nuevo_usuario` aplica las reglas de formato.
        u = validar_nuevo_usuario(username)
        # BACKEND-AUDIT-0178: `INSERT ... ON CONFLICT DO NOTHING` evita la
        # carrera entre dos requests con mismo username (ambos pasaban
        # `existe()`, el segundo violaba PK con UniqueViolationError sin
        # try/except). Con `RETURNING username` distinguimos "inserté" de
        # "ya existía" — y NO levantamos UniqueViolation porque no sale del DB.
        res = await self._db.fetchval(
            "INSERT INTO users (username, password_hash) VALUES ($1,$2) "
            "ON CONFLICT (username) DO NOTHING RETURNING username",
            u, hash_password(password),  # valida password vacía / corta / larga
        )
        if res is None:
            raise ValueError("ese usuario ya existe")
        return u

    async def epoch(self, username: str) -> int:
        """Contador de sesiones del usuario (BACKEND-AUDIT-0002). 0 para
        usuarios pre-fix (la columna tiene default 0)."""
        v = await self._db.fetchval(
            "SELECT epoch FROM users WHERE username=$1",
            normalizar(username),
        )
        return int(v) if v is not None else 0

    async def revocar_sesiones(self, username: str) -> None:
        """Incrementa el epoch (BACKEND-AUDIT-0002)."""
        await self._db.execute(
            "UPDATE users SET epoch = epoch + 1 WHERE username=$1",
            normalizar(username),
        )

    async def asegurar_externo(self, username: str) -> str:
        """Idem `UserStore.asegurar_externo` pero en Postgres. Idempotente
        vía `ON CONFLICT DO NOTHING` (atómico, sin carrera entre dos logins
        OAuth simultáneos del mismo usuario)."""
        u = normalizar(username)
        if not u:
            raise ValueError("usuario inválido")
        await self._db.execute(
            "INSERT INTO users (username, password_hash) VALUES ($1,$2) "
            "ON CONFLICT (username) DO NOTHING",
            u, MARCADOR_EXTERNO,
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
        """Reemplazo del set del equipo. El mapa en memoria es la verdad; lo
        volcamos. Implementación con diff sobre el estado existente para
        evitar la write amplification de DELETE+INSERT completo
        (BACKEND-AUDIT-0177): si el cambio es 1 path de 5000, hacemos 1 UPSERT,
        no 5000 INSERTs. Para sets pequeños el costo de leer + comparar es
        despreciable; para grandes el ahorro es 100x."""
        async with self._db.tx() as con:
            rows = await con.fetch(
                "SELECT path, owner FROM ownership WHERE team_id=$1", team_id
            )
            previos = {r["path"]: r["owner"] for r in rows}
            a_borrar = [p for p in previos if p not in owners]
            a_upsert = [
                (team_id, p, o) for p, o in owners.items()
                if previos.get(p) != o
            ]
            if a_borrar:
                await con.executemany(
                    "DELETE FROM ownership WHERE team_id=$1 AND path=$2",
                    [(team_id, p) for p in a_borrar],
                )
            if a_upsert:
                await con.executemany(
                    "INSERT INTO ownership (team_id, path, owner) "
                    "VALUES ($1,$2,$3) ON CONFLICT (team_id, path) "
                    "DO UPDATE SET owner = EXCLUDED.owner",
                    a_upsert,
                )
