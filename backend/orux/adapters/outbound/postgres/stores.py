"""Adaptadores Postgres de usuarios, ownership, propuestas y webhooks.
MISMA semántica que sus contrapartes en memoria; el server no sabe con cuál
habla. NO importan asyncpg (sólo usan el `Database` inyectado): `import`
seguro en el sandbox. Se ejercitan de verdad en el VPS (paso 3b), no acá.
"""

from __future__ import annotations

from orux.domain.identity.passwords import (
    MARCADOR_EXTERNO,
    hash_password,
    verificar_password,
)
from orux.domain.identity.store import normalizar, validar_nuevo_usuario
from orux.domain.protocol import Proposal


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

    async def borrar(self, username: str) -> bool:
        """Capa 23: borra un usuario. True si se borró, False si no existía.
        Lanza `ValueError` si el usuario es creador de algún team o tiene
        archivos en `ownership`: ambas FKs son ON DELETE RESTRICT, así que
        el DELETE crudo tiraría ForeignKeyViolationError; preferimos un
        error claro y temprano. Transacción para evitar TOCTOU entre el
        chequeo y el borrado."""
        u = normalizar(username)
        async with self._db.tx() as con:
            n_teams = await con.fetchval(
                "SELECT count(*) FROM teams WHERE creador=$1", u,
            )
            if n_teams:
                raise ValueError(
                    f"el usuario es creador de {n_teams} equipo(s); "
                    "borra los equipos primero"
                )
            n_own = await con.fetchval(
                "SELECT count(*) FROM ownership WHERE owner=$1", u,
            )
            if n_own:
                raise ValueError(
                    f"el usuario es dueño de {n_own} archivo(s) en algún "
                    "equipo; reasigna o borra los equipos primero"
                )
            v = await con.fetchval(
                "DELETE FROM users WHERE username=$1 RETURNING username", u,
            )
            return v is not None

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


class PgProposalsStore:
    """Persistencia de propuestas POR EQUIPO. Igual que `PgOwnershipStore`:
    el hot path sigue siendo el dict en memoria del runtime; este store
    sólo CARGA al abrir el equipo y se escribe-a-través tras cada mutación
    (put / pop / drop_path / reset por clone destructivo).

    Antes vivían sólo en memoria del `TeamRuntime`: un deploy a mitad de
    "Ana editó, Kai por aprobar" perdía el estado. Con esto, un restart del
    server reconstruye las propuestas pendientes y la conversación sigue.

    El `proposal_id` (`path::author_id`) es determinista: el UPSERT
    reemplaza la propuesta vieja si el autor reedita el mismo path —misma
    semántica que `Proposals.put` en memoria.
    """

    def __init__(self, db) -> None:
        self._db = db

    async def cargar(self, team_id: str) -> list[Proposal]:
        rows = await self._db.fetch(
            "SELECT proposal_id, path, author_id, author_name, content "
            "FROM proposals WHERE team_id=$1",
            team_id,
        )
        return [
            Proposal(
                id=r["proposal_id"],
                path=r["path"],
                author_id=r["author_id"],
                author_name=r["author_name"],
                content=r["content"],
            )
            for r in rows
        ]

    async def guardar(self, team_id: str, prop: Proposal) -> None:
        """UPSERT de una propuesta. Reemplazo en reedición = mismo
        proposal_id, content nuevo (`DO UPDATE`)."""
        await self._db.execute(
            "INSERT INTO proposals "
            "(team_id, proposal_id, path, author_id, author_name, content) "
            "VALUES ($1,$2,$3,$4,$5,$6) "
            "ON CONFLICT (team_id, proposal_id) "
            "DO UPDATE SET content = EXCLUDED.content, "
            "              author_name = EXCLUDED.author_name",
            team_id, prop.id, prop.path,
            prop.author_id, prop.author_name, prop.content,
        )

    async def borrar(self, team_id: str, proposal_id: str) -> None:
        """Al aprobar/rechazar (Resolve)."""
        await self._db.execute(
            "DELETE FROM proposals WHERE team_id=$1 AND proposal_id=$2",
            team_id, proposal_id,
        )

    async def borrar_path(self, team_id: str, path: str) -> None:
        """Al borrarse el archivo (Delete): todas las propuestas sobre
        ese path quedan moot."""
        await self._db.execute(
            "DELETE FROM proposals WHERE team_id=$1 AND path=$2",
            team_id, path,
        )

    async def borrar_todo(self, team_id: str) -> None:
        """Tras un clone destructivo: el workspace es otro repo, las
        propuestas viejas ya no aplican."""
        await self._db.execute(
            "DELETE FROM proposals WHERE team_id=$1", team_id,
        )


class PgWebhooksStore:
    """Idempotencia de webhooks de Stripe por event_id.

    Stripe garantiza ENTREGA, no orden ni unicidad. Sin esto:
    - un webhook reentregado por timeout aplica el cambio dos veces (con
      `actualizar_suscripcion` que fija valores no rompe nada en la
      práctica, pero loguea ruido y dispara side-effects extra);
    - peor: si `customer.subscription.deleted` llega DESPUÉS de un evento
      más nuevo por demora de red, el equipo queda en `free` aunque siga
      pagando. (En la práctica acá no hay update intermedio mapeado a un
      cambio de plan, pero sí pasa con secuencias raras del dashboard).

    Esta tabla resuelve la primera (idempotencia exacta por event_id) y
    da base para resolver la segunda (ordenar por `created` del evento).
    Hoy resuelve la primera; la segunda se aborda al haber un caso real.
    """

    def __init__(self, db) -> None:
        self._db = db

    async def marcar(self, event_id: str) -> bool:
        """True si es la PRIMERA vez (insertó); False si ya estaba (replay).

        Usa `INSERT ... ON CONFLICT DO NOTHING RETURNING event_id`: la
        decisión "primera o replay" es atómica (no hay carrera entre
        SELECT y INSERT — dos workers procesando el mismo webhook a la
        vez ven una decisión consistente)."""
        v = await self._db.fetchval(
            "INSERT INTO processed_webhooks (event_id) VALUES ($1) "
            "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
            event_id,
        )
        return v is not None

    async def purgar(self, antes_de_segundos: int = 30 * 24 * 3600) -> int:
        """Borra eventos procesados hace más de `antes_de_segundos`.
        Stripe ya no reentrega tras ~30 días, así que un event_id
        olvidado a los 30 no rompe la idempotencia en la práctica.
        Devuelve cuántos se borraron (para loguear)."""
        res = await self._db.execute(
            "DELETE FROM processed_webhooks "
            "WHERE processed_at < now() - ($1 || ' seconds')::interval",
            str(int(antes_de_segundos)),
        )
        try:
            return int(res.split()[-1])
        except (ValueError, IndexError):
            return 0
