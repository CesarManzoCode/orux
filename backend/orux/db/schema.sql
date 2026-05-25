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
    -- capa 31: cobro POR ASIENTO. Id de la suscripción de Stripe del equipo
    -- (`sub_...`). NULL = equipo free, o premium puesto a mano por el
    -- operador (sin suscripción real). Con él, cuando entra un miembro
    -- nuevo a un equipo premium, el server ajusta la cantidad de asientos
    -- de la suscripción (factura = precio_unitario * miembros).
    stripe_subscription_id TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Idempotente para DBs ya desplegadas (capa 15) que no tenían la columna:
-- CREATE IF NOT EXISTS no altera una tabla existente.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS plan TEXT NOT NULL DEFAULT 'free';
-- Recrear el CHECK constraint si vino sin él (DBs pre-fix).
ALTER TABLE teams DROP CONSTRAINT IF EXISTS teams_plan_check;
ALTER TABLE teams ADD CONSTRAINT teams_plan_check CHECK (plan IN ('free', 'premium'));
-- capa 31: idempotente para DBs ya desplegadas que no tenían la columna.
ALTER TABLE teams ADD COLUMN IF NOT EXISTS stripe_subscription_id TEXT;

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
    -- BACKEND-AUDIT-0214 (fix completo 2026-05-24): invitaciones caducan
    -- a los 7 días. La encarnación anterior dejó la columna pero ni
    -- `crear_invitacion` la seteaba ni `redimir` la verificaba: cualquier
    -- código filtrado seguía vivo indefinidamente. Ahora:
    --   - DEFAULT en la columna (defensa en profundidad: un INSERT que
    --     olvide la columna sigue caducando).
    --   - `crear_invitacion` la setea explícitamente (auto-documentado).
    --   - `redimir` rechaza con TeamError("expirada") si ya pasó.
    --   - Backfill de abajo (idempotente) cubre rows pre-fix con
    --     `created_at + 7d` para que dejen de ser eternas en el upgrade.
    expires_at TIMESTAMPTZ NOT NULL DEFAULT (now() + interval '7 days')
);
-- Migración para DBs pre-fix donde la columna existía sin DEFAULT/NOT NULL:
-- 1) asegurar la columna; 2) backfill NULLs (= invitaciones eternas pre-fix)
-- con created_at+7d para que el ALTER SET NOT NULL no falle; 3) set DEFAULT;
-- 4) set NOT NULL. Todo idempotente: si ya está como queremos, los ALTER
-- no son destructivos y los UPDATE matchean 0 rows.
ALTER TABLE invites ADD COLUMN IF NOT EXISTS expires_at TIMESTAMPTZ;
UPDATE invites SET expires_at = created_at + interval '7 days'
    WHERE expires_at IS NULL;
ALTER TABLE invites ALTER COLUMN expires_at SET DEFAULT (now() + interval '7 days');
ALTER TABLE invites ALTER COLUMN expires_at SET NOT NULL;
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

-- Propuestas tentativas pendientes (capa 4). Hasta ahora vivían SOLO en
-- memoria del `TeamRuntime`: un deploy a mitad de "Ana editó, Kai por
-- aprobar" perdía el estado. Ahora se durabilizan: `Proposals` en memoria
-- sigue siendo el hot path; cada `put/pop/drop_path` se escribe-a-través
-- y al abrir un equipo el runtime se hidrata.
-- proposal_id es `path::author_id` (determinista, lo construye el server):
-- reeditar reemplaza en vez de duplicar. Por equipo: dos equipos pueden
-- tener un proposal_id idéntico sin colisión.
CREATE TABLE IF NOT EXISTS proposals (
    team_id     TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    proposal_id TEXT NOT NULL,
    path        TEXT NOT NULL,
    author_id   TEXT NOT NULL,
    author_name TEXT NOT NULL,
    content     TEXT NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (team_id, proposal_id)
);
-- `drop_path` borra todas las propuestas sobre un path al borrarse el
-- archivo. Sin índice por (team_id, path), seq scan sobre la tabla entera.
CREATE INDEX IF NOT EXISTS idx_proposals_team_path ON proposals(team_id, path);

-- Webhooks de Stripe ya aplicados (idempotencia por event_id). Stripe
-- garantiza entrega, NO orden ni unicidad: puede reentregar el mismo
-- event_id por timeout, o entregar `subscription.deleted` ANTES que el
-- `subscription.updated` por demora de red. Con esta tabla, antes de
-- aplicar miramos si ese event_id ya se procesó; si sí, ignoramos.
-- Garantía: cada evento de Stripe se aplica EXACTAMENTE UNA VEZ.
-- Pruned periódicamente: tras 30 días un evento ya no llega de Stripe.
CREATE TABLE IF NOT EXISTS processed_webhooks (
    event_id     TEXT PRIMARY KEY,
    processed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- Para el barrido de viejos (purge >30 días): O(log n) en vez de seq scan.
CREATE INDEX IF NOT EXISTS idx_webhooks_processed ON processed_webhooks(processed_at);

-- BACKEND-AUDIT-0204: tabla de versiones de esquema. Por ahora es solo
-- "this schema applied"; cuando aparezca Alembic, esta tabla es el origen.
CREATE TABLE IF NOT EXISTS schema_version (
    v          INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO schema_version (v) VALUES (1) ON CONFLICT DO NOTHING;
