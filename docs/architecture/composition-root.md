# Composition root

El composition root es **el único lugar donde se decide qué adapter concreto cumple cada Port**. Vive en `backend/orux/composition.py`.

`__main__.py` solo carga config (env vars + filesystem) y llama al composition; el composition arma el grafo completo y devuelve un `SyncServer` listo para correr.

## `AppConfig`

```python
@dataclass(frozen=True)
class AppConfig:
    base_dir: Path     # directorio raíz del estado (~/.orux por defecto)
    secret: str        # secreto HMAC para tokens de sesión
    dsn: str = ""      # vacío = modo dev (JSON local); seteado = Postgres
    host: str = "localhost"
    port: int = 8765
```

`AppConfig.desde_env(base_dir, secret)` lee:

- `ORUX_DB_DSN`: si está, modo Postgres.
- `ORUX_HOST`: default `localhost`.
- `ORUX_PORT`: default `8765`.

## `build_server(config) -> SyncServer`

Dos modos, elegidos por la presencia/ausencia de `dsn`:

### Modo Postgres (producción)

```python
async def _build_postgres(config: AppConfig) -> SyncServer:
    db = await Database.conectar(config.dsn)
    ws_root = config.base_dir / "ws"
    
    users = PgUserStore(db)
    teams = PgTeamStore(db)
    ownership_store = PgOwnershipStore(db)
    proposals_store = PgProposalsStore(db)
    
    def _runtime_factory(team_id: str) -> TeamRuntime:
        d = ws_root / team_id
        return TeamRuntime(
            team_id=team_id, storage=DiskStorage(d), git=GitRepo(d),
        )
    
    return SyncServer(
        users=users, teams=teams,
        ownership_store=ownership_store, proposals_store=proposals_store,
        runtime_factory=_runtime_factory,
        secret=config.secret,
    )
```

Características:

- **Metadatos en Postgres** (users, teams, ownership, proposals, webhooks).
- **Workspace de cada equipo es su propio repo git** en `/data/ws/<team_id>/`.
- Cada equipo: aislado en DB Y en filesystem. Sigue valiendo "git clone basta" — cada carpeta es un repo de verdad.

### Modo JSON local (dev)

```python
def _build_dev_json(config: AppConfig) -> SyncServer:
    ws = config.base_dir / "workspace"
    users = JsonUserStore(config.base_dir / "users.json")
    ownership_store = JsonOwnershipStore(config.base_dir / "ownership.json")
    
    return SyncServer(
        storage=DiskStorage(ws),
        users=users,
        ownership_store=ownership_store,
        secret=config.secret,
        git=GitRepo(ws),
    )
```

Características:

- **Single-team implícito**: un solo workspace, todos los equipos comparten el mismo JSON de ownership.
- **Los equipos NO sobreviven a reiniciar** (MemTeamStore no persiste): por eso producción DEBE setear `ORUX_DB_DSN`.
- Útil para correr local sin Postgres.

## Por qué hay un composition root explícito

Antes del refactor hex, el cableado vivía dentro de `__main__.py` con `if dsn: ... else: ...`. Funcionaba, pero:

1. **No era testeable end-to-end**: para probar el grafo cableado había que importar `__main__` y eso arrastraba `signal.add_signal_handler` y otras cosas que no querés en tests.
2. **No era reusable**: si mañana querés un CLI / script de migración / job programado, tenías que duplicar el wiring.
3. **No estaba documentado dónde se decide cada Port**: leer `sync.py` no te decía qué hay detrás de `users`.

Con `build_server(config)`, todo lo anterior se resuelve. El `__main__` queda en ~15 líneas, todas de setup operativo (señales, logging, await):

```python
async def _amain() -> None:
    base = Path(os.environ.get("ORUX_DATA") or BASE_POR_DEFECTO)
    base.mkdir(parents=True, exist_ok=True)
    secret = _secreto(base)
    config = AppConfig.desde_env(base_dir=base, secret=secret)
    server = await build_server(config)
    
    tarea_principal = asyncio.create_task(server.run(config.host, config.port))
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, tarea_principal.cancel)
    try:
        await tarea_principal
    except asyncio.CancelledError:
        logger.info("server: shutdown limpio por señal")
```

## Cómo agregar un nuevo adapter

Pasos exactos:

1. **Definir el Port** (si no existe ya) en `backend/orux/ports/`.
2. **Implementar el adapter** en `backend/orux/adapters/outbound/<tecnología>/`.
3. **Agregarlo al test contract** (`backend/tests/test_ports_contract.py`) con un `isinstance` check.
4. **Cablearlo en `composition.py`**: agregar el modo o variante que corresponda.
5. **Tests de integración** opcionales sobre el adapter solo.

## Lo que NO se decide en composition

- **El secreto HMAC** (`secret`): lo arma `_secreto(base)` en `__main__.py` (lee `ORUX_SESSION_SECRET` env o `~/.orux/secret` file; crea el file si no existe).
- **El healthcheck** del proceso `api`: vive en el `app.py` HTTP, no en composition.
- **Tasks de fondo** (eviction de runtimes, purga de webhooks): se levantan en `SyncServer.run(...)` y en `_lifespan` de la app HTTP.

Esos son detalles operativos del runtime, no del cableado de adapters.

## El proceso `api` (HTTP)

El `api` tiene su propio `__main__` (`adapters/inbound/http/__main__.py`) que arma su Starlette con `crear_app(users, teams, webhooks)`. Su composition es menor porque solo necesita stores Postgres (no usa los Mem* ni JSON):

```python
db = await Database.conectar(dsn)
users = PgUserStore(db)
teams = PgTeamStore(db)
webhooks = PgWebhooksStore(db)
app = crear_app(users, teams, webhooks)
```

Es deliberadamente **un proceso aparte** del WebSocket server. Un fallo en `api` no tumba la colaboración.
