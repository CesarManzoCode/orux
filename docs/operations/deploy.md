# Operations: Deploy

Cómo se despliega Orux en el VPS. La fuente de verdad es la raíz del repo (`docker-compose.yml`, `Dockerfile`, `Dockerfile.web`, `Caddyfile`); este doc explica la **arquitectura** del deploy.

## Topología

```
                      Internet
                         │
                         ↓
                  ┌──────────────┐
                  │  Caddy (443) │  ← TLS automático, proxy reverso
                  │   :80, :443  │     headers de seguridad, CSP
                  └──────┬───────┘
                         │
        ┌────────────────┼────────────────┐
        │                │                │
        ↓ /              ↓ /api/v1/*      ↓ /ws (proxy WS)
   ┌─────────┐      ┌──────────┐    ┌───────────┐
   │  web    │      │   api    │    │   orux    │
   │ (Caddy  │      │ (uvicorn │    │ (Python   │
   │  static)│      │  :8800)  │    │  WS :8765)│
   └─────────┘      └────┬─────┘    └─────┬─────┘
                         │                │
                         └────────┬───────┘
                                  │
                                  ↓
                         ┌────────────────┐
                         │   postgres     │
                         │   (interno)    │
                         └────────────────┘
```

4 contenedores. **Solo Caddy se expone a internet** (puertos 80/443). El resto vive en la red Docker interna.

## Servicios

### `caddy`

Imagen: `caddy:2` (pinear digest).

- TLS automático con Let's Encrypt.
- Proxy reverso a `web`, `api`, `orux`.
- Headers de seguridad (HSTS, X-Frame-Options, CSP por-ruta).
- Sirve estático del frontend (montado desde `web` build output).

Volumen: `/data/caddy` para certificados.

### `web`

Imagen multi-stage construida por `Dockerfile.web`:

1. **Stage build**: Node 20, `npm ci`, `npm run build` en `frontend/ide` y `frontend/landing`.
2. **Stage final**: Caddy alpine sirviendo `dist/`.

Sirve:

- `/` → `frontend/landing/dist/` (la landing).
- `/app/*` → `frontend/ide/dist/` (el IDE SPA).
- `/admin` → `frontend/ops/admin.html` (panel operador, vanilla).

### `api`

Imagen `Dockerfile` (la misma del backend). Comando: `python -m orux.adapters.inbound.http`.

- Puerto interno 8800.
- Conecta a `postgres` para users/teams/webhooks.
- Cero estado propio (cualquier réplica funcionaría — aún no escalado).

### `orux`

Imagen `Dockerfile` (mismo que `api`). Comando: `python -m orux.server`.

- Puerto interno 8765 (WS).
- Conecta a `postgres` para users/teams/ownership/proposals.
- Stateful por equipo (TeamRuntime en memoria + sesiones LSP + roster).
- **NO escalable horizontal hoy** — sesiones WS son sticky.

### `postgres`

Imagen `postgres:16-alpine` (pinear digest).

- Solo accesible por la red Docker interna.
- Volumen `/data/postgres` para los datos.
- Schema aplicado idempotente por `orux` y `api` al boot.

## Recursos (`deploy.resources.limits`)

Tras el VPS upgrade del 2026-05-23 (4 vCPU / 8 GB / 160 GB):

| Servicio | CPUs | Memoria |
|---|---|---|
| `orux` | 3 | 4 GB |
| `api` | 0.5 | 768 MB |
| `postgres` | 1 | 1.5 GB |
| `caddy` | 0.5 | 256 MB |

Total: 5 vCPU (oversubscription) / 6.5 GB (82% físico).

`orux` lleva la mayor parte porque hace LSP (subprocess pesado), análisis semántico y mantiene workspaces en memoria por equipo.

## Volúmenes

| Volumen | Para qué | Backup |
|---|---|---|
| `/data/orux` | `~/.orux/` del contenedor `orux`: secret, ws/ (workspaces git por equipo) | Crítico — backup diario |
| `/data/postgres` | Datos de Postgres | Crítico — backup diario |
| `/data/caddy` | Certificados TLS Let's Encrypt | Re-emitible (se regenera si se pierde) |

`scripts/backup-db.sh` hace `pg_dump` + opcional sync a DO Spaces. Ver [`backup.md`](backup.md).

## Variables de entorno

Variables requeridas (sin ellas no arranca o degrada):

| Var | Contenedor | Default | Para qué |
|---|---|---|---|
| `ORUX_DB_DSN` | orux, api | (vacío = modo dev JSON) | Postgres DSN: `postgresql://user:pass@postgres:5432/orux` |
| `ORUX_SESSION_SECRET` | orux, api | Auto-genera | Secret HMAC, compartido para que ambos firmen/verifiquen iguales |
| `ORUX_WS_ORIGINS` | orux | `https://orux.space,...` | Whitelist anti-CSRF WS |

Variables opt-in (sin ellas el servicio responde 503):

| Var | Contenedor | Para qué |
|---|---|---|
| `ORUX_ADMIN_USER` + `ORUX_ADMIN_TOKEN` | api | Panel admin del operador |
| `ORUX_GH_CLIENT_ID` + `ORUX_GH_CLIENT_SECRET` + `ORUX_GH_REDIRECT` | api | OAuth GitHub |
| `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` | api, orux | Billing |
| `STRIPE_PRICE_AMOUNT` + `STRIPE_PRICE_CURRENCY` + `STRIPE_PRICE_INTERVAL` | api | Config del producto Stripe |
| `STRIPE_PRICE_DESCRIPCION` | api | Nombre mostrado en Checkout |

Variables operativas (defaults sanos):

| Var | Default | Para qué |
|---|---|---|
| `ORUX_DATA` | `/data/orux` | Directorio base del estado |
| `ORUX_HOST` | `localhost` | Bind del WS |
| `ORUX_PORT` | `8765` | Puerto del WS |
| `ORUX_TOKEN_TTL_SEC` | 2592000 (30d) | Vida de tokens de sesión |
| `ORUX_GIT_TIMEOUT` | 120 | Timeout git ops remotas (s) |
| `ORUX_GIT_TIMEOUT_LOCAL` | 10 | Timeout git ops locales (s) |
| `ORUX_REGISTRO_MAX_POR_IP` | 20 | Cap de registros por IP en 10min |
| `ORUX_MAX_USUARIOS` | 10000 | Cap absoluto de usuarios de la plataforma |
| `ORUX_VERSION` | "dev" | Version del deploy (mostrada en /api/v1/status) |

## Comandos del Makefile

```bash
make up        # docker-compose up -d --build
make down      # docker-compose down (PRESERVA volúmenes)
make logs      # tail -f de los 4 contenedores
make ps        # docker-compose ps
make restart   # restart de los 4 contenedores

make db-backup    # pg_dump → /data/backups/orux-YYYY-MM-DD.sql
make db-restore   # restaura del último backup
make db-shell     # psql -U orux orux

make redeploy  # pull + build + up (atómico)
```

Convención: TODOS los comandos operativos viven en el Makefile. Si necesitás recordar algo dos veces, va al Makefile.

## Flujo de redeploy

```bash
# En el VPS, en /opt/orux:
git pull origin main          # trae los cambios
make redeploy                  # rebuild + restart
docker compose logs -f orux api  # verificar boot
```

Tiempo aproximado: ~2 min (build de frontend) + ~30s (boot de orux + api).

Durante el redeploy:

- WebSocket clients se desconectan → reconectan con backoff exponencial (capa P0 pre-anuncio: 500ms → 30s, reset al onopen).
- HTTP requests fallan ~30s.

Para minimizar downtime, hay margen para hacer un deploy blue-green más adelante (run nuevo container, switch Caddy upstream, kill viejo). Hoy no es necesario.

## Healthchecks

| Contenedor | Healthcheck | Si falla |
|---|---|---|
| `orux` | WS handshake a `ws://localhost:8765/` (no HTTP) | `restart_policy: always` reintenta |
| `api` | `GET /health` (incluye `db.ping()`) → 503 si DB caída | Idem |
| `postgres` | `pg_isready` | Idem |
| `caddy` | `wget -q --spider http://localhost:80/api/v1/status` | Idem |

**Trampa documentada** (RUNBOOK.md): el healthcheck del `orux` antes hacía `socket.create_connection` y cerraba sin handshake → el servidor websockets intentaba parsear HTTP y gritaba en logs. Funcionaba pero ruidoso. Arreglado: handshake WS real + close inmediato.

## Logs

Stdout de cada contenedor → `docker compose logs <servicio>`. Sin journal compartido (cada container es independiente).

Logs estructurados con `logging.basicConfig(format="%(asctime)s %(levelname)s %(message)s")`. Para diagnóstico:

```bash
docker compose logs orux --since 1h | grep -iE "error|warn"
docker compose logs api --since 1h | grep -iE "error|warn"
docker compose logs orux --since 5m | grep -iE "auth|login|oauth"
docker compose logs orux | grep -E "BACKEND-AUDIT|LSP"
```

Sin shipping a un agregador (Datadog, Loki) — etapa de prototipo.

## Limitaciones conocidas

- **Single-node**: el WS server es stateful por equipo. No se puede escalar horizontal sin sticky sessions + estado compartido. Hoy 50-100 devs concurrentes con 4 vCPU / 8 GB es holgado.
- **Sin CI/CD automatizado**: `git pull && make redeploy` manual. Para algo más automatizado, GitHub Actions disparando deploy SSH al VPS.
- **Backups solo de DB**: el directorio `/data/orux/ws/<team_id>/` (workspaces git) NO se backupea sistemáticamente. **Cada equipo es su propio repo git**: si el dev tiene push regular, está respaldado en su remoto. Si no, perder el VPS = perder lo no-pusheado. Mitigación social: pedir a los equipos que pusheen.
- **Métricas en logs**: `client_track` postea analytics al log. Para Grafana / dashboards reales, hay que parsear los logs o agregar export Prometheus.

Ver [`runbook.md`](runbook.md) para operaciones comunes y [`troubleshooting.md`](troubleshooting.md) para diagnóstico.
