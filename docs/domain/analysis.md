# Domain: analysis

`backend/orux/domain/analysis/` es el motor del análisis semántico: detectar qué cambios importan a otros archivos, propagarlos, detectar renames. Es **el** diferencial del producto.

## Estructura

```
analysis/
├── modelo.py       Simbolo (firma + init + superficie), severidad_de, cambios_que_importan_modelo
├── tiers.py        Jerarquía: LSP → AST → tree-sitter → regex
├── python.py       Tier 1 (ast stdlib)
├── treesitter.py   Wrapper sobre tree-sitter
├── javascript.py   Tier 2 (tree-sitter JS/TS)
├── go.py           Tier 2 (tree-sitter Go)
├── rust.py         Tier 2 (tree-sitter Rust)
├── lsp.py          Tier 0 (cliente LSP genérico + arrancar_lsp por lenguaje)
├── transitive.py   Onda transitiva por interfaz contaminada (premium)
└── rename.py       Detección de rename de miembro + codemod
```

## La pregunta que resuelve

Cuando un dev cambia un archivo, ¿a quién le importa? Si Ana cambia la firma de `Usuario.get_id() -> int` a `Usuario.get_id() -> UUID`, ¿qué archivos USAN ese método y por lo tanto se rompen?

Esto es lo que el cliente del IDE espera al hacer Ctrl+S. La respuesta tiene que ser **rápida** (sub-segundo), **precisa** (sin falsos positivos que ahoguen el aviso) y **honesta** (si no se puede analizar, decirlo, no inventar).

## La jerarquía de tiers (capa 16)

Por archivo corre el tier más profundo disponible:

| Tier | Lenguajes | Motor | Para qué |
|---|---|---|---|
| **0 LSP** | Python, JS/TS, Go, Rust | pyright / typescript-language-server / gopls / rust-analyzer | Solo el *fan-out* (resolución real de "quién usa este símbolo") |
| **1 AST** | Python | `ast` de la stdlib | Extracción de símbolos + firma + superficie |
| **2 tree-sitter** | JS/TS, Go, Rust | tree-sitter (parser C universal) | Igual que AST pero genérico |
| **3 regex** | fallback | Token-scan | Cuando no hay tier mejor disponible |

`tiers.tier_para(path)` elige el tier por extensión. `tiers.lenguaje_de(path)` devuelve el lenguaje canónico (o `None` si el archivo no es de un lenguaje soportado).

`tiers.analizador_efectivo(path, sesion)` devuelve qué analizador EFECTIVAMENTE se usó (para el chip del cliente: si la sesión LSP estaba caída, dice `"ast"` no `"lsp"`).

## El modelo `Simbolo`

```python
@dataclass(frozen=True)
class Simbolo:
    nombre: str          # "Usuario", "get_id", …
    firma: str           # "(self, id: int) -> User" o "(name: string)" según lenguaje
    init: str            # contenido del __init__ (para clases Python) — relevante en rename
    superficie: frozenset[str]  # atributos públicos de la clase / interfaz exportada
```

Es el shape común que todos los tiers producen. Lo crítico es:

- **`firma`**: dos firmas distintas = la interfaz cambió = quien usa el símbolo se rompe (severidad alta).
- **`init`**: cambios en el constructor de una clase importan a quien la instancia.
- **`superficie`**: atributos públicos. Cambiar un atributo de `pub` a `priv` afecta a quien lee `obj.X`.

`cambios_que_importan_modelo(viejo, nuevo) -> dict[nombre, motivo]` compara dos sets de Simbolo y devuelve qué cambió que importa. Motivos típicos:

- `"se renombró firma"` (severidad alta).
- `"se quitó del API público"` (severidad alta).
- `"cambió __init__"` (severidad media).
- `"se agregó al API"` (severidad baja).

`severidad_de(motivo) -> "alta" | "media" | "baja"` clasifica para el chip de color del cliente.

## El motor `impacto`

```python
# orux/domain/analysis/__init__.py
def impacto(workspace, path, viejo, nuevo, sesion=None) -> dict[str, list[str]]:
    """Símbolo cambiado en `path` → otros archivos que lo referencian."""
    lang = tiers.lenguaje_de(path)
    if lang is None:
        return {}
    cambiados = tiers.cambios(path, viejo, nuevo, sesion)
    if not cambiados:
        return {}
    tier = tiers.tier_para(path)
    return tiers.archivos_afectados(
        path, workspace, nuevo, list(cambiados), lang, tier, sesion,
    )
```

`tiers.cambios(path, viejo, nuevo, sesion) -> dict[nombre, motivo]`:

- Llama al tier disponible para extraer símbolos del viejo y nuevo.
- Aplica `cambios_que_importan_modelo` para filtrar SOLO los cambios que afectan a quien usa.

`tiers.archivos_afectados(path, workspace, nuevo, simbolos, lang, tier, sesion)`:

- Para cada símbolo cambiado, busca quién lo usa en el workspace.
- Con sesión LSP viva: usa `paths_que_referencian` (resolución REAL de pyright/etc).
- Sin sesión: token-scan por símbolo (degradado pero no ciego).

**Lección documentada del LSP** (BACKEND-AUDIT-LSP-fallback): LSP silencio ≠ "sin uso real". Si LSP devuelve `refs=[]` para un símbolo, podría ser un import roto del cliente — degradamos a token-scan POR símbolo en vez de asumir cero usos. Cuesta perf pero no mata avisos.

## El motor `motivos`

```python
def motivos(path, viejo, nuevo, sesion=None) -> dict[str, str]:
    """Símbolo cambiado → POR QUÉ su cambio le importa a quien lo usa."""
    return tiers.cambios(path, viejo, nuevo, sesion)
```

Mismo cálculo que `impacto`, devuelve los motivos legibles. El cliente los muestra junto al aviso para que NO sea "algo cambió" sino "se renombró X→Y" o "cambió la firma".

## Impacto transitivo (`transitive.py`)

Premium. La onda expansiva de un cambio.

**Decisión clave**: transitivo NO es "referencias de referencias" (eso explota en ruido — justo lo que mataron las capas 16-19). Es **propagación por INTERFAZ CONTAMINADA**:

```
1. Cambio de S llega a R que lo usa.
2. Para cada símbolo T de R que menciona a S:
   · Si S aparece en la INTERFAZ de T (firma/init/superficie):
     → la interfaz de T quedó contaminada
     → se avisa Y se propaga (los que usan T también están en la onda)
   · Si S aparece SOLO en el CUERPO de T:
     → la interfaz de T NO cambió
     → se avisa TERMINAL (revisá) y la onda CORTA ahí
```

`impacto_transitivo(workspace, path, syms_cambiados, *, fan_out, extraer, lenguaje_de, max_prof=4, max_nodos=200)`:

- BFS sobre la frontera (símbolo, archivo).
- `visitados` corta ciclos.
- `max_prof` y `max_nodos` acotan la explosión combinatoria con truncado HONESTO (`truncado=True` en el output).

Eso acota la explosión y es lo honesto. Reusa `Simbolo` (capa 16) y el fan-out (LSP en deploy, falso en tests). Ciclos por visitados; profundidad y presupuesto de nodos con truncado honesto (nunca cuelga, nunca miente).

**Decisión adicional**: el transitivo NO usa LSP a propósito (costo de cómputo — un símbolo aguas-abajo no justifica el round-trip a pyright). Su analizador efectivo es el del tier sin LSP — el chip del cliente refleja eso (no engaña).

## Rename detection (`rename.py`)

Detecta renames de miembro CONFIABLES entre dos versiones del mismo archivo.

```python
@dataclass(frozen=True)
class Rename:
    clase: str       # "Usuario"
    viejo: str       # "get_id"
    nuevo: str       # "obtener_id"

def detectar_rename(viejo_simbolos, nuevo_simbolos) -> Rename | None:
    """Detecta UN rename confiable (1 quitado + 1 agregado consistente)."""
```

**Reglas de confiabilidad** (todas tienen que cumplirse):

1. **Exactamente 1 quitado y 1 agregado** en la misma clase.
2. **Mismas firmas** (mismos parámetros y tipo de retorno).
3. **Guardia del `__init__`** (Python): si el `__init__` cambió, se relaja si los cambios son CONSISTENTES con el rename (capa 26b, 2026-05-20): un rename de `self.X = Y` cuenta como rename de atributo.

Si no se cumplen las 3 reglas, NO es un rename detectable → impacto normal.

**Caso real del usuario** (capa 26b): rename mezclado (2 quitados + 1 agregado) NO califica como rename, sigue sin codemod a propósito. El dev tiene que aplicarlo manual o aprobarlo paso a paso.

### `aplicar_rename(contenido, viejo, nuevo) -> str`

Codemod heurístico. Reemplaza `viejo` por `nuevo` con word-boundary, no en strings/comentarios, no en attribute access incorrecto.

**Guardas** (BACKEND-AUDIT):

- Si `viejo` o `nuevo` están vacíos → no toca (BACKEND-AUDIT-0231): un viejo vacío convertía el patrón en `\.\b` que pisaba cada punto.
- Word-boundary estricto.

### `texto_sugerencia(r: Rename) -> str`

Genera el texto accionable para el aviso free:

```
"se renombró Usuario.get_id → obtener_id; actualizá los usos"
```

Reemplaza el motivo genérico ("se renombró firma") cuando hay rename detectado pero el plan no aplica el codemod (free). La onda como tal se manda igual, solo cambia el texto.

## LSP (Tier 0)

`analysis/lsp.py` tiene el cliente LSP genérico (`ClienteLSP`, `SesionLSP`) y los arrancadores por lenguaje (`arrancar_pyright`, `arrancar_tsserver`, `arrancar_gopls`, `arrancar_rust_analyzer`).

`arrancar_lsp(lang, ws_dir) -> SesionLSP | None` orquesta:

1. Spawn del subprocess (`pyright-python-langserver`, `typescript-language-server`, `gopls`, `rust-analyzer`).
2. Handshake LSP (initialize + initialized).
3. Devuelve la `SesionLSP` viva o `None` si falló.

`paths_que_referencian(sesion, raiz, simbolo)` es el USO REAL: pregunta al LSP "quién usa este símbolo de verdad" (no token-scan).

**Tres trampas históricas con pyright en `python:3.12-slim`** (documentadas en CLAUDE.md):

1. **`libatomic.so.1` falta** → pyright-python (Node prearmado) crashea silencioso. Fix: `apt install libatomic1`.
2. **`PYRIGHT_PYTHON_CACHE_DIR` debe ser writable** por el usuario runtime no-root.
3. **`documentSymbol` de pyright NO trae firma en `detail`** → no detecta cambios. Regla: detección con AST/tree-sitter (capa 1/2), fan-out con LSP (capa 0).

Lección transversal: un componente que **degrada en silencio** es invisible en producción. `arrancar_lsp` loguea la razón exacta + cola de stderr; sin esa instrumentación las 3 trampas habrían sido a ciegas.

### Lifecycle por equipo (en `runtime.py`)

`TeamRuntime.lsp_sesion(lang, cap_langs)` cachea la sesión por equipo+lenguaje:

- **Lazy**: se arranca al 1er análisis de ese lenguaje.
- **Reintento exponencial**: si falla arrancar, cooldown crecente (60s → 120s → 240s → … → 30 min). Auto-recupera si el operador arregla el entorno en caliente.
- **Detección de muerte**: si la sesión cacheada murió (subprocess crash, OOM), se descarta y se reintenta. Antes cacheaba `None` para siempre y la degradación era permanente.
- **Cap por plan**: si `cap_langs` (free=2, premium=INF) ya está consumido, no arranca un lenguaje nuevo (degrada a tree-sitter/coarse).
- **Eviction de sesiones ociosas** (`evictar_lsp_ociosas(ttl)`): cierra las sin uso hace más de TTL. La RAM escala con equipos ACTIVOS, no totales.

## Cómo se invoca todo esto

El use case `application/impacto.py:calcular_impacto_save` orquesta:

1. Lee `plan = await teams.plan(team_id)`, `cap_langs = limites(plan)["max_langs"]`.
2. Hilo (no event loop): obtiene `sesion = rt.lsp_sesion(lang, cap_langs)`; llama `impacto + motivos + analizador_efectivo`.
3. Reagrupa `símbolo → archivos` ↦ `archivo_afectado → símbolos`.
4. Para cada archivo afectado con dueño: arma `ImpactMessage`.
5. Si plan premium: arranca onda transitiva (otra `asyncio.to_thread`) y agrega mensajes.

El inbound (`server/impacto.py`) recibe los mensajes y los entrega a cada dueño con `_enviar_a`.

Esto se documenta end-to-end en [`flows/save-and-impact.md`](../flows/save-and-impact.md).
