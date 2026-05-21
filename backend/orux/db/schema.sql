-- Esquema real de Postgres (capa 15: sistema multi-equipo).
--
-- Frontera decidida con el usuario: la DB es autoritativa para METADATOS
-- (quién existe, qué equipos hay, quién es de qué equipo, quién es dueño de
-- qué). El CONTENIDO de los archivos NO vive acá: cada equipo tiene su repo
-- git real en disco (/data/ws/<team_id>/). Eso respeta la tesis "integra
-- con git, no lo reemplaza" y mantiene "git clone basta".
--
-- Idempotente a propósito (CREATE ... IF NOT EXISTS): el server lo aplica al
-- arrancar; no metemos Alembic todavía (una herramienta de migraciones es
-- otra capa, entra cuando un cambio de esquema real lo exija — misma regla
-- de dependencias del proyecto). Para ALTER que sí son no-idempotentes,
-- usamos `IF NOT EXISTS` o `DROP CONSTRAINT IF EXISTS` + recreación.

CREATE TABLE IF NOT EXISTS users (
    -- username YA viene normalizado (trim+minúsculas) desde la app: la
    -- unicidad es sobre la forma canónica, igual que en el UserStore JSON.
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    -- BACKEND-AUDIT-0002: contador de sesiones del usuario. Sirve para
    -- revocar sin rotar el secreto global del server (los tokens emitidos
    -- con epoch<actual dejan de valer). Default 0 = compat con users viejos.
    epoch         INTEGER NOT NULL DEFAULT 0,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Idempotente para DBs ya desplegadas pre-fix que no tenían `epoch`.
ALTER TABLE users ADD COLUMN IF NOT EXISTS epoch INTEGER NOT NULL DEFAULT 0;

CREATE TABLE IF NOT EXISTS teams (
    id         TEXT PRIMARY KEY,            -- id corto estable (no el nombre)
    nombre     TEXT NOT NULL,
    -- BACKEND-AUDIT-0172: ON DELETE RESTRICT en creador. Si alguien tiene
    -- equipos, no se puede borrar la cuenta sin antes traspasar/eliminar el
    -- equipo (la integridad referencial dispara, no se borra a ciegas).
    creador    TEXT NOT NULL REFERENCES users(username) ON DELETE RESTRICT,
    -- capa 22: free = puerta de entrada. BACKEND-AUDIT-0173: CHECK constraint
    -- para que el DB rechace planes inexistentes (defensa en profundidad
    -- frente a manipulaciones fuera de la app).
    plan       TEXT NOT NULL DEFAULT 'free' CHECK (plan IN ('free', 'premium')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Idempotente para DBs ya desplegadas (capa 15) que no tenían la columna:
-- CREATE IF NOT EXISTS no altera una tabla existente.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free';
-- Recrear el CHECK constraint si vino sin él (DBs pre-fix).
ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_plan_check;
ALTER TABLE teams ADD CONSTRAINT teams_plan_check CHECK (plan IN ('free', 'premium'));

CREATE TABLE IF NOT EXISTS team_members (
    team_id  TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    username TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    -- 'admin' = creó el equipo / lo gestiona; 'member' = invitado.
    rol      TEXT NOT NULL CHECK (rol IN ('admin', 'member')),
    joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, username)
);

CREATE TABLE IF NOT EXISTS invites (
    -- code de un solo uso: el admin lo genera, el invitado lo redime.
    code       TEXT PRIMARY KEY,
    team_id    TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    -- BACKEND-AUDIT-0172: SET NULL para no romper integridad cuando se
    -- borra una cuenta histórica que generó/usó la invitación. El histórico
    -- queda con NULL en lugar de violar la FK.
    creado_por TEXT REFERENCES users(username) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    usado_por  TEXT REFERENCES users(username) ON DELETE SET NULL,
    usado_at   TIMESTAMPTZ,
    -- BACKEND-AUDIT-0214: invitaciones caducan a los 7 días. Sin esto, un
    -- código de hace 2 años seguía siendo redimible (defensa contra códigos
    -- filtrados de logs/historial). El default cubre rows pre-fix: NULL
    -- significa "creada antes del fix, sigue sin caducar"; los nuevos sí.
    expires_at TIMESTAMPTZ
);
ALTER TABLE invites ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
-- Recrear FKs si vinieron sin ON DELETE (DBs pre-fix). Idempotente:
-- nombramos las constraints con un nombre estable que ALTER puede dropear.
ALTER TABLE invites DROP CONSTRAINT IF EXISTS invites_creado_por_fkey;
ALTER TABLE invites ADD CONSTRAINT invites_creado_por_fkey
    FOREIGN KEY (creado_por) REFERENCES users(username) ON DELETE SET NULL;
ALTER TABLE invites DROP CONSTRAINT IF EXISTS invites_usado_por_fkey;
ALTER TABLE invites ADD CONSTRAINT invites_usado_por_fkey
    FOREIGN KEY (usado_por) REFERENCES users(username) ON DELETE SET NULL;

CREATE TABLE IF NOT EXISTS ownership (
    -- Ownership AHORA es por equipo (antes era un JSON global). Un mismo
    -- path puede tener dueños distintos en equipos distintos: aislamiento.
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    path    TEXT NOT NULL,
    owner   TEXT NOT NULL REFERENCES users(username) ON DELETE RESTRICT,
    PRIMARY KEY (team_id, path)
);

CREATE INDEX IF NOT EXISTS idx_members_user ON team_members(username);
CREATE INDEX IF NOT EXISTS idx_invites_team ON invites(team_id);
-- BACKEND-AUDIT-0171: índice por owner para las consultas "qué archivos
-- son de X" (el panel admin, futuro purge de usuario). Sin él, seq scan.
CREATE INDEX IF NOT EXISTS idx_ownership_owner ON ownership(owner);
-- Cleanup de invitaciones expiradas: índice para que el barrido sea O(log n).
CREATE INDEX IF NOT EXISTS idx_invites_expires ON invites(expires_at)
    WHERE expires_at IS NOT NULL;

-- BACKEND-AUDIT-0204: tabla de versiones de esquema. Por ahora es solo
-- "this schema applied"; cuando aparezca Alembic, esta tabla es el origen.
CREATE TABLE IF NOT EXISTS schema_version (
    v          INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_version (v) VALUES (1) ON CONFLICT DO NOTHING;
