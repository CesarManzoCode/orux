# Development: Agregar una feature

Recetas concretas para los casos más comunes.

## Caso 1: Un mensaje WS nuevo

Cuatro pasos mecánicos.

### 1. Definir el `Message`

`backend/orux/domain/protocol/messages.py`:

```python
@dataclass
class MiMensajeMessage:
    type: Literal["mi_mensaje"] = "mi_mensaje"
    campo1: str = ""
    campo2: int = 0
```

Y agregar a la `Message` union al final del archivo:

```python
Message = Union[..., MiMensajeMessage]
```

### 2. Registrar en `codec.decode`

`backend/orux/domain/protocol/codec.py`:

```python
def decode(raw):
    ...
    tipo = datos.get("type")
    if tipo == "mi_mensaje":
        return MiMensajeMessage(
            type="mi_mensaje",
            campo1=_str(datos.get("campo1")),
            campo2=_int(datos.get("campo2"), minimo=0, maximo=1000),
        )
```

Usar los helpers de `validation.py` (`_str`, `_int`, `_bool`, `_dict_str_str`, etc.) para validación tipada.

### 3. Use case en `application/use_cases.py`

```python
@dataclass
class MiCommand:
    campo1: str
    campo2: int
    autor_id: str

@dataclass
class MiResult:
    broadcast_algo: tuple[str, str] | None = None

async def mi_use_case(
    rt: "TeamRuntime",
    ownership_store: OwnershipStorePort | None,  # los Ports que necesite
    cmd: MiCommand,
) -> MiResult:
    # lógica acá
    return MiResult(broadcast_algo=("path", "content"))
```

Exportar en `application/__init__.py`.

### 4. Handler en `dispatch.py`

`backend/orux/adapters/inbound/websocket/dispatch.py`:

```python
async def _h_mi_mensaje(server, rt, websocket, yo, team_id, message):
    res = await mi_use_case(
        rt,
        server._ownership_store,
        MiCommand(
            campo1=message.campo1,
            campo2=message.campo2,
            autor_id=yo.client_id,
        ),
    )
    if res.broadcast_algo:
        path, content = res.broadcast_algo
        await server._broadcast_todos(rt, encode(SomeMessage(path=path, content=content)))

# Y agregar a la tabla:
HANDLERS = {
    ...,
    MiMensajeMessage: _h_mi_mensaje,
}
```

### 5. Test

`backend/tests/test_sync.py` (o un archivo nuevo):

```python
async def test_mi_mensaje_aplica(sync_server):
    server, port = sync_server
    async with connect(f"ws://localhost:{port}") as ws:
        await _entrar(ws)
        await ws.send(json.dumps({
            "type": "mi_mensaje",
            "campo1": "X",
            "campo2": 42,
        }))
        msg = json.loads(await ws.recv())
        assert msg["type"] == "some"
```

### 6. Frontend (si el cliente debe usarlo)

`frontend/ide/src/store.ts`:

```typescript
type MiMensajeMessage = { type: "mi_mensaje"; campo1: string; campo2: number };
type Message = ... | MiMensajeMessage;
```

Y los handlers correspondientes en el `switch (msg.type)`.

## Caso 2: Un endpoint HTTP nuevo

### 1. Use case en `application/http_use_cases.py`

```python
async def mi_operacion(teams, team_id) -> dict:
    """Lógica pura sin HTTP."""
    return {"resultado": "..."}
```

### 2. Handler en `adapters/inbound/http/app.py`

```python
async def _mi_operacion(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    tid = req.path_params["tid"]
    result = await service.mi_operacion(req.app.state.teams, tid)
    return JSONResponse(result)
```

`_gate(req)` para endpoints protegidos por bearer del operador.

### 3. Ruta en `crear_app`

```python
routes = [
    ...,
    Route("/api/v1/mi-operacion/{tid}", _mi_operacion, methods=["POST"]),
]
```

### 4. Test

`backend/tests/test_api_service.py`:

```python
async def test_mi_operacion():
    teams = MemTeamStore()
    eq = await teams.crear_equipo("test", "ana")
    result = await mi_operacion(teams, eq["id"])
    assert result["resultado"] == "..."
```

## Caso 3: Un Port nuevo

Cuando aparece una necesidad de pluggear infraestructura nueva (segundo backend git, otro proveedor de pagos, etc.).

### 1. Definir el Port en `ports/`

```python
# backend/orux/ports/mi_port.py
from typing import Protocol, runtime_checkable

@runtime_checkable
class MiPort(Protocol):
    """Doc del contrato + cuándo se usa + decisiones."""
    
    async def operacion1(self, arg: str) -> bool: ...
    async def operacion2(self) -> list[str]: ...
```

Re-exportar en `ports/__init__.py`.

### 2. Implementar adapter(s) en `adapters/outbound/`

```python
# backend/orux/adapters/outbound/mi_tecnologia/mi_adapter.py
class MiAdapter:
    def __init__(self, config_externa: str):
        self._config = config_externa
    
    async def operacion1(self, arg):
        # implementación real
        ...
```

Re-exportar en `adapters/outbound/mi_tecnologia/__init__.py`.

### 3. Contract test

`backend/tests/test_ports_contract.py`:

```python
def test_mi_adapter_cumple_port():
    assert isinstance(MiAdapter("config"), MiPort)
```

### 4. Cablear en `composition.py`

```python
async def _build_postgres(config):
    ...
    mi_adapter = MiAdapter(os.environ.get("MI_CONFIG", ""))
    return SyncServer(
        ...,
        mi_port=mi_adapter,
    )
```

Y agregar al `SyncServer.__init__` el nuevo parámetro `mi_port: MiPort | None`.

### 5. Use case que lo usa

```python
async def operacion_use_case(rt, mi_port: MiPort | None, cmd):
    if mi_port:
        result = await mi_port.operacion1(cmd.arg)
        ...
```

## Caso 4: Un campo nuevo en el dominio

Por ejemplo, agregar `Ownership` con un `claimed_at` timestamp.

### 1. Decidir si es del modelo o derivable

Si es derivable (e.g. desde logs), no lo agregues al modelo. Si es load-bearing (e.g. para "ordenar ownership por antigüedad"), sí.

### 2. Cambiar el dominio

`backend/orux/domain/state/ownership.py`:

```python
class Ownership:
    def __init__(self, inicial: dict[str, str] | None = None,
                 inicial_timestamps: dict[str, float] | None = None):
        self._owners = dict(inicial) if inicial else {}
        self._claimed_at = dict(inicial_timestamps) if inicial_timestamps else {}
        ...
    
    def claim(self, path, client_id):
        with self._lock:
            ...
            self._claimed_at[path] = time.time()
            return True
    
    def claimed_at(self, path) -> float | None:
        return self._claimed_at.get(path)
```

### 3. Cambiar los Ports (si la persistencia cambia)

Si necesitás persistir el timestamp:

```python
# ports/persistencia.py
class OwnershipStorePort(Protocol):
    async def cargar(self, team_id: str) -> tuple[dict[str, str], dict[str, float]]: ...
    async def guardar(self, team_id: str, owners: dict[str, str], timestamps: dict[str, float]) -> None: ...
```

(Cambio breaking — actualizar los 2 adapters: `JsonOwnershipStore` y `PgOwnershipStore` + schema.sql).

### 4. Schema migration

```sql
-- backend/orux/adapters/outbound/postgres/schema.sql
ALTER TABLE ownership ADD COLUMN IF NOT EXISTS claimed_at TIMESTAMPTZ DEFAULT now();
```

Idempotente (`IF NOT EXISTS`).

### 5. Tests

- `test_admin.py`: agregar caso con timestamp.
- `test_ports_contract.py`: actualizar firma esperada del Port.
- Verifica que cargar persistencia vieja sin la columna sigue funcionando (compat).

## Caso 5: Una capa de seguridad nueva

E.g. agregar validación de tamaño máximo de invitaciones.

### 1. Definir el tope en el dominio

`backend/orux/domain/teams/store.py`:

```python
_MAX_INVITES_POR_EQUIPO = 100
```

### 2. Validar en el método

```python
async def crear_invitacion(self, team_id, por_usuario):
    ...
    if len([i for i in self._invites.values() if i["team_id"] == team_id]) >= _MAX_INVITES_POR_EQUIPO:
        raise TeamError("este equipo tiene demasiadas invitaciones pendientes")
    ...
```

### 3. Replicar en `PgTeamStore`

```python
async def crear_invitacion(self, team_id, por_usuario):
    ...
    n = await con.fetchval(
        "SELECT count(*) FROM invites WHERE team_id=$1 AND usado_por IS NULL",
        team_id,
    )
    if n >= _MAX_INVITES_POR_EQUIPO:
        raise TeamError("...")
    ...
```

### 4. Test cubriendo el caso

```python
async def test_crear_invitacion_rechaza_si_tope():
    teams = MemTeamStore()
    eq = await teams.crear_equipo("test", "ana")
    for _ in range(100):
        await teams.crear_invitacion(eq["id"], "ana")
    with pytest.raises(TeamError, match="demasiadas"):
        await teams.crear_invitacion(eq["id"], "ana")
```

### 5. Documentar el tope

Agregar al `domain/teams.md` o crear si no existe. Documentar el por qué (anti-abuso, evitar leak de codes en logs, etc.).

## Caso 6: Una variable de entorno nueva

### 1. Leer del entorno con clamp

```python
# en config.py o donde corresponda
MI_TOPE = _env_int("ORUX_MI_TOPE", default=100, minimo=1, maximo=10000)
```

### 2. Documentar en `docs/operations/env-vars.md`

Agregar la variable a la tabla correspondiente con su default y rango.

### 3. Actualizar `.env.example`

```bash
# Tope de Y (default 100, clamp 1-10000)
# ORUX_MI_TOPE=100
```

Comentado por default; el operador descomenta si quiere override.

### 4. Test

```python
def test_mi_tope_env(monkeypatch):
    monkeypatch.setenv("ORUX_MI_TOPE", "50")
    # forzar re-import del módulo si MI_TOPE es module-level
    ...
```

## Convenciones de PR

- **Una feature por PR**, no múltiples mezcladas.
- **Tests obligatorios**, salvo refactor que no cambia comportamiento (en cuyo caso, la suite existente debe pasar).
- **Mensaje de commit** describe el QUÉ y POR QUÉ ("agregar tope de invitaciones por equipo (anti-leak en logs)").
- **CLAUDE.md / docs actualizados** si la feature cambia algo arquitectónico o operativo.

## Lecciones aprendidas

- **No abstraer hasta que duela**: el código por capas (1→33+) creció agregando features mínimas. Cada vez que se agregó una capa, fue porque la anterior funcionaba pero faltaba algo CONCRETO.
- **Resistir feature soup**: una capa increíble vale más que veinte mediocres.
- **Documentar el "por qué"**, no solo el "qué". Los `BACKEND-AUDIT-XXXX` en los comentarios son la trazabilidad.
- **Una dep entra cuando un cuello de botella concreto la justifica**: no preventivamente.
