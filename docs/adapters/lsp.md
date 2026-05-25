# Adapter: LSP

`backend/orux/adapters/outbound/analysis/lsp_factory.py` es el adapter delgado de `LspFactoryPort`. La lógica real del cliente LSP vive en `domain/analysis/lsp.py` (es parte del motor de análisis).

Esta separación responde a: la sesión LSP **es** un detalle del análisis (no infraestructura genérica). El factory adapter es el wrapper que el caller usa para arrancar sesiones; el dominio del análisis sabe qué hacer con ellas.

## El adapter

```python
class LspFactoryAdapter:
    def arrancar(self, lang: str, ws_dir: str) -> LspSession | None:
        return arrancar_lsp(lang, ws_dir)
```

Trivial. Delega a `domain.analysis.lsp.arrancar_lsp` que orquesta el spawn + handshake para los 4 lenguajes soportados.

## `arrancar_lsp(lang, ws_dir) -> SesionLSP | None`

Por lenguaje:

- `"py"` → `arrancar_pyright(ws_dir)` (binario `pyright-python-langserver`).
- `"jsts"` → `arrancar_tsserver(ws_dir)` (binario `typescript-language-server`).
- `"go"` → `arrancar_gopls(ws_dir)` (binario `gopls`).
- `"rust"` → `arrancar_rust_analyzer(ws_dir)` (binario `rust-analyzer`).

Cada `arrancar_*` hace:

1. Spawn del subprocess con `subprocess.Popen` (stdin/stdout pipes).
2. Handshake LSP: enviar `initialize` con `rootUri = file://<ws_dir>`, recibir respuesta, enviar `initialized`.
3. Devolver `SesionLSP` viva.

Si algo falla: loguea razón exacta + cola de stderr (NO degrada silencioso) y devuelve `None`. El caller maneja `None` como "sin Tier 0 para este lenguaje" — degrada a tree-sitter / AST / regex.

## `SesionLSP`

Wrapper sobre el subprocess + cliente LSP genérico.

```python
class SesionLSP:
    def disponible(self) -> bool:
        # True si el subprocess está vivo y el cliente puede mandar requests.
    
    def cerrar(self) -> None:
        # Envía `shutdown` + `exit` LSP; mata el subprocess.
    
    # Métodos internos que usa el motor de análisis:
    def documentSymbol(self, uri) -> list[dict]
    def references(self, uri, line, character) -> list[dict]
    def didOpen(self, uri, text, lang) -> None
    def didChange(self, uri, text) -> None
    # ...
```

## Lifecycle por equipo

El factory adapter NO mantiene cache. El cache vive en `TeamRuntime.lsp_sesion(lang, cap_langs)`:

```python
def lsp_sesion(self, lang, cap_langs=None):
    """Sesión LSP de ESTE equipo para `lang`, tibia.
    Lazy: se arranca UNA vez al 1er análisis de ese lenguaje y se reusa.
    None si el lenguaje no tiene server / no hay dir / cooldown tras fallo.
    """
```

Lógica del cache (en `runtime.py`):

### Lazy start

La primera vez que se llama para un lenguaje, arranca y guarda en `self._lsp[lang]`. Ahorra arrancar pyright para un equipo que NO toca Python.

### Detección de muerte

Si la sesión cacheada existe pero `.disponible() == False` (subprocess crashed): la descarta y reintenta arrancar.

Antes el cache guardaba `None` para siempre tras un fallo — si pyright crasheaba una vez (env sin libatomic, OOM), la degradación era permanente. Ahora cada entrada es un `_LspEstado` que sabe si la sesión está viva y si toca reintentar.

### Reintento exponencial

Tras un fallo, `cooldown_seg = min(1800, 60 * (2 ** intentos_fallidos))`:

| Intento | Cooldown |
|---|---|
| 1 | 60s |
| 2 | 120s |
| 3 | 240s |
| 4 | 480s |
| 5+ | 1800s (30 min, tope) |

Sin tope, un entorno roto de raíz peletearía el spawn cada análisis (`pyright-python-langserver` cuesta CPU). Con tope, permite auto-recuperar cuando el operador arregla el entorno (`apt install libatomic1`, liberar RAM).

### Cap por plan (capa 22)

```python
cap_langs = limites(plan)["max_langs"]  # free=2, premium=INF

if cap_langs is not None and estado is None and self._lsp_lenguajes_activos() >= cap_langs:
    return None  # plan free, ya hay 2 lenguajes activos
```

`cap_langs` solo aplica a lenguajes NUEVOS (sin `_LspEstado` previo). Si ya teníamos estado para `"py"` y volvemos a pedirlo, no lo bloqueamos por estar en el cap — ya contó alguna vez.

### Eviction de sesiones ociosas

`evictar_lsp_ociosas(ttl)`: cierra las sesiones sin uso hace más de TTL segundos. La RAM escala con equipos **activos**, no totales.

```python
def evictar_lsp_ociosas(self, ttl):
    ahora = time.monotonic()
    for lang in list(self._lsp):
        if ahora - self._lsp_uso.get(lang, ahora) < ttl:
            continue
        sesion = self._lsp[lang].sesion
        if sesion: sesion.cerrar()
        del self._lsp[lang]
        del self._lsp_uso[lang]
```

`ttl` se elige generoso: tan largo que es casi seguro que el equipo se fue, no que está pensando un rato. Default operativo: 30 min sin uso = evict.

### Reciclar al clone destructivo

`reciclar_lsp()`: mata TODAS las sesiones y fuerza re-arranque al próximo análisis. Lo llama el flujo de clone (capa 15): el clone cambia TODO el workspace ⇒ el índice de cada server LSP quedó obsoleto.

## Pyright: tres trampas históricas en `python:3.12-slim` (VPS)

Documentadas en CLAUDE.md y en los comentarios del código. Cada una me costó debugging real:

### 1. `libatomic.so.1` falta

`pyright-python` (el paquete pip) baja un Node prearmado que enlaza `libatomic.so.1`. La imagen `python:3.12-slim` no la trae → al arrancar el subprocess Node falla con:

```
node: error while loading shared libraries: libatomic.so.1: cannot open shared object file
```

→ pyright no levanta → análisis degrada MUDO a Tier 1/2/3.

**Fix**: `apt install libatomic1` en el Dockerfile.

### 2. `PYRIGHT_PYTHON_CACHE_DIR` debe ser writable

pyright-python escribe en su cache (lock/chequeos) en cada arranque. Si el directorio es read-only para el usuario runtime no-root, el langserver no inicia.

**Fix**: `chown -R orux:orux $PYRIGHT_PYTHON_CACHE_DIR` en el Dockerfile, NO `chmod a+rX` (no le da write a `orux`).

### 3. `documentSymbol` no rellena `detail`

Diseño de pyright: el `documentSymbol` (lista de símbolos del archivo) **no rellena la firma en `detail`**. Si lo usás para DETECTAR qué cambió, no ves nada porque las firmas vienen vacías.

**Decisión arquitectónica**: la detección de cambios de interfaz la hace la jerarquía AST/tree-sitter (Tier 1/2). pyright aporta SOLO el fan-out (`references`: quién usa de verdad un símbolo).

## Lección transversal: degradación silenciosa = invisible

Un componente que **degrada en silencio** es invisible en producción. Las 3 trampas de arriba habrían sido a ciegas si `arrancar_pyright` no logueara la razón exacta + cola de stderr al fallar.

Hoy:

```python
def arrancar_pyright(ws_dir):
    try:
        proc = subprocess.Popen([...], stdout=PIPE, stdin=PIPE, stderr=PIPE)
        # handshake
        return SesionLSP(proc, ...)
    except FileNotFoundError as e:
        logger.warning("LSP py NO disponible: pyright-python-langserver no encontrado en PATH")
        return None
    except Exception as e:
        cola_stderr = _scrubear_stderr(proc.stderr.read())
        logger.warning("LSP py NO disponible -> análisis degrada. Razón: %s | stderr: %s", e, cola_stderr)
        return None
```

Cualquier fallo de LSP queda en los logs con razón legible. El operador puede `docker compose logs orux | grep LSP` y entender qué arreglar.

## Por qué el adapter es solo 4 líneas

El factory adapter es trivial porque toda la lógica está en `arrancar_lsp` (que sigue siendo función pura del dominio). El valor de tenerlo como Port:

1. **Tests pueden mockear `LspFactoryPort`** sin parchear `arrancar_lsp` globalmente.
2. **Si entra otro motor LSP** (servicio externo, language server embebido), es otro adapter.
3. **Documenta que arrancar LSP es un efecto externo** del sistema.

Los tests reales que ejercitan LSP de verdad (`test_lsp.py`) están marcados con `@pytest.mark.slow` porque levantar pyright cuesta ~5s en CI.

## El `LspSession` Protocol

El runtime solo necesita 2 métodos para el lifecycle:

```python
class LspSession(Protocol):
    def disponible(self) -> bool: ...
    def cerrar(self) -> None: ...
```

El resto del comportamiento (documentSymbol, references, etc.) lo consume el adapter del análisis internamente — el caller (runtime) no lo conoce.

Esto es importante porque permite que en tests un objeto dummy con esos 2 métodos cuente como `LspSession` válida.
