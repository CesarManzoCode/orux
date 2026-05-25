# Development: Setup local

Cómo correr el backend en tu máquina sin Docker.

## Requisitos

- **Python 3.11+** (el código usa typing moderno: `dict[str, int]`, `X | None`, etc.).
- **git** (no `git2`, el binario clásico).
- Opcionales (para LSP funcionando):
  - `pyright-python` (vía `pip install`).
  - `typescript-language-server` (npm global).
  - `gopls` (Go).
  - `rust-analyzer`.

## Instalación

```bash
cd backend
pip install -e ".[dev]"   # editable + deps de desarrollo
```

`-e` (editable): los cambios al código se reflejan sin reinstalar. `[dev]` trae pytest, pytest-asyncio, ruff, etc.

Dependencias del backend (mínimas):

- `websockets` — WS server.
- `asyncpg` — Postgres async (solo se importa si hay `ORUX_DB_DSN`).
- `starlette` + `uvicorn` — el proceso HTTP del panel admin.
- `tree-sitter` — análisis Tier 2.
- `pyright` — LSP de Python (opcional).

NO usamos: SQLAlchemy, FastAPI, Pydantic, Stripe SDK, requests. Regla: una dep entra cuando un cuello de botella concreto la justifica.

## Modo dev (sin Postgres)

```bash
cd backend
python -m orux.server
```

Arranca el WS en `localhost:8765`. Estado en `~/.orux/`:

- `~/.orux/secret` (auto-generado al primer boot).
- `~/.orux/users.json` (`JsonUserStore`).
- `~/.orux/ownership.json` (`JsonOwnershipStore`).
- `~/.orux/workspace/` (un workspace único compartido).

Los equipos NO sobreviven a reiniciar (`MemTeamStore` es in-memory). Útil para iterar rápido sin levantar Docker.

## Modo dev con Postgres

```bash
# Levantar Postgres en Docker:
docker run -d --name orux-pg \
  -p 5432:5432 \
  -e POSTGRES_USER=orux \
  -e POSTGRES_PASSWORD=orux \
  -e POSTGRES_DB=orux \
  postgres:16-alpine

# Arrancar el backend con DSN:
export ORUX_DB_DSN="postgresql://orux:orux@localhost:5432/orux"
python -m orux.server
```

Ahora los equipos sí persisten. El schema se aplica idempotente al boot.

## Frontend (en otra terminal)

```bash
cd frontend/ide
npm install
npm run dev
# → http://localhost:5173
```

El WS de `store.ts` apunta por default a `ws://localhost:8765`. Si necesitás otro:

```bash
VITE_WS_URL=ws://192.168.1.10:8765 npm run dev
```

## Test rápido (smoke)

Abrir `http://localhost:5173`. Register con un username (e.g. `dev`) + password (>=8 chars). Crear un equipo. Editar archivos.

Para verificar que el LSP arranca (si pyright instalado):

```bash
# En los logs del backend:
# "LSP py arrancado" → OK
# "LSP py NO disponible" → revisar mensaje de error
```

## Variables env útiles en dev

```bash
export ORUX_DATA=/tmp/orux-dev           # estado fuera de ~/.orux (para empezar de cero)
export ORUX_TOKEN_TTL_SEC=300            # tokens cortos (5min) para probar reauth
export PYTHONUNBUFFERED=1                # logs en tiempo real
export PYTHONDONTWRITEBYTECODE=1         # sin .pyc en el dir
```

Para apagar el rate-limit en dev:

```bash
export ORUX_REGISTRO_MAX_POR_IP=999999
```

## Correr el proceso `api` (panel admin / OAuth / billing)

```bash
# En otra terminal:
export ORUX_DB_DSN="postgresql://orux:orux@localhost:5432/orux"
export ORUX_ADMIN_USER=dev
export ORUX_ADMIN_TOKEN=$(openssl rand -hex 32)
export ORUX_SESSION_SECRET=...   # el mismo que el orux server
python -m orux.adapters.inbound.http
# → http://localhost:8800
```

Sin `ORUX_ADMIN_*`, los endpoints `/api/v1/admin/*` responden 503.

## Tests

Ver [`testing.md`](testing.md). Comando rápido:

```bash
cd backend
python -m pytest -q          # 513 tests, ~23s
python -m pytest -x -q       # detiene en el primer fallo
python -m pytest tests/test_sync.py -v   # un archivo específico
```

## Linters / formatters

```bash
ruff check backend
ruff format backend
```

Sin pre-commit hook hoy. Ejecutar manualmente antes de commitear.

## Estructura del repo

```
laidea/
├── backend/
│   ├── orux/                      # el paquete Python
│   │   ├── domain/                # dominio puro
│   │   ├── application/           # use cases
│   │   ├── ports/                 # contratos
│   │   ├── adapters/              # implementaciones
│   │   ├── composition.py
│   │   └── ...                    # paths viejos (re-exports backward-compat)
│   ├── tests/                     # 513 tests
│   ├── pyproject.toml
│   └── ...
├── frontend/
│   ├── ide/                       # SPA del IDE (React + Vite)
│   ├── landing/                   # Landing (React + Vite)
│   └── ops/                       # Panel admin (vanilla HTML)
├── docs/                          # ← estás acá
├── docker-compose.yml             # 4 servicios
├── Dockerfile                     # backend (orux + api)
├── Dockerfile.web                 # frontend (multi-stage)
├── Caddyfile                      # proxy reverso + TLS
├── Makefile                       # comandos operativos
├── CLAUDE.md                      # contexto para Claude (no para humanos)
├── README.md                      # visión del producto
└── RUNBOOK.md                     # operaciones detalladas
```

## Para entender el código rápido

Lecturas recomendadas en orden:

1. [`docs/architecture/overview.md`](../architecture/overview.md) — los pilares (hex, ports, adapters).
2. [`docs/flows/edit-and-coordinate.md`](../flows/edit-and-coordinate.md) — el caso de uso central.
3. `backend/orux/domain/state/ownership.py` — el corazón de la tesis (50 líneas).
4. `backend/orux/application/use_cases.py` — qué hace cada handler.
5. `backend/orux/adapters/inbound/websocket/sync.py` — el server WS.

## Trampas comunes en dev

### Imports relativos rotos

Tras el refactor hex (2026-05-24), hay re-exports backward-compat. El código nuevo debería usar la ubicación real:

```python
# ✗ Vieja (funciona pero deprecado):
from orux.state.ownership import Ownership

# ✓ Nueva:
from orux.domain.state.ownership import Ownership

# o más simple para usos comunes:
from orux.domain.state import Ownership
```

### Monkey-patches que no aplican

Si querés mockear `arrancar_lsp` en un test:

```python
# ✗ NO funciona (re-export copia atributos):
monkeypatch.setattr(orux.server.runtime, "arrancar_lsp", fake)

# ✓ Apuntar al módulo real:
monkeypatch.setattr(orux.adapters.inbound.websocket.runtime, "arrancar_lsp", fake)
```

### Variables env quedaron seteadas

Si arrancaste el server con `ORUX_DB_DSN=...` y querés volver a modo JSON:

```bash
unset ORUX_DB_DSN
python -m orux.server
```

`pip install -e .` no afecta env vars; el `unset` es la única forma.

### `~/.orux/` con estado corrupto

Si tras un error el estado quedó inconsistente:

```bash
rm -rf ~/.orux/
python -m orux.server
# Re-genera todo limpio.
```

Cuidado: borra `users.json`, `ownership.json`, `secret`, `workspace/`. Todos los users de dev se pierden.

## IDE recomendado

VS Code con extensiones:

- Python (`ms-python.python`).
- Pylance (`ms-python.vscode-pylance`).
- Ruff (`charliermarsh.ruff`).

Settings.json sugerido para el workspace:

```json
{
  "python.analysis.typeCheckingMode": "basic",
  "ruff.lint.run": "onType",
  "[python]": {
    "editor.defaultFormatter": "charliermarsh.ruff",
    "editor.formatOnSave": true
  }
}
```
