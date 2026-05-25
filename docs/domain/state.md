# Domain: state

`backend/orux/domain/state/` modela el estado vivo del workspace de un equipo: archivos, dueños, propuestas tentativas, presencia, paths seguros, colisiones por línea.

Es el **dominio puro** del producto. No sabe que existe Postgres, ni WebSockets. Recibe las mutaciones desde el `TeamRuntime` y las expone con métodos sync (las llamadas vienen ya en el loop asyncio del server, pero estos objetos son rápidos y no hacen IO).

## Archivos

| Archivo | Qué hace |
|---|---|
| `document.py` | `Document(content: str)` — wrapper trivial. Un archivo del workspace es un `Document`. |
| `workspace.py` | `Workspace` — `dict[path, Document]` con topes (50k archivos, 1MB/archivo, 256MB total). |
| `ownership.py` | `Ownership` — `dict[path, username]` (memoria pura sync con `threading.Lock`). |
| `proposals.py` | `Proposals` (en memoria) + `MemProposalsStore` (adapter persistencia in-memory para tests). |
| `presence.py` | `Roster` — presencia por equipo (quién está en qué archivo y línea). |
| `locks.py` | `lineas_tocadas(viejo, nuevo)` — qué líneas cambiaron entre dos versiones (capa 5: colisiones). |
| `paths.py` | `path_seguro(p) -> bool` — la frontera contra paths peligrosos. |
| `storage.py` | `DiskStorage` — `WorkspaceStoragePort` sync con escritura atómica + carga al boot. |

## `Workspace`

Mapa `path → Document`. La unidad de coordinación es el ARCHIVO (no el proyecto): cada archivo tiene su propio ownership, su propia presencia, su propio baseline de análisis. Decisión load-bearing desde la capa 1: por eso un cambio en `auth.py` no compite con uno en `models.py`.

```python
class Workspace:
    def __init__(self, storage: WorkspaceStoragePort | None = None): ...
    def snapshot(self) -> dict[str, str]: ...
    def exists(self, path: str) -> bool: ...
    def get_or_create(self, path: str) -> Document: ...
    def update(self, path: str, content: str) -> None: ...  # crea si no existía
    def delete(self, path: str) -> bool: ...
    def recargar(self) -> None: ...                          # para clone destructivo
    def cargar_de_disco(self) -> None: ...                   # al boot
```

**Topes blandos** (env-configurables):

| Var env | Default | Limita |
|---|---|---|
| `ORUX_WS_MAX_ARCHIVOS` | 50.000 | Número de archivos por workspace |
| `ORUX_WS_MAX_BYTES_ARCHIVO` | 1 MB | Tamaño individual |
| `ORUX_WS_MAX_BYTES_TOTAL` | 256 MB | Suma de todos los archivos en memoria |

Si un update rompería un tope, `update` levanta `WorkspaceLleno` y NO toca memoria/disco. El server traduce a un error para el cliente.

**Orden update memoria→disco**: si persistir falla (path inseguro mandado por un cliente, disco lleno, permisos), la memoria queda coherente y la retransmisión sigue funcionando. Persistir nunca debe poder tumbar el tiempo real.

## `Ownership`

Mapa `path → username`. Memoria pura sync con `threading.Lock` interno (necesario porque `claim`/`asignar`/`liberar` se llaman desde corutinas distintas y deben serializarse para no perder writes).

```python
class Ownership:
    def __init__(self, inicial: dict[str, str] | None = None): ...
    def owner(self, path: str) -> str | None: ...
    def claim(self, path: str, client_id: str) -> bool: ...
        # True = quedaste como dueño (era libre, o ya eras vos).
        # False = lo tiene otro; claim NO roba.
    def asignar(self, path: str, user: str) -> None: ...
        # SIN condiciones. Solo lo llama el admin del equipo.
    def liberar(self, path: str) -> bool: ...
        # True = había dueño y se quitó.
    def purgar_usuario(self, user: str) -> int: ...
        # Para cuando el admin borra una cuenta.
    def reset(self) -> None: ...
        # Para clone destructivo (capa 10).
    def snapshot(self) -> dict[str, str]: ...
```

**Tres reglas que NO cambian** desde la capa 4:

1. `claim` respeta al dueño actual. Ownership es coordinación, no robo.
2. `asignar` es del admin. Reparte zonas sin pedir permiso al dueño anterior (capa 12).
3. El ownership **NO se libera al desconectar**. Sobrevive cierre de pestaña, reload, reinicio del server.

## `Proposals`

Propuestas tentativas: cambios de no-dueños esperando aprobación.

```python
class Proposals:
    def make_id(path: str, author_id: str) -> str:
        # path::author_id — determinista
    def put(self, path, author_id, author_name, content) -> Proposal: ...
        # Reemplaza la propuesta vieja del mismo autor sobre el mismo path.
    def get(self, proposal_id: str) -> Proposal | None: ...
    def pop(self, proposal_id: str) -> Proposal | None: ...
    def drop_author(self, author_id: str) -> None: ...
        # Al desconectarse: sus propuestas son moot.
    def drop_path(self, path: str) -> None: ...
        # Al borrar el archivo.
    def para(self, owner_id, owner_de) -> list[Proposal]: ...
        # Para reentregar al dueño que se conecta.
    def cargar(self, proposals: list) -> None: ...
        # Hidratar desde el store al abrir el equipo.
```

**ID determinista** (`path::author_id`): mientras un dev sigue tecleando, sus updates reemplazan la propuesta en vez de acumular una por tecla. El dueño siempre ve la última.

**Reentrega**: el server llama `para(owner_id, owner_de)` al final del handshake. Si Ana propuso un cambio mientras Kai estaba offline, Kai vuelve y la ve.

**Topes** (anti-abuso, BACKEND-AUDIT-0071/-0238):

- `MAX_CONTENT_BYTES` = 1 MB (igual que un update legítimo).
- `MAX_POR_AUTOR` = 50 propuestas pendientes por autor por equipo.

Si se rebasa, `put` levanta `PropuestaInvalida`. El autor tiene que resolver/abandonar las viejas primero.

`MemProposalsStore` (en el mismo archivo) es la implementación in-memory del `ProposalsStorePort` para tests y dev. Mantiene `dict[team_id, dict[proposal_id, Proposal]]`.

## `Roster` (presencia)

Quién está en qué archivo y en qué línea, por equipo.

```python
class Roster:
    def mover(self, client_id: str, path: str, line: int) -> PresenceState | None: ...
        # None si la presencia no cambió.
    def quitar(self, client_id: str) -> None: ...
    def en_path(self, path: str) -> list[PresenceState]: ...
    def lineas_ocupadas(self, path: str, *, excepto: str) -> set[int]: ...
        # Para validar updates entrantes (colisiones por línea).
```

**Color**: cada client recibe un color del set determinista basado en hash del client_id (estable cross-conexión: si Ana vuelve, mantiene su color).

## `lineas_tocadas` (locks.py)

Para la **capa 5: colisiones por línea**. Cuando dos personas tocan el mismo archivo sin dueño:

1. La 2ª persona escribe en líneas del archivo.
2. El server compara las líneas que el update toca (`lineas_tocadas(viejo, nuevo)`) vs. las líneas ocupadas por otros (`Roster.lineas_ocupadas(path, excepto=yo)`).
3. Si hay intersección → rebote: el update se rechaza, el autor recibe el contenido viejo.

Algoritmo: LCS truncado a `_LCS_MAX_CELDAS` (perf-bound para archivos enormes). Si el LCS se sale del cap, fallback a "tocó todas las líneas" (defensivo).

## `path_seguro` (paths.py)

**La frontera contra paths peligrosos**. Se aplica al RECIBIR el mensaje, no solo al escribir.

Rechaza:

- Vacío, `.`, `..`.
- Absolutos (`/etc/passwd`, `C:\Windows`).
- Cualquier `..` interno (escapes).
- Backslashes (`a\b`).
- Segmentos vacíos (`a//b`).
- Segmentos `.` (`a/./b`).
- NUL (`\x00`).
- Control chars (`\n`, `\t`, …).
- Invisibles Unicode (zero-width, bidi-override).
- `.git/` y `.GIT/` (case-insensitive en filesystems HFS+/NTFS).

Llamado desde:

- `dispatch.py` antes de aplicar updates (M1: defensa en la frontera del mensaje).
- `DiskStorage._destino` antes de escribir.
- `Ownership.__init__` al cargar persistido (filtra paths peligrosos que un store viejo pudo tener).

## `DiskStorage` (storage.py)

Implementación canónica de `WorkspaceStoragePort`. Sync por el hot path.

```python
class DiskStorage:
    def __init__(self, root: Path | str): ...
    def guardar(self, path: str, content: str) -> None: ...
    def borrar(self, path: str) -> None: ...
    def cargar(self) -> dict[str, str]: ...
```

**Defensas** (cada una con su BACKEND-AUDIT):

- `_destino(path)`: valida `path_seguro`, resuelve, verifica que cae bajo `root`. Defensa anti-symlink intermedio (un symlink dentro del workspace que apunta afuera se rechaza con `ValueError`).
- **Atomic write**: tmp con pid+uuid + `os.replace`. Sin esto, un crash a mitad de `write_text` deja el archivo TRUNCADO en disco y al reiniciar se carga como verdad.
- **Cleanup de `.tmp` huérfanos** al boot (SIGKILL entre write y replace deja basura).
- **Filter de `.git`** case-insensitive al cargar (el workspace puede SER un repo git).
- **Tope por archivo de 2MB al cargar** (BACKEND-AUDIT-0079): un PNG de 5GB tirado por error reventaba el server al boot.
- **PermissionError/OSError por archivo se loguea y se sigue**: no aborta toda la carga (BACKEND-AUDIT-0078).
- **UnicodeDecodeError**: se loguea y se omite (binarios no soportados).

`cargar()` devuelve claves en formato POSIX (`src/auth.py`, con `/`) siempre — ese es el formato que viaja por el protocolo.
