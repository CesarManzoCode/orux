# Seguridad: paths del cliente

Los paths que el cliente manda (en `Update`, `Delete`, `Claim`, `AdminAssign`, etc.) son **input no confiable**. Sin validación, un cliente malicioso puede escribir en `/etc/passwd`, leer archivos del host, escapar del workspace.

## El defensor: `path_seguro`

Vive en `backend/orux/domain/state/paths.py`. Es la frontera contra paths peligrosos. Se aplica **en el dispatch del mensaje**, ANTES de tocar memoria/disco.

```python
def path_seguro(p: str) -> bool:
    """True si el path es legítimo para un archivo del workspace."""
```

Rechaza (cada uno con su razón concreta):

| Patrón rechazado | Por qué |
|---|---|
| `""` (vacío) | Inservible |
| `"."`, `".."` | Auto-referencias inválidas |
| `/etc/passwd`, `C:\Windows` | Absolutos |
| `../etc/passwd`, `a/../../x` | Traversal con `..` |
| `a\b`, `a\\b` | Backslashes (evasión / ambigüedad) |
| `a//b`, `a/./b` | Segmentos vacíos / `.` |
| `a/..` | Termina en `..` |
| `x\x00.py` | NUL byte (corta argv en C) |
| `linea\nrota.py` | Control chars |
| Zero-width Unicode, bidi-override | Suplantación visual |
| `.git/foo`, `.GIT/foo`, `.Git/foo` | Repo interno (case-insensitive para HFS+/NTFS) |

Casos válidos:

- `"src/auth.py"` ✓
- `"tests/test_unit.py"` ✓
- `"README.md"` ✓
- `"feature_branch.md"` ✓
- `"design/screens/login.png"` ✓

## Dónde se aplica (M1: en la frontera del mensaje)

**Robustez M1** (auditoría): validar paths SOLO al escribir es insuficiente. Un path malicioso que pasa el dispatch pero se rechaza al escribir igual **entra al estado en memoria** y se difunde al resto del equipo como archivo fantasma.

Solución: validar en `dispatch.py` ANTES de aplicar:

```python
async def _h_update(server, rt, websocket, yo, team_id, message):
    if not path_seguro(message.path):
        return  # ignorar silencioso (no le damos info al atacante)
    res = await update_use_case(...)
```

Mismo patrón en `_h_delete`, `_h_claim`, `_h_save`, `_h_admin_assign`.

`_h_admin_assign_many` filtra path-a-path (un path inseguro en la lista no debe meter ownership fantasma ni anular el resto del reparto):

```python
for p in cmd.paths:
    if not path_seguro(p):
        continue
    ...
```

## Validación en `DiskStorage._destino`

Defensa en profundidad: aunque el dispatch ya rechazó, `DiskStorage._destino` valida de nuevo antes de escribir:

```python
def _destino(self, path):
    if not path or path in (".", "/"):
        raise ValueError(f"path inválido: {path!r}")
    
    destino = (self.root / path).resolve()
    if destino == self.root or not destino.is_relative_to(self.root):
        raise ValueError(f"path fuera del workspace: {path!r}")
    
    # Anti-symlink intermedio (BACKEND-AUDIT-0076)
    actual = self.root
    for parte in destino.relative_to(self.root).parts:
        actual = actual / parte
        if actual.is_symlink():
            real = actual.resolve()
            if not real.is_relative_to(self.root):
                raise ValueError(f"path atraviesa un symlink fuera del workspace: {path!r}")
    
    return destino
```

Validaciones:

1. **No vacío, no `.`, no `/`**.
2. **`root / path` resuelto cae bajo `root`**. Esto atrapa absolutos (`/etc/passwd` → root absorbido) y `..` (resolve los colapsa).
3. **Anti-symlink intermedio** (BACKEND-AUDIT-0076): cualquier componente del path que SEA un symlink y resuelva fuera de root → escape. Defensa contra symlinks ya plantados dentro del workspace.

### Por qué el segundo control

`path_seguro` valida la STRING del path. `_destino` resuelve EFECTIVAMENTE el FS y verifica el resultado. Casos donde el segundo control atrapa lo que el primero no puede:

- Symlink plantado: `path_seguro("link/file.py")` pasa (es un path legítimo string-wise), pero `link` es un symlink a `/etc`. Solo se ve resolviendo.
- Resolución case-insensitive en HFS+/NTFS: `.GiT/HEAD` puede pasar `path_seguro` si el case se case-insensitive-iza después; el FS lo resuelve a `.git/HEAD`.

## Validación al CARGAR (Ownership y Workspace)

`Ownership.__init__` (cuando recibía `path` antes del refactor hex; ahora vive en `JsonOwnershipStore`):

```python
return {
    k: v for k, v in data.items()
    if isinstance(k, str) and isinstance(v, str) and path_seguro(k)
}
```

Filtra paths peligrosos que un store viejo pudo haber persistido o que un atacante inyectó editando `ownership.json` directamente (BACKEND-AUDIT-0066). Si una entrada no pasa: se ignora, no se levanta error.

`DiskStorage.cargar` tiene filtros adicionales al cargar archivos del disco:

- **Filtro `.git/`** case-insensitive (workspace puede SER un repo git).
- **Filtro `.<pid>.tmp`** (BACKEND-AUDIT-0236): solo los temporales con pid (de escrituras atómicas a medias), no archivos legítimos `config.tmp` del repo.
- **Tope 2MB por archivo** al cargar (BACKEND-AUDIT-0079): un PNG/zip de GB no se carga (workspace de orux es código de texto, no binarios grandes).
- **PermissionError/OSError por archivo**: se loguea y se sigue, no aborta toda la carga (BACKEND-AUDIT-0078).
- **UnicodeDecodeError**: archivo binario que alguien dejó en la carpeta — se loguea y se omite.

## Formato POSIX consistente

`DiskStorage.cargar` devuelve claves en formato POSIX (`src/auth.py` con `/`) SIEMPRE, aunque el FS use `\\`:

```python
rel = p.relative_to(self.root).as_posix()
```

Razón: ese es el formato que viaja por el protocolo y con el que el resto del sistema indexa el workspace. Sin esto, un equipo en Windows tendría keys `src\\auth.py` y un cliente Linux no las matchearía.

## Defensas adicionales relacionadas

### Tope de tamaño por archivo y workspace

- `MAX_BYTES_ARCHIVO` = 1 MB en updates (alineado con `MAX_FRAME_BYTES`).
- `MAX_BYTES_TOTAL` = 256 MB en suma del workspace.
- `MAX_ARCHIVOS` = 50.000.

`Workspace.update` levanta `WorkspaceLleno` si rebasaría. NO toca memoria/disco. El server lo propaga como error al cliente.

### Tope al cargar de disco

`DiskStorage._MAX_BYTES_CARGAR = 2 MB` por archivo. Un PNG/zip que un dev dejó en el repo NO entra al workspace en memoria. Se loguea warning y se omite.

### Cleanup de `.tmp` huérfanos al boot

`DiskStorage._limpiar_tmps_huerfanos` barre `*.<digits>.tmp` cuyo pid no está vivo. Sin esto, SIGKILL entre `write` y `replace` deja basura acumulando.

## Tests

`backend/tests/test_robustez.py` cubre exhaustivamente:

- `path_seguro` con cada patrón rechazado.
- `DiskStorage._destino` con symlinks reales (creados en `tmp_path`).
- Update con path inseguro: NO entra al workspace ni al ownership.
- Cleanup de `.tmp` huérfanos.

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| Cliente manda Update y nada pasa | `path_seguro(path) == False` — el dispatch lo descartó silencioso |
| Logs `path atraviesa un symlink fuera del workspace` | Alguien plantó un symlink dentro del workspace que apunta a fuera de root. Investigar |
| Logs `archivo demasiado grande, se omite: PATH (N bytes)` | Alguien dejó un binario gigante en el workspace. Borrarlo manualmente |
| Logs `no se pudo leer X: PermissionError` | Permisos rotos en `/data/ws/<team_id>`. `chown -R orux:orux ...` |

## Por qué silencio (no error)

Si el dispatch detecta path inseguro, lo IGNORA silencioso. NO manda un `AuthError` al cliente. Razón:

- **No darle información al atacante**: un error explícito le dice "ese path lo rechazo por X razón" → puede iterar.
- **Cliente legítimo nunca manda paths inseguros**: si lo hace, es bug del cliente y se ve en logs del browser.
- **Cliente atacante**: el silencio le hace creer que el path "se aplicó" sin que se aplique. Maximiza confusión, minimiza pista.

Lo único que se loguea es un `logger.warning` en el server para auditoría del operador.
