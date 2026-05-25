# Adapters

Los adapters son las implementaciones concretas de los Ports. Hay dos categorías:

- **Inbound**: quien INICIA conversaciones con el dominio (WebSocket, HTTP).
- **Outbound**: lo que el dominio invoca para hablar con afuera (Postgres, JSON, Git, Stripe, LSP).

## Layout

```
backend/orux/adapters/
├── inbound/
│   ├── websocket/      SyncServer + dispatch + runtime + auth_handshake + lobby + …
│   └── http/           app.py (Starlette: panel admin + OAuth + webhooks)
└── outbound/
    ├── json/           JsonOwnershipStore, JsonUserStore
    ├── identity/       HmacSessionTokenAdapter, GithubOAuthAdapter
    ├── billing/        StripeBillingAdapter
    ├── analysis/       SemanticAnalysisAdapter, LspFactoryAdapter
    ├── postgres/       Database + PgUserStore + PgOwnershipStore + PgProposalsStore + PgWebhooksStore + PgTeamStore
    └── git/            binary.py (GitBinaryAdapter, alias GitRepo)
```

## Inbound: WebSocket (`adapters/inbound/websocket/`)

El núcleo del servidor en tiempo real. Una conexión WebSocket en `ws://host:8765` pasa por:

1. **Autenticación** (`auth_handshake.py`): register/login/session → usuario autenticado.
2. **Lobby** (`lobby.py`): el usuario ve sus equipos, crea uno (queda admin), redime un código de invitación, o selecciona uno existente.
3. **Sesión de equipo** (`sync.py` + `dispatch.py`): handshake (init/welcome/ownership/admin_info/git) y bucle de mensajes operando sobre el `TeamRuntime` (estado vivo del equipo).

### `SyncServer` (`sync.py`)

El servidor principal. Su `__init__` acepta los Ports (todos opcionales, con defaults razonables para tests):

```python
SyncServer(
    storage: WorkspaceStoragePort | None,
    users: UserStorePort | UserStore | None,
    ownership: Ownership | None,
    secret: str | None,
    git: GitPort | None,
    teams: TeamStorePort | None,
    runtime_factory=None,
    ownership_store: OwnershipStorePort | None,
    proposals_store: ProposalsStorePort | None,
)
```

Mantiene un `dict[team_id, TeamRuntime]` perezoso (los runtimes se construyen al primer cliente del equipo, se evictan tras TTL sin conexiones).

### `TeamRuntime` (`runtime.py`)

Todo el estado vivo de UN equipo: workspace, ownership, proposals, roster (presencia), conexiones, sesiones LSP, lock de git, lock de estado. Aislamiento total: el runtime de un equipo no ve al otro.

```python
class TeamRuntime:
    team_id: str
    workspace: Workspace
    ownership: Ownership
    proposals: Proposals
    roster: Roster
    clients: set[ServerConnection]
    git: GitPort | None
    # … más estado interno
```

La sesión LSP (`lsp_sesion(lang, cap)`) es lazy + con reintento exponencial: la 1ª llamada arranca pyright/tsserver/etc.; si falla, cooldown crecente (60s → 120s → 240s → … → 30 min) antes del siguiente intento. Auto-recupera si el operador arregla el entorno en caliente.

### `dispatch.py` — translate-only

Cada mensaje del protocolo tiene su handler `_h_<tipo>`. El handler ya NO contiene lógica de negocio: decodifica el mensaje, arma el Command, llama al use case, traduce el Result a sends:

```python
async def _h_claim(server, rt, websocket, yo, team_id, message):
    res = await claim_use_case(
        rt,
        server._ownership_store,
        ClaimCommand(path=message.path, autor_id=yo.client_id),
    )
    await server._broadcast_todos(
        rt, encode(OwnershipMessage(owners=res.broadcast_ownership)),
    )
```

Tabla `HANDLERS: dict[type, Handler]` que mapea clase de mensaje → handler. Agregar un mensaje nuevo es sumar UNA entrada acá y un `_h_<x>`.

### Pieza por pieza

| Archivo | Qué hace |
|---|---|
| `sync.py` | `SyncServer` + el bucle de mensajes + broadcasts + locks por equipo |
| `dispatch.py` | Tabla de handlers + translate WS↔use case |
| `runtime.py` | `TeamRuntime` + gestión de sesiones LSP por equipo |
| `auth_handshake.py` | Register / login / session (token HMAC) |
| `lobby.py` | El usuario ve/elige/crea un equipo antes de entrar a la sesión |
| `eviction.py` | Barrido de runtimes ociosos (sin conexiones tras TTL) |
| `impacto.py` | Translator del Save (capa 19): delega a `application/impacto.py` |
| `seats.py` | Ajuste de asientos en Stripe cuando entra/sale un miembro |
| `config.py` | Topes runtime (rate limits, frame size, WS origins, …) |
| `util.py` | Helpers puros: `autor_git`, `ip_cliente`, `wrap_users` (sync→async) |

## Inbound: HTTP (`adapters/inbound/http/app.py`)

Un proceso aparte (Starlette/uvicorn, puerto 8800). Cumple tres roles:

1. **Panel del operador** (`/api/v1`): login con cuenta de admin → token bearer → endpoints de listado/borrado/cambio de plan. Llama a use cases en `application/http_use_cases.py`.
2. **OAuth GitHub callback** (`/oauth/github/login`, `/oauth/github/callback`): redirige a GitHub, recibe el code, intercambia por access token, lee el perfil, deriva la identidad `gh:<login>`, emite token de sesión idéntico al del WS server.
3. **Webhooks Stripe** (`/api/v1/billing/webhook`): verifica firma HMAC, parsea evento, aplica cambio de plan vía `aplicar_evento_stripe`. Idempotente por `event_id` (con `WebhooksStorePort`).

`crear_app(users, teams, webhooks)` arma el Starlette con todas las rutas. Es invocado por el `__main__.py` del proceso `api`.

**Decisión crítica**: este proceso NO comparte el loop ni el estado del servidor WebSocket. Un fallo acá no tumba la colaboración. Solo lee/escribe Postgres.

## Outbound: Postgres (`adapters/outbound/postgres/`)

### `Database` (`pool.py`)

Wrapper sobre `asyncpg.Pool` con:

- Conexión perezosa (`Database.conectar(dsn)` async).
- Aplicación idempotente del schema (`schema.sql`) al primer connect.
- Transacciones explícitas (`async with db.tx() as con: ...`).
- Helpers: `fetchval`, `fetchrow`, `fetch`, `execute`.
- Healthcheck `ping()` para `/health` del proceso `api`.

### Schema (`schema.sql`)

Idempotente (CREATE TABLE IF NOT EXISTS, ALTER TABLE ADD COLUMN IF NOT EXISTS) — se aplica en cada arranque. Tablas:

| Tabla | Para qué |
|---|---|
| `users` | `username` (PK), `password_hash` (PBKDF2 / MARCADOR_EXTERNO para OAuth), `epoch` (revocación quirúrgica) |
| `teams` | `id`, `nombre`, `creador`, `plan` (free/premium), `stripe_subscription_id` |
| `team_members` | `team_id`, `username`, `rol` (admin/member). FK con ON DELETE CASCADE |
| `invites` | `code`, `team_id`, `creado_por`, `usado_por`, `expires_at`. TTL 7 días |
| `ownership` | `team_id`, `path`, `owner`. FK con ON DELETE CASCADE |
| `proposals` | `team_id`, `proposal_id`, `path`, `author_id`, `author_name`, `content`. FK con ON DELETE CASCADE |
| `processed_webhooks` | `event_id` (PK), `processed_at`. Idempotencia Stripe |

### Stores (`stores.py` + `teams.py`)

Cada `Pg*Store` implementa su Port async, recibe `Database` por inyección, y delega a SQL parametrizado.

Decisiones importantes:

- **Atomic UPSERT** con `ON CONFLICT DO NOTHING RETURNING ...` para evitar carreras entre dos registros con el mismo username.
- **Diff sobre el estado existente** en `PgOwnershipStore.guardar` para evitar write amplification (si el cambio es 1 path de 5000, hacemos 1 UPSERT, no 5000 INSERTs).
- **FOR UPDATE** en `PgTeamStore.redimir` para que el chequeo de "ya usado" sea atómico con el set.
- **TTL de invitaciones (7 días)** validado dentro de la transacción (no en Python, no hay TOCTOU).

## Outbound: JSON local (`adapters/outbound/json/`)

Modo dev/tests sin Postgres. Encapsulan la atomicidad/permisos/validación que vivía inline en `Ownership` y `UserStore` antes del refactor hex.

- `JsonOwnershipStore`: archivo único `~/.orux/ownership.json` (single-team por diseño, el `team_id` se ignora — en modo dev multi-equipo todos comparten el mismo JSON).
- `JsonUserStore`: archivo único `~/.orux/users.json`. Lock interno `asyncio.Lock` para check-then-set.

Hardening conservado:

- Tmp único con pid+uuid para no chocar entre corutinas (`BACKEND-AUDIT-0064`).
- Permisos 0600 al crear (los hashes PBKDF2 no se exponen a otros usuarios del host).
- `fsync` antes del replace: durabilidad real ante corte de luz.
- Validación estructural al cargar: JSON no-dict / paths inseguros se filtran sin tumbar el server.

## Outbound: Identity (`adapters/outbound/identity/`)

Dos adapters **delgados** que cierran config externa y delegan a las funciones puras de `domain/identity/`:

- `HmacSessionTokenAdapter(secret)`: cierra el secret HMAC; `crear` y `usuario_de` delegan a `tokens.crear_token` / `usuario_de_token`. El secret puede ser `str` (modo histórico), `list` (rotación con fallback ordenado) o `dict {kid: secret}` (rotación atómica por kid).
- `GithubOAuthAdapter(client_id, redirect_uri, state_secret)`: cierra los tres params y delega a `oauth.url_autorizacion`, `firmar_state`, `validar_state`, `identidad_github`. La llamada de red real (intercambiar code por token) NO está acá — vive en `inbound/http/app.py:_intercambiar` por separación de responsabilidades.

## Outbound: Billing (`adapters/outbound/billing/stripe.py`)

`StripeBillingAdapter(webhook_signing_secret, currency, unit_amount, interval, descripcion_producto)` cierra:

- `webhook_signing_secret`: el `whsec_...` que firma cada webhook.
- Config del producto (`currency`, `unit_amount`, `interval`, `descripcion_producto`).

Delega a `domain/billing.py` (funciones puras: HMAC verify, parser de eventos, builders de form-data). La parte de red real (POST a Stripe para crear el Checkout, ajustar asientos) vive en `adapters/outbound/billing/stripe_client.py` (sigue en `orux/stripe_client.py` por simplicidad histórica; podría moverse).

## Outbound: Analysis (`adapters/outbound/analysis/`)

Dos adapters:

- `SemanticAnalysisAdapter`: cumple `AnalysisPort` delegando a `domain.analysis` (impacto, motivos, tiers, rename, sugerencia).
- `LspFactoryAdapter`: cumple `LspFactoryPort` delegando a `domain.analysis.lsp.arrancar_lsp`.

`impacto_transitivo` (premium) NO está en el Port porque requiere callbacks inyectados de bajo nivel; el caller (`application/impacto.py`) lo usa directamente como función pura.

## Outbound: Git (`adapters/outbound/git/binary.py`)

`GitRepo` (alias `GitBinaryAdapter`) envuelve el binario `git` del sistema. Es la pieza más endurecida de seguridad — ver [`security/git.md`](../security/git.md) para el detalle de todas las defensas (allowlist de URLs, hooks deshabilitados, env filtrado, credenciales efímeras, askpass temporal, anti-traversal, etc.).

Operaciones expuestas: `asegurar` (git init si hace falta), `estado` (rama + cambios + últimos commits), `commitear`, `clonar` (destructivo), `push`, `push_a_rama` (force-with-lease + link de PR).

`EstadoGit` (value object): vive en `ports/git.py` como parte del contrato.
