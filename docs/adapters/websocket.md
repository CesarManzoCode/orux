# Adapter: WebSocket (inbound)

`backend/orux/adapters/inbound/websocket/` es el inbound adapter principal: el servidor WebSocket que los clientes del IDE usan en `ws://host:8765`.

Es donde el código se vuelve "vivo" — el bucle de mensajes, los broadcasts, la coreografía de locks por equipo, el lifecycle de las sesiones LSP. Es también el módulo más grande del backend.

## Archivos

| Archivo | Qué hace | LOC |
|---|---|---|
| `sync.py` | `SyncServer` — el servidor WS, broadcasts, eviction de runtimes, ajuste de asientos | ~960 |
| `dispatch.py` | Tabla de handlers + translate WS↔use case | ~330 |
| `runtime.py` | `TeamRuntime` — estado vivo de UN equipo + lifecycle de sesiones LSP | ~270 |
| `auth_handshake.py` | Register / login / session (token HMAC) | ~210 |
| `lobby.py` | Usuario ve/elige/crea equipo antes de entrar a la sesión | ~95 |
| `eviction.py` | Barrer runtimes ociosos | ~140 |
| `impacto.py` | Translator del Save (delega a `application/impacto.py`) | ~75 |
| `seats.py` | Ajuste de asientos en Stripe cuando entra/sale miembro | ~90 |
| `config.py` | Topes runtime (rate limits, frame size, WS origins) | ~110 |
| `util.py` | Helpers puros: `autor_git`, `ip_cliente`, `wrap_users` | ~120 |

## `SyncServer` — el corazón

```python
class SyncServer:
    def __init__(
        self,
        storage: WorkspaceStoragePort | None,
        users: UserStorePort | UserStore | None,
        ownership: Ownership | None,
        secret: str | None,
        git: GitPort | None,
        teams: TeamStorePort | None,
        runtime_factory=None,
        ownership_store: OwnershipStorePort | None,
        proposals_store: ProposalsStorePort | None,
    ): ...
    
    async def run(self, host, port) -> None: ...
```

Estado del server (no del equipo):

```python
self._runtimes: dict[str, TeamRuntime] = {}  # team_id → runtime
self._rt_locks: dict[str, asyncio.Lock] = {}  # locks para construir runtimes
self._registro_buckets: dict[str, list[float]] = {}  # rate-limit registros
self._login_buckets: dict[str, list[float]] = {}     # rate-limit logins
self._asientos_locks: dict[str, asyncio.Lock] = {}   # locks de ajuste Stripe
self._stripe_secret: str = os.environ.get("STRIPE_SECRET_KEY", "")
```

## Flujo de una conexión

```
ws connect → autenticar → lobby → seleccionar/crear equipo → sesión de equipo
                                                                    │
                              ┌─────────────────────────────────────┘
                              ↓
   bucle de mensajes (update / save / claim / resolve / commit / ...)
                              ↓
                      ws close / leave
```

### 1. Conexión (`sync.py:_atender_conexion`)

```python
async def _atender_conexion(self, websocket):
    # Whitelist de origins WS (anti-CSRF): valida header Origin
    origen = websocket.request.headers.get("origin", "")
    if not self._origen_permitido(origen):
        await websocket.close(code=4001, reason="origin no permitido")
        return
    
    # Rate-limit por IP
    ip = ip_cliente(websocket)
    
    yo = await self._autenticar(websocket, ip)
    if yo is None:
        return  # auth falló, conexión cerrada
    
    # Lobby
    team = await self._lobby(websocket, yo)
    if team is None:
        return  # el cliente cerró sin elegir equipo
    
    # Sesión de equipo
    rt = await self._runtime_para(team["id"])
    async with self._sumar_cliente_a(rt, websocket, yo):
        await self._handshake_equipo(rt, websocket, yo, team)
        await self._bucle_mensajes(rt, websocket, yo, team["id"])
```

### 2. Autenticación (`auth_handshake.py`)

El cliente puede:

- **Registrar** (`RegisterMessage`): username + password → crea usuario, emite token.
- **Login** (`LoginMessage`): username + password → verifica, emite token.
- **Session** (`SessionMessage`): token → valida HMAC + epoch, recupera username.
- **OAuth** se hace en el proceso HTTP (paralelo): el cliente recibe el token tras el callback y lo presenta vía `SessionMessage`.

Rate-limit por IP:

- Registros: 20 por 10 min (ajustable con `ORUX_REGISTRO_MAX_POR_IP`). Cap generoso para una oficina entera detrás de NAT; bot lo choca.
- Logins: 3 por minuto (BACKEND-AUDIT-0163: bajado de 5 a 3).

### 3. Lobby (`lobby.py`)

Tras auth, el usuario recibe `LobbyMessage` con sus equipos. Puede:

- **Crear** (`CreateTeamMessage`): nuevo equipo, quedo como admin.
- **Redimir** (`RedeemInviteMessage`): unirme a un equipo con código.
- **Seleccionar** (`SelectTeamMessage`): un equipo del que ya soy miembro.

El server responde `TeamReadyMessage{team_id, nombre, rol}` cuando el cliente puede entrar.

### 4. Sesión de equipo

#### Handshake

```
S→C: InitMessage{documents}           # snapshot del workspace
S→C: WelcomeMessage{client_id, name, color, others}  # presencia
S→C: OwnershipMessage{owners}          # mapa actual
S→C: AdminInfoMessage{is_admin, members}
S→C: GitStatusMessage{...}              # si git disponible
S→C: ProposalMessage × N                # reentrega de propuestas pendientes para el dueño
```

#### Bucle de mensajes

```python
async def _bucle_mensajes(self, rt, websocket, yo, team_id):
    async for raw in websocket:
        try:
            message = decode(raw)
        except ProtocolError as e:
            # Manda AuthError + sigue (no cierra la conexión)
            continue
        # Lock por equipo para read-modify-write
        async with rt._estado_lock:
            await dispatch(self, rt, websocket, yo, team_id, message)
```

### 5. Cierre

`_sumar_cliente_a` es un async context manager. Al salir (close o `LeaveMessage`):

- Quita al cliente del `rt.clients`.
- Quita al cliente del `rt.roster` (presencia).
- Broadcast a los demás: cursor desaparece.
- Si era el último cliente: marca `rt._vacio_desde = monotonic()` (para eviction).

## `TeamRuntime`

Documentado en [`architecture/adapters.md`](../architecture/adapters.md). Tiene:

- `workspace`, `ownership`, `proposals`, `roster` (estado del dominio).
- `clients: set[ServerConnection]` (conexiones activas).
- `git: GitPort | None`.
- `_lsp: dict[str, _LspEstado]` (sesiones LSP por lenguaje, con cooldown).
- `_git_lock: asyncio.Lock` (serializa git por equipo).
- `_estado_lock: asyncio.Lock` (serializa update/save/resolve/delete/claim/admin_assign/clone-reinit).

## Locks

### `rt._estado_lock`

Por equipo. Lo agarra `_aplicar` del bucle antes de llamar `dispatch`. Los handlers NO re-toman (los use cases ya operan dentro del lock).

**Por qué existe** (auditoría C1/C2/A1/A2): tramos read-modify-write (`leo snapshot → await análisis → muto → difundo`) se intercalan en el `await` y pisan estado con foto vieja. Sin el lock:

- `_propagar_rename`: lost update.
- El `claim` del creador corría DESPUÉS de un await.
- `Resolve` aceptaba contenido obsoleto.

Trade-off aceptado: los Save de UN equipo se serializan. Son por Ctrl+S (no por tecla), la coherencia del baseline lo exige.

Presencia (`Roster.mover`) y git NO toman este lock: siguen ágiles aunque un análisis de Save esté corriendo.

### `rt._git_lock`

Serializa commit/clone/push del equipo. Por-runtime: el git de un equipo no bloquea al de otro.

Orden git → estado (nunca al revés en ningún handler) ⇒ sin deadlock. El `_h_clone` toma git_lock + estado_lock anidados; otros handlers solo toman estado_lock o git_lock pero no ambos.

### `rt._lsp_lock` (`threading.Lock`)

Interno de `runtime._LspEstado`. Sync porque `arrancar_lsp` corre en `to_thread`. Cubre el cache `_lsp[lang]` (verificación, asignación, cleanup).

### Server-level

- `self._rt_locks[team_id]`: para construir el runtime sin carrera (BACKEND-AUDIT-0220).
- `self._asientos_locks[team_id]`: para ajuste de asientos sin pisar conteo.

## `dispatch.py` — translate-only

Cada handler `_h_<tipo>`:

1. Decodifica del `message` (ya parseado por `codec.decode` en el bucle).
2. Arma el `Command` del use case.
3. Llama al use case con los Ports inyectados desde `server._X`.
4. Traduce el `Result` a `_broadcast` / `_enviar_a` / `_broadcast_todos` con `encode(...)`.

No tiene lógica de negocio. Es **inbound puro**.

Tabla `HANDLERS: dict[type, Handler]` mapea clase de mensaje → handler. Agregar un mensaje nuevo es:

1. Definir el `Message` en `protocol/messages.py`.
2. Registrarlo en `protocol/codec.py:decode`.
3. Escribir el use case en `application/use_cases.py`.
4. Escribir el `_h_<x>` en `dispatch.py` y sumarlo a `HANDLERS`.

Cuatro pasos mecánicos.

## Broadcasts

```python
async def _broadcast(self, rt, exclude_ws, payload):
    """A todos los de `rt.clients` menos `exclude_ws`."""

async def _broadcast_todos(self, rt, payload):
    """A todos los de `rt.clients` (incluyendo el emisor)."""

async def _enviar_a(self, rt, client_id, payload):
    """SOLO al cliente con ese client_id (en este equipo)."""
```

`payload` es `bytes` (ya `encode`-ado). El server no decide qué encode — el use case devolvió un Result, el inbound encoded con `encode(...)`.

Manejo de errores: `ConnectionClosed` se ignora silencioso (el cliente cerró entre el send y el await). Otros errores se loguean pero NO tumban el broadcast a los demás.

## Whitelist de Origins WS (anti-CSRF)

Validación crítica: el header `Origin` del handshake se compara contra `WS_ORIGINS`:

```python
# config.py
WS_ORIGINS = _env_list("ORUX_WS_ORIGINS", default=[
    "https://orux.space",
    "http://localhost:5173",
    "http://localhost:8080",
])
```

Sin esto, un sitio malicioso (`attacker.com`) podría abrir un WebSocket al server de Orux desde el navegador de la víctima (cookies no aplican a WS, pero un token de sesión robado de localStorage sí). El header `Origin` que manda el navegador NO se puede falsificar desde el script.

Conexiones SIN `Origin` (tests, healthcheck, Electron) pasan: no son del browser.

**REGLA OPERATIVA**: cada cliente nuevo del navegador debe sumarse a `ORUX_WS_ORIGINS`. `*` desactiva el filtro (solo debug puntual).

## Eviction de runtimes ociosos

`barrer_runtimes_ociosos(ttl, runtimes, rt_locks, asientos_locks, tiene_proposals_store)`:

- Cada N segundos.
- Para cada runtime: si `_vacio_desde is not None and ahora - _vacio_desde > ttl` y no hay propuestas pendientes: evict.
- Evict = cerrar todas las sesiones LSP (`reciclar_lsp`) + remover del `self._runtimes`.

Sin esto, `_runtimes` crece sin techo: cada equipo que se conectó alguna vez retiene RAM (workspace + ownership + presencia + propuestas) hasta que muere el proceso.

`barrer_runtimes_ociosos` es robusto: si `runtime_evictable` (helper que decide) explota, loguea ERROR y sigue la próxima vuelta — el loop NO muere en silencio.

## Comparación con HTTP inbound

El HTTP (`adapters/inbound/http/app.py`) es mucho más simple: cada request es independiente, no hay estado vivo del cliente. Ver [`adapters/http.md`](http.md).

El WS es "stateful": cada cliente tiene su conexión persistente, su entrada en el roster, su token de sesión vivo. Eso es lo que hace que `SyncServer` sea grande — toda esa coreografía vive acá.
