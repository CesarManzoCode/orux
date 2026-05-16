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
-- de dependencias del proyecto).

CREATE TABLE IF NOT EXISTS users (
    -- username YA viene normalizado (trim+minúsculas) desde la app: la
    -- unicidad es sobre la forma canónica, igual que en el UserStore JSON.
    username      TEXT PRIMARY KEY,
    password_hash TEXT NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS teams (
    id         TEXT PRIMARY KEY,            -- id corto estable (no el nombre)
    nombre     TEXT NOT NULL,
    creador    TEXT NOT NULL REFERENCES users(username),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

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
    creado_por TEXT NOT NULL REFERENCES users(username),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    usado_por  TEXT REFERENCES users(username),   -- NULL = sin usar
    usado_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS ownership (
    -- Ownership AHORA es por equipo (antes era un JSON global). Un mismo
    -- path puede tener dueños distintos en equipos distintos: aislamiento.
    team_id TEXT NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
    path    TEXT NOT NULL,
    owner   TEXT NOT NULL REFERENCES users(username),
    PRIMARY KEY (team_id, path)
);

CREATE INDEX IF NOT EXISTS idx_members_user ON team_members(username);
CREATE INDEX IF NOT EXISTS idx_invites_team ON invites(team_id);
