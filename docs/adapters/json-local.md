# Adapter: JSON local

`backend/orux/adapters/outbound/json/` es la persistencia para **modo dev sin Postgres**. Encapsula la lógica de atomicidad/permisos/validación que vivía inline en `Ownership` y `UserStore` antes del refactor hex del 2026-05-24.

## Cuándo se usa

Cuando `ORUX_DB_DSN` está vacío. El composition root entra a `_build_dev_json` y cablea:

```python
JsonUserStore(base_dir / "users.json")
JsonOwnershipStore(base_dir / "ownership.json")
```

Modo dev = pruebas locales sin levantar Postgres. **Los equipos NO sobreviven a reiniciar** (`MemTeamStore` no persiste). Producción DEBE setear `ORUX_DB_DSN`.

## Adapters

### `JsonOwnershipStore`

```python
class JsonOwnershipStore:
    def __init__(self, path: Path | str): ...
    async def cargar(self, team_id: str) -> dict[str, str]:
        # team_id IGNORADO (single-team por diseño).
    async def guardar(self, team_id: str, owners: dict[str, str]) -> None:
        # team_id IGNORADO.
```

**Single-team por diseño**: ignora `team_id`. En modo dev multi-equipo, todos comparten el mismo JSON (mismo comportamiento que el viejo `_base_ownership` compartido entre runtimes).

Esto NO es bug; es la convención del modo dev. Si en el futuro alguien necesita multi-team JSON real, sería otro adapter (`JsonOwnershipStoreMulti` con un archivo por team_id).

### `JsonUserStore`

```python
class JsonUserStore:
    def __init__(self, path: Path | str): ...
    # implementa UserStorePort completo (async)
    async def registrar / asegurar_externo / verificar / epoch / revocar_sesiones / borrar / existe / usuarios ...
    def admin(self) -> str | None:
        # Compat con tests legacy (capa 12 pre-multi-team). Sync.
```

Mantiene `dict[username, registro]` en memoria; cada mutación hace flush al disco.

`admin()` (sync, lee dict) está para los tests del admin global (capa 12 pre-multi-team). NO está en `UserStorePort` porque producción multi-team usa rol DENTRO del equipo.

## Hardening conservado

La lógica de atomicidad y validación se conservó del código original (cada item con su BACKEND-AUDIT):

### Tmp único con pid+uuid

```python
sufijo = f".{os.getpid()}.{uuid.uuid4().hex}.tmp"
tmp = self._path.with_suffix(self._path.suffix + sufijo)
```

Sin esto, dos corutinas del mismo proceso escribiendo al mismo archivo se pisaban su propio `.tmp` (BACKEND-AUDIT-0064).

### Permisos 0600

Al crear con `os.open(tmp, O_CREAT | O_WRONLY | O_TRUNC, 0o600)`. Sin esto, otros usuarios del host pueden leer los hashes PBKDF2 de `users.json` (BACKEND-AUDIT-0013).

### `fsync` antes del replace

```python
with os.fdopen(fd, "w", encoding="utf-8") as f:
    json.dump(owners, f, indent=2, sort_keys=True, ensure_ascii=False)
    f.flush()
    os.fsync(f.fileno())
os.replace(tmp, self._path)
```

Durabilidad real ante corte de luz: sin `fsync`, el OS puede haber bufferado el write y la página queda en cache; un corte deja el archivo VIEJO en disco (no corrupto, pero sin la última escritura).

### Validación al cargar

```python
if not isinstance(data, dict):
    return {}
return {
    k: v for k, v in data.items()
    if isinstance(k, str) and isinstance(v, str) and path_seguro(k)
}
```

- JSON no-dict → arranca vacío en vez de explotar.
- Path inseguro guardado por un store viejo (o atacante) → se filtra (BACKEND-AUDIT-0066).
- Entradas con tipos malos → se descartan.

En `JsonUserStore` la validación es similar:

```python
for k, v in cargado.items():
    if not isinstance(k, str): continue
    if isinstance(v, str) or (isinstance(v, dict) and isinstance(v.get("hash"), str)):
        limpio[k] = v
```

Acepta registros legacy (string puro = hash directo) y nuevos (dict con `hash` + `epoch`).

### Lock interno (`asyncio.Lock`)

```python
async def registrar(self, username, password):
    u = validar_nuevo_usuario(username)
    async with self._lock:
        if u in self._usuarios:
            raise ValueError("ese usuario ya existe")
        self._usuarios[u] = {"hash": hash_password(password), "epoch": 0}
        await self._flush()
    return u
```

Cubre tramos check-then-set (TOCTOU). Sin esto, dos requests concurrentes con el mismo username pasaban ambos el check.

## Async con `to_thread`

Los métodos son `async` pero el IO real es sync (`json.dump`, `os.replace`). Envolvemos con `asyncio.to_thread` para no bloquear el loop:

```python
async def guardar(self, team_id, owners):
    del team_id
    await asyncio.to_thread(self._guardar_sync, owners)
```

Es estricto con el modelo asyncio: aunque para archivos pequeños (KB) el IO es ~1ms y no bloquea perceptiblemente, ser consistente previene problemas reales si el ownership crece a MB en algún momento.

## Por qué no se usa JSON en producción

- Single-writer (un solo proceso). El día que haya réplicas múltiples del server WS, el JSON deja de servir.
- Sin transacciones cross-store (no se puede atomizar "agregar miembro" + "guardar ownership inicial").
- Sin queries complejos (panel admin del operador no podría hacer "todos los equipos con plan premium con >10 miembros").
- Reload completo al boot (no scalable a workspaces gigantes).

Para todo eso está Postgres. JSON es para que un dev levante el server en su máquina sin necesidad de levantar `docker-compose up postgres`.

## Layout de los archivos

En modo dev (default `~/.orux/`):

```
~/.orux/
├── users.json          # JsonUserStore
├── ownership.json      # JsonOwnershipStore (single-team)
├── secret              # secreto HMAC (0600, generado al primer boot)
└── workspace/          # DiskStorage (el workspace en disco)
    ├── src/
    ├── tests/
    └── README.md
```

En producción (default `/data/`):

```
/data/
├── secret
└── ws/                 # DiskStorage por equipo
    ├── abc12345/       # workspace del equipo abc12345 (es un repo git real)
    │   ├── .git/
    │   ├── src/
    │   └── tests/
    └── def67890/       # workspace del equipo def67890
```

Configurable con `ORUX_DATA` (env). Decisión load-bearing: vivir FUERA del repo del proyecto (heredada de Live Server pre-React) — evita que herramientas locales (linters, watchers de IDE) crucen con el estado persistido.
