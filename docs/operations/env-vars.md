# Operations: Variables de entorno

Referencia completa de las env vars que afectan al backend. Agrupadas por concepto.

## Críticas (sin ellas no arranca o degrada serio)

| Var | Contenedores | Default | Para qué |
|---|---|---|---|
| `ORUX_DB_DSN` | orux, api | (vacío) | Postgres DSN: `postgresql://user:pass@host:port/dbname`. Vacío = modo dev JSON. |
| `ORUX_SESSION_SECRET` | orux, api | Auto-genera en `~/.orux/secret` si vacío | Secret HMAC para tokens de sesión. **DEBE ser idéntico** en `api` y `orux` para OAuth. |
| `ORUX_WS_ORIGINS` | orux | `https://orux.space,http://localhost:5173,http://localhost:8080` | Whitelist anti-CSRF WS. Cada cliente nuevo debe sumarse. `*` = deshabilitado (debug). |
| `ORUX_DATA` | orux | `~/.orux` (usuario) o `/data/orux` (Docker) | Directorio base del estado (secret, workspaces). |

## Opt-in: panel del operador

Sin ellas: panel admin responde 503.

| Var | Contenedor | Para qué |
|---|---|---|
| `ORUX_ADMIN_USER` | api | Username del operador (debe registrarse como usuario normal primero). |
| `ORUX_ADMIN_TOKEN` | api | Secret HMAC para firmar tokens del panel. NUNCA viaja al cliente. |

## Opt-in: OAuth GitHub

Sin ellas: `/oauth/github/*` responde 503.

| Var | Contenedor | Para qué |
|---|---|---|
| `ORUX_GH_CLIENT_ID` | api | Client ID de la app OAuth en GitHub. |
| `ORUX_GH_CLIENT_SECRET` | api | Client secret. NUNCA en logs, NUNCA en commits. |
| `ORUX_GH_REDIRECT` | api | URL absoluta del callback (`https://orux.space/oauth/github/callback`). |
| `ORUX_PUBLIC_URL` | api | URL del SPA (para `_sanitizar_app_url` anti open-redirect). |

Ver [`oauth-github.md`](../oauth-github.md) para el setup del dashboard de GitHub.

## Opt-in: Billing Stripe

Sin ellas: `/api/v1/billing/*` responde 503 y `seats.disparar_ajuste` skipea silencioso.

| Var | Contenedores | Para qué |
|---|---|---|
| `STRIPE_SECRET_KEY` | api, **orux** | API key. **AMBOS contenedores**: api para Checkout, orux para ajuste de asientos. |
| `STRIPE_WEBHOOK_SECRET` | api | El `whsec_...` para verificar firmas. |
| `STRIPE_PRICE_AMOUNT` | api | Precio en centavos (e.g. `20000` = $200.00). |
| `STRIPE_PRICE_CURRENCY` | api | ISO 4217 (`MXN`, `USD`, …). |
| `STRIPE_PRICE_INTERVAL` | api | `month` o `year`. |
| `STRIPE_PRICE_DESCRIPCION` | api | Nombre mostrado en Checkout (`"Orux Premium"`). |

## Operativas: topes y timeouts

Defaults sanos. Ajustar solo si hay justificación operativa.

### Tokens y sesiones

| Var | Default | Clamp | Para qué |
|---|---|---|---|
| `ORUX_TOKEN_TTL_SEC` | 2592000 (30 días) | 0 - 31536000 (1 año) | Vida de tokens de sesión. 0 = sin expiración (NO usar). |

### Anti-abuso

| Var | Default | Para qué |
|---|---|---|
| `ORUX_REGISTRO_MAX_POR_IP` | 20 | Registros por IP en 10 min. |
| `ORUX_MAX_USUARIOS` | 10000 | Cap absoluto de usuarios en la plataforma. |

### Git timeouts

| Var | Default | Clamp | Para qué |
|---|---|---|---|
| `ORUX_GIT_TIMEOUT` | 120s | ≥5s | Operaciones git remotas (fetch, clone, push). |
| `ORUX_GIT_TIMEOUT_LOCAL` | 10s | ≥5s | Operaciones git locales (status, log, add, commit). |
| `ORUX_GIT_TIMEOUT_REMOTO` | (alias de ORUX_GIT_TIMEOUT) | | |

### Workspace

| Var | Default | Clamp | Para qué |
|---|---|---|---|
| `ORUX_WS_MAX_ARCHIVOS` | 50000 | 100 - 1000000 | Archivos máximos por workspace. |
| `ORUX_WS_MAX_BYTES_ARCHIVO` | 1 MB | 1KB - 16MB | Tamaño máximo por archivo. |
| `ORUX_WS_MAX_BYTES_TOTAL` | 256 MB | 1MB - 4GB | Suma máxima de bytes del workspace. |

### Postgres pool

| Var | Default | Para qué |
|---|---|---|
| `ORUX_DB_POOL_MIN` | 2 | Conexiones mínimas en el pool asyncpg. |
| `ORUX_DB_POOL_MAX` | 10 | Conexiones máximas. |
| `ORUX_DB_TIMEOUT` | 10s | Timeout por query individual. |

## Operativas: networking

| Var | Default | Para qué |
|---|---|---|
| `ORUX_HOST` | `localhost` | Bind del WS server. En Docker: `0.0.0.0`. |
| `ORUX_PORT` | `8765` | Puerto del WS. |

## Operativas: metadata

| Var | Default | Para qué |
|---|---|---|
| `ORUX_VERSION` | `"dev"` | Versión del deploy. Mostrada en `/api/v1/status` para diagnóstico. |

## Variables OAuth state (no documentadas arriba)

Algunas variables internas que afectan al state CSRF de OAuth:

| Var | Default | Para qué |
|---|---|---|
| `ORUX_OAUTH_STATE_MAX_EDAD` | 120s | TTL del state CSRF. Bajar = menos ventana de replay; subir = más holgura para usuarios lentos. |

## Variables del frontend (en build, no runtime)

El frontend se construye con Vite. Variables `VITE_*` se inyectan en build time:

| Var | Para qué |
|---|---|
| `VITE_WS_URL` | URL del WS server (default `wss://${host}:443/ws`). |
| `VITE_API_URL` | URL del HTTP api (default `${origin}/api/v1`). |
| `VITE_PUBLIC_URL` | URL pública para canonical links, etc. |

Setear en `frontend/ide/.env` para dev local; el build de producción los toma del Docker build.

## Variables NUNCA en el repo

Las siguientes DEBEN estar en `.env` (excluido por `.gitignore`) o en un password manager:

- `ORUX_SESSION_SECRET`
- `ORUX_ADMIN_TOKEN`
- `ORUX_GH_CLIENT_SECRET`
- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `ORUX_DB_DSN` (contiene password de DB)

El `.env.example` documenta cuáles son sin sus valores.

## Cómo verificar las env en el contenedor

```bash
docker compose exec api env | grep -E "ORUX|STRIPE" | sort
docker compose exec orux env | grep -E "ORUX|STRIPE" | sort
```

Para chequear que `ORUX_SESSION_SECRET` es idéntico en ambos (crítico para OAuth):

```bash
diff <(docker compose exec api env | grep SESSION) \
     <(docker compose exec orux env | grep SESSION)
# Si imprime algo, hay desincronización.
```

## Cómo aplicar cambios de env

```bash
# 1. Editar docker-compose.yml o .env
vim /opt/orux/.env

# 2. Recrear los contenedores afectados
docker compose up -d --force-recreate api orux

# 3. Verificar que tomaron los nuevos valores
docker compose logs api orux | tail -20
```

`docker compose restart` NO recarga env vars del docker-compose.yml. Usar `--force-recreate`.

## Convenciones

- **Sin prefijo (`PATH`, `HOME`, …)**: estándar del OS.
- **`ORUX_*`**: del producto.
- **`STRIPE_*`**: Stripe.
- **`VITE_*`**: frontend (build time).
- **`PYTHONUNBUFFERED=1`**: clásico para que logs salgan en tiempo real (no bufferados).

Variables que NO usamos pero existen en algunos entornos:

- `PYTHONDONTWRITEBYTECODE=1`: para no escribir `.pyc` en producción. Lo seteamos en el Dockerfile.
- `PYTHONPATH`: no lo seteamos; el paquete `orux` se instala con `pip install -e .`.
