# Adapter: Postgres

`backend/orux/adapters/outbound/postgres/` es el adapter de producción para los stores que requieren DB durable.

## Archivos

| Archivo | Qué hace |
|---|---|
| `pool.py` | `Database` — wrapper sobre `asyncpg.Pool`. Conexión, helpers, transacciones, healthcheck. |
| `schema.sql` | Schema idempotente. Se aplica en cada arranque (CREATE TABLE IF NOT EXISTS, ALTER ADD COLUMN IF NOT EXISTS). |
| `stores.py` | `PgUserStore`, `PgOwnershipStore`, `PgProposalsStore`, `PgWebhooksStore`. |
| `teams.py` | `PgTeamStore` (separado por tamaño del SQL). |

Re-export desde `orux.db` y `orux.teams.pg` para backward compat (callers viejos siguen funcionando).

## `Database` (`pool.py`)

```python
class Database:
    @classmethod
    async def conectar(cls, dsn: str) -> "Database":
        # Crea el pool asyncpg. Aplica schema.sql idempotente.
    
    async def fetchval(self, sql, *args) -> Any: ...
    async def fetchrow(self, sql, *args) -> dict | None: ...
    async def fetch(self, sql, *args) -> list[dict]: ...
    async def execute(self, sql, *args) -> str: ...
    
    @asynccontextmanager
    async def tx(self) -> Connection:
        # Transacción explícita: async with db.tx() as con: ...
    
    async def ping(self) -> bool:
        # Healthcheck: SELECT 1.
    
    async def close(self) -> None: ...
```

**Config via env**:

- `ORUX_DB_DSN`: `postgresql://user:pass@host:port/dbname`.
- `ORUX_DB_POOL_MIN` (default 2), `ORUX_DB_POOL_MAX` (default 10).
- `ORUX_DB_TIMEOUT` (default 10s) — para queries individuales.

**Aplicación idempotente del schema**: cada vez que `conectar()` corre, ejecuta `schema.sql`. Las sentencias son `CREATE ... IF NOT EXISTS` y `ALTER ... ADD COLUMN IF NOT EXISTS` para que se puedan correr N veces sin romper.

## Schema (`schema.sql`)

### `users`

```sql
CREATE TABLE IF NOT EXISTS users (
    username       TEXT PRIMARY KEY,
    password_hash  TEXT NOT NULL,    -- PBKDF2 o MARCADOR_EXTERNO (OAuth)
    epoch          INTEGER NOT NULL DEFAULT 0,  -- BACKEND-AUDIT-0002 revocación
    created_at     TIMESTAMPTZ DEFAULT now()
);
```

### `teams`

```sql
CREATE TABLE IF NOT EXISTS teams (
    id                       TEXT PRIMARY KEY,
    nombre                   TEXT NOT NULL,
    creador                  TEXT NOT NULL REFERENCES users(username) ON DELETE RESTRICT,
    plan                     TEXT NOT NULL DEFAULT 'free',
    stripe_subscription_id   TEXT,              -- nullable: free o premium manual
    created_at               TIMESTAMPTZ DEFAULT now()
);
```

`ON DELETE RESTRICT` en `creador`: para borrar un usuario que es creador de equipos, primero hay que borrar los equipos. `borrar_usuario` use case lo levanta como `ValueError` legible.

### `team_members`

```sql
CREATE TABLE IF NOT EXISTS team_members (
    team_id   TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    username  TEXT NOT NULL REFERENCES users(username) ON DELETE RESTRICT,
    rol       TEXT NOT NULL CHECK (rol IN ('admin', 'member')),
    PRIMARY KEY (team_id, username)
);
CREATE INDEX IF NOT EXISTS idx_members_user ON team_members (username);
```

`ON DELETE CASCADE` en `team_id`: borrar un equipo barre sus miembros.

### `invites`

```sql
CREATE TABLE IF NOT EXISTS invites (
    code          TEXT PRIMARY KEY,
    team_id       TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    creado_por    TEXT NOT NULL,
    usado_por     TEXT,                          -- nullable: aún sin usar
    usado_at      TIMESTAMPTZ,
    expires_at    TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days')
);
```

**TTL en el default + override explícito** (defensa en profundidad): `MemTeamStore` setea explícitamente con `now + INVITE_TTL_DAYS`; el DEFAULT es backup si en el futuro alguien hace INSERT sin pasar `expires_at`.

### `ownership`

```sql
CREATE TABLE IF NOT EXISTS ownership (
    team_id  TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    path     TEXT NOT NULL,
    owner    TEXT NOT NULL REFERENCES users(username) ON DELETE RESTRICT,
    PRIMARY KEY (team_id, path)
);
```

`ON DELETE RESTRICT` en `owner`: el use case `borrar_usuario` levanta ValueError si el usuario tiene ownership pendiente.

### `proposals`

```sql
CREATE TABLE IF NOT EXISTS proposals (
    team_id      TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    proposal_id  TEXT NOT NULL,        -- path::author_id (determinista)
    path         TEXT NOT NULL,
    author_id    TEXT NOT NULL,
    author_name  TEXT NOT NULL,
    content      TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (team_id, proposal_id)
);
```

UPSERT en `PgProposalsStore.guardar` reemplaza la propuesta si el autor re-edita el mismo path (misma semántica que `Proposals.put` en memoria).

### `processed_webhooks`

```sql
CREATE TABLE IF NOT EXISTS processed_webhooks (
    event_id      TEXT PRIMARY KEY,
    processed_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

Solo Stripe (hoy). Si entra otro proveedor con webhooks, agregar columna `provider`.

## `PgUserStore` (`stores.py`)

```python
class PgUserStore:
    def __init__(self, db: Database): ...
    
    async def existe(self, username) -> bool
    async def usuarios(self) -> list[str]                   # Capa 23 (operador)
    async def registrar(self, username, password) -> str    # Atomic UPSERT
    async def asegurar_externo(self, username) -> str       # OAuth
    async def epoch(self, username) -> int                  # Revocación
    async def revocar_sesiones(self, username) -> None
    async def borrar(self, username) -> bool                # Tx + check FK
    async def verificar(self, username, password) -> bool
```

**Atomic UPSERT** en `registrar` (BACKEND-AUDIT-0178):

```sql
INSERT INTO users (username, password_hash) VALUES ($1, $2)
ON CONFLICT (username) DO NOTHING RETURNING username
```

Sin esto, dos requests con el mismo username pasaban `existe()` y el segundo violaba PK con `UniqueViolationError`. Con `RETURNING username` distinguimos "inserté" de "ya existía" sin try/except y la decisión es atómica.

**Tx + check FK** en `borrar` (Capa 23):

```python
async with self._db.tx() as con:
    n_teams = await con.fetchval("SELECT count(*) FROM teams WHERE creador=$1", u)
    if n_teams:
        raise ValueError(f"el usuario es creador de {n_teams} equipo(s); ...")
    n_own = await con.fetchval("SELECT count(*) FROM ownership WHERE owner=$1", u)
    if n_own:
        raise ValueError(f"el usuario es dueño de {n_own} archivo(s); ...")
    v = await con.fetchval("DELETE FROM users WHERE username=$1 RETURNING username", u)
    return v is not None
```

Tx para evitar TOCTOU entre el chequeo y el borrado. Sin esto, alguien podría agregar al usuario como creador entre el `count(*)` y el `DELETE`.

## `PgOwnershipStore`

```python
class PgOwnershipStore:
    async def cargar(self, team_id) -> dict[str, str]
    async def guardar(self, team_id, owners: dict[str, str]) -> None
```

**Diff sobre el estado existente** (BACKEND-AUDIT-0177):

```python
async def guardar(self, team_id, owners):
    async with self._db.tx() as con:
        rows = await con.fetch("SELECT path, owner FROM ownership WHERE team_id=$1", team_id)
        previos = {r["path"]: r["owner"] for r in rows}
        a_borrar = [p for p in previos if p not in owners]
        a_upsert = [(team_id, p, o) for p, o in owners.items() if previos.get(p) != o]
        # DELETE solo los que se fueron
        # UPSERT solo los que cambiaron
```

Sin esto, un cambio de 1 path en un equipo con 5000 paths hacía DELETE+INSERT de los 5000 (write amplification). Con diff: 1 UPSERT.

Para sets pequeños el costo de leer + comparar es despreciable; para grandes el ahorro es 100x.

## `PgProposalsStore`

UPSERT en `guardar` (reemplaza si reedición del mismo path):

```sql
INSERT INTO proposals (team_id, proposal_id, path, author_id, author_name, content)
VALUES ($1, $2, $3, $4, $5, $6)
ON CONFLICT (team_id, proposal_id) DO UPDATE
  SET content = EXCLUDED.content,
      author_name = EXCLUDED.author_name
```

`borrar_path(team_id, path)`: al borrar el archivo, todas las propuestas sobre ese path quedan moot.

`borrar_todo(team_id)`: tras clone destructivo (workspace es otro repo, propuestas viejas no aplican).

## `PgWebhooksStore`

Idempotencia de webhooks Stripe.

```python
async def marcar(self, event_id) -> bool:
    """True = primera vez (insertó), False = ya estaba (replay)."""
    v = await self._db.fetchval(
        "INSERT INTO processed_webhooks (event_id) VALUES ($1) "
        "ON CONFLICT (event_id) DO NOTHING RETURNING event_id",
        event_id,
    )
    return v is not None

async def purgar(self, antes_de_segundos=30*24*3600) -> int:
    """Borra eventos procesados hace más de N segundos (default 30 días).
    Stripe ya no reentrega tras ~30 días, así que es seguro purgar.
    """
```

La purga corre cada 24h vía `_purgar_webhooks_periodico` en el lifespan de la app HTTP.

## `PgTeamStore` (`teams.py`)

La superficie larga del `TeamStorePort` (equipos / membresía / invitaciones / suscripciones).

### `crear_equipo` — tx con reintentos

```python
async def crear_equipo(self, nombre, creador):
    nombre = validar_nombre_equipo(nombre)
    async with self._db.tx() as con:
        tid = _id_equipo()
        for _ in range(16):  # BACKEND-AUDIT-0179
            if not await con.fetchval("SELECT 1 FROM teams WHERE id=$1", tid):
                break
            tid = _id_equipo()
        else:
            raise TeamError("no se pudo generar id de equipo único")
        await con.execute("INSERT INTO teams ...")
        await con.execute("INSERT INTO team_members ...")  # creador como admin
    return {"id": tid, "nombre": nombre}
```

Tope de 16 reintentos para no congelar la tx si un bug en `_id_equipo` devuelve siempre el mismo.

### `redimir` — FOR UPDATE + verificación atómica de plan

```python
async def redimir(self, code, usuario):
    u = normalizar(usuario)
    async with self._db.tx() as con:
        inv = await con.fetchrow(
            "SELECT team_id, usado_por, "
            "  (expires_at IS NOT NULL AND expires_at <= now()) AS expirada "
            "FROM invites WHERE code=$1 FOR UPDATE",
            code,
        )
        if inv is None or inv["usado_por"] is not None:
            return None
        if inv["expirada"]:
            raise TeamError("esta invitación expiró — pedile al admin una nueva")
        # cap del plan dentro de la tx
        ya = await con.fetchval("SELECT 1 FROM team_members ...")
        if not ya:
            n = await con.fetchval("SELECT count(*) FROM team_members ...")
            if not permite_miembro(plan, n):
                raise TeamError("este equipo llegó al límite del plan free ...")
        await con.execute("UPDATE invites SET usado_por=$1 WHERE code=$2", u, code)
        await con.execute("INSERT INTO team_members ... ON CONFLICT DO NOTHING")
```

Decisiones:

- **`FOR UPDATE`** en el SELECT del invite: lockea la fila hasta el commit. Sin esto, dos clientes con el mismo código pasaban ambos el check y ambos terminaban como miembro.
- **Chequeo de expiración en SQL** (no en Python): atómico con el `FOR UPDATE`.
- **Cap del plan dentro de la tx**: si rechaza, rollback ⇒ el código NO se consume (reintentás tras el upgrade).

### `equipos_de(usuario)` — para el Lobby

```sql
SELECT t.id, t.nombre, t.plan, m.rol,
       (SELECT count(*) FROM team_members mm WHERE mm.team_id = t.id) AS miembros
FROM team_members m JOIN teams t ON t.id = m.team_id
WHERE m.username = $1
ORDER BY t.nombre
```

Incluye `plan` (Hub muestra el badge + upgrade) y `miembros` (capa 31: para mostrar los asientos). Subconsulta correlacionada barata por el índice `idx_members_user`.

## Cómo se cablea (composition root)

```python
# composition.py
async def _build_postgres(config):
    db = await Database.conectar(config.dsn)
    return SyncServer(
        users=PgUserStore(db),
        teams=PgTeamStore(db),
        ownership_store=PgOwnershipStore(db),
        proposals_store=PgProposalsStore(db),
        runtime_factory=_runtime_factory,
        secret=config.secret,
    )
```

El proceso `api` HTTP también recibe `Database`:

```python
# adapters/inbound/http/__main__.py
db = await Database.conectar(dsn)
app = crear_app(
    users=PgUserStore(db),
    teams=PgTeamStore(db),
    webhooks=PgWebhooksStore(db),
)
```

Son dos procesos separados; cada uno tiene su propio `Database` (su propio pool asyncpg). Comparten la DB física pero no el cliente.
