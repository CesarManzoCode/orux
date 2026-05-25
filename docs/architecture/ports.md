# Ports (contratos formales)

Un *Port* es un `typing.Protocol` que define qué necesita el dominio sin saber quién lo implementa. Es la pieza central del refactor hexagonal del 2026-05-24.

Todos los Ports viven en `backend/orux/ports/` y se re-exportan desde `orux.ports`.

## Por qué Protocols y no clases abstractas

`typing.Protocol` permite *duck typing estructural*: una clase es un Port válido si tiene los métodos con las firmas correctas — sin herencia, sin registro manual, sin acoplamiento.

El `@runtime_checkable` permite verificar con `isinstance(adapter, Port)`, lo que usamos en `tests/test_ports_contract.py` como guard rail: si alguien renombra un método del Port y se olvida del adapter, el test falla con un mensaje claro en vez de un `AttributeError` en runtime.

## Diseño sync vs async

| Port | Sync/Async | Razón |
|---|---|---|
| `WorkspaceStoragePort` | sync | El hot path (broadcast tras update) no debe pagar `await` por cada tecla. |
| Todos los demás | async | Postgres es async nativo (`asyncpg`); el server es asyncio; los stores en memoria devuelven al instante. Unifica la superficie. |

Para `WorkspaceStoragePort` el IO real es trivial (un archivo de texto por update) y queda atrapado y logueado en `Workspace.update` para no tumbar el tiempo real si falla.

## Los 11 Ports

### Persistencia (`ports/persistencia.py`)

#### `OwnershipStorePort`

Carga/guarda el mapa ownership de un equipo. El dominio (`state.Ownership`) es la verdad en memoria; este Port escribe-a-través: `cargar` al abrir el equipo, `guardar` tras cada mutación (claim / asignar / liberar / purgar_usuario / reset).

```python
class OwnershipStorePort(Protocol):
    async def cargar(self, team_id: str) -> dict[str, str]: ...
    async def guardar(self, team_id: str, owners: dict[str, str]) -> None: ...
```

Implementaciones: `adapters/outbound/json/ownership.py:JsonOwnershipStore` (modo dev) y `adapters/outbound/postgres/stores.py:PgOwnershipStore` (producción).

#### `ProposalsStorePort`

Persiste propuestas tentativas (capa 4: "editar primero, negociar después"). El hot path es el dict en memoria de `state.Proposals`; el Port escribe-a-través tras put/pop/drop_path/borrar_todo.

```python
class ProposalsStorePort(Protocol):
    async def cargar(self, team_id: str) -> list[Proposal]: ...
    async def guardar(self, team_id: str, prop: Proposal) -> None: ...
    async def borrar(self, team_id: str, proposal_id: str) -> None: ...
    async def borrar_path(self, team_id: str, path: str) -> None: ...
    async def borrar_todo(self, team_id: str) -> None: ...
```

Implementaciones: `MemProposalsStore` (tests, vive en `domain/state/proposals.py`) y `PgProposalsStore` (producción).

#### `UserStorePort`

Persiste usuarios. Async por consistencia con el resto; el adapter JSON usa `to_thread` para envolver IO sync.

```python
class UserStorePort(Protocol):
    async def existe(self, username: str) -> bool: ...
    async def usuarios(self) -> list[str]: ...
    async def registrar(self, username: str, password: str) -> str: ...
    async def verificar(self, username: str, password: str) -> bool: ...
    async def asegurar_externo(self, username: str) -> str: ...
    async def epoch(self, username: str) -> int: ...
    async def revocar_sesiones(self, username: str) -> None: ...
    async def borrar(self, username: str) -> bool: ...
```

Implementaciones: `JsonUserStore` (dev) y `PgUserStore` (producción).

#### `WebhooksStorePort`

Idempotencia de webhooks Stripe por `event_id`. Sin esto, un webhook reentregado por timeout aplicaría el cambio dos veces.

```python
class WebhooksStorePort(Protocol):
    async def marcar(self, event_id: str) -> bool: ...
    async def purgar(self, antes_de_segundos: int = ...) -> int: ...
```

`marcar` devuelve `True` si es la primera vez (insertó), `False` si ya estaba (replay).

#### `TeamStorePort`

Equipos, membresía e invitaciones. Una superficie grande pero estable; `MemTeamStore` y `PgTeamStore` la implementan idéntica.

```python
class TeamStorePort(Protocol):
    # Equipos
    async def crear_equipo(self, nombre: str, creador: str) -> dict: ...
    async def equipo(self, team_id: str) -> dict | None: ...
    async def plan(self, team_id: str) -> str: ...
    async def set_plan(self, team_id: str, plan: str) -> None: ...
    async def actualizar_suscripcion(self, team_id: str, plan: str, subscription_id: str) -> None: ...
    async def suscripcion(self, team_id: str) -> str: ...
    async def contar_miembros(self, team_id: str) -> int: ...
    async def todos(self) -> list[dict]: ...
    async def equipos_de(self, usuario: str) -> list[dict]: ...
    async def borrar(self, team_id: str) -> bool: ...
    # Membresía
    async def es_miembro(self, team_id: str, usuario: str) -> bool: ...
    async def rol(self, team_id: str, usuario: str) -> str | None: ...
    async def miembros(self, team_id: str) -> list[dict]: ...
    # Invitaciones
    async def crear_invitacion(self, team_id: str, por_usuario: str) -> str: ...
    async def redimir(self, code: str, usuario: str) -> dict | None: ...
```

#### `WorkspaceStoragePort`

Persistencia del workspace en disco. **SYNC a propósito** (ver explicación arriba).

```python
class WorkspaceStoragePort(Protocol):
    def guardar(self, path: str, content: str) -> None: ...
    def borrar(self, path: str) -> None: ...
    def cargar(self) -> dict[str, str]: ...
```

Implementación canónica: `state.DiskStorage` (vive en `domain/state/storage.py` por simplicidad histórica).

### Externos (`ports/git.py`, `ports/identity.py`, `ports/billing.py`, `ports/analysis.py`)

#### `GitPort`

Operaciones git sobre el workspace de un equipo. Las credenciales son SIEMPRE efímeras: las pasa el caller en cada operación remota, el adapter no las persiste.

```python
class GitPort(Protocol):
    def asegurar(self) -> None: ...
    def estado(self) -> EstadoGit: ...
    def commitear(self, mensaje: str, autor_nombre: str, autor_email: str) -> tuple[bool, str]: ...
    def clonar(self, url: str, usuario: str, token: str) -> tuple[bool, str]: ...
    def push(self, usuario: str, token: str, url: str | None = None, rama: str | None = None) -> tuple[bool, str]: ...
    def push_a_rama(self, usuario: str, token: str, rama: str, url: str | None = None) -> tuple[bool, str, str]: ...
```

`EstadoGit` (value object): `disponible: bool`, `rama: str`, `cambios: int`, `commits: list[str]`.

Implementación: `adapters/outbound/git/binary.py:GitRepo` (alias `GitBinaryAdapter`).

#### `SessionTokenPort`

Emite y verifica tokens de sesión HMAC.

```python
class SessionTokenPort(Protocol):
    def crear(self, username: str, ttl_seg: int | None = None, *, epoch: int = 0, kid: str | None = None) -> str: ...
    def usuario_de(self, token: str, *, epoch_de: Callable[[str], int] | None = None) -> str | None: ...
```

Implementación: `adapters/outbound/identity/hmac_session.py:HmacSessionTokenAdapter`. Es delgado: cierra el secret HMAC y delega a `identity.tokens.crear_token` / `usuario_de_token` (que siguen siendo funciones puras del dominio).

#### `OAuthPort`

Flujo OAuth de un proveedor (hoy: GitHub).

```python
class OAuthPort(Protocol):
    def url_autorizacion(self, state: str, scope: str | None = None) -> str: ...
    def firmar_state(self, ahora: float | None = None) -> str: ...
    def validar_state(self, state: str, max_edad: float = 120.0, ahora: float | None = None) -> bool: ...
    def identidad(self, perfil: dict) -> str: ...
```

Implementación: `GithubOAuthAdapter`. La parte que habla con la red (intercambiar `code` por access token + leer perfil) vive en `adapters/inbound/http/app.py:_intercambiar` y es separada del adapter.

#### `BillingPort`

Operaciones del proveedor de pagos.

```python
class BillingPort(Protocol):
    def params_checkout(self, team_id: str, success_url: str, cancel_url: str, seats: int) -> dict[str, str]: ...
    def verificar_firma_webhook(self, payload: bytes, cabecera_firma: str) -> bool: ...
    def parsear_evento(self, payload: bytes) -> dict: ...
    def event_id(self, evento: dict) -> str: ...
    def cambio_de_plan(self, evento: dict) -> tuple[str, str] | None: ...
    def suscripcion_de_evento(self, evento: dict) -> str: ...
    def params_actualizar_cantidad(self, seats: int) -> dict[str, str]: ...
    def item_id_de_suscripcion(self, suscripcion: dict) -> str: ...
```

Implementación: `StripeBillingAdapter`. Delegado a `domain.billing` (funciones puras).

#### `AnalysisPort` + `LspFactoryPort` + `LspSession`

El análisis semántico tiene tres caras:

```python
class AnalysisPort(Protocol):
    def lenguaje_de(self, path: str) -> str | None: ...
    def analizador_efectivo(self, path: str, sesion: LspSession | None) -> str: ...
    def impacto(self, workspace, path, viejo, nuevo, sesion=None) -> dict[str, list[str]]: ...
    def motivos(self, path, viejo, nuevo, sesion=None) -> dict[str, str]: ...
    def detectar_rename(self, path, viejo, nuevo) -> Rename | None: ...
    def aplicar_rename(self, contenido, viejo_nombre, nuevo_nombre) -> str: ...
    def texto_sugerencia(self, r: Rename) -> str: ...

class LspFactoryPort(Protocol):
    def arrancar(self, lang: str, ws_dir: str) -> LspSession | None: ...

class LspSession(Protocol):
    def disponible(self) -> bool: ...
    def cerrar(self) -> None: ...
```

Implementaciones: `SemanticAnalysisAdapter` y `LspFactoryAdapter`. Envuelven `domain.analysis` (funciones puras del motor).

## Contract tests

`backend/tests/test_ports_contract.py` verifica con `isinstance(adapter, Port)` que cada implementación cumple su contrato:

```python
def test_pg_ownership_cumple_port(db_dummy):
    assert isinstance(PgOwnershipStore(db_dummy), OwnershipStorePort)
```

16 tests, uno por (adapter, Port). Cuando agregás un Port nuevo o renombrás un método, este test falla con un error claro.

## Patrón de adapters delgados

Decisión consciente: los adapters NO reimplementan lógica. Las funciones puras (`crear_token`, `billing.params_checkout`, `analysis.impacto`, `tiers.cambios`, …) siguen siendo funciones puras en el dominio. El adapter solo **cierra config externa** (un secret, un client_id, una URL base) y **delega** a la función pura.

Esto evita el anti-patrón "objetificar funciones por convención hex". El valor real de hex acá es encapsular config externa para que el dominio no la conozca, no forzar el patrón "todo es un objeto".
