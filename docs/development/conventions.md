# Development: Convenciones

Las convenciones que aplicamos en el código del backend de Orux. Algunas vienen del usuario (decisiones DECRETADAS), otras emergen de la práctica.

## Idioma

**Español en todo**: nombres de funciones, comentarios, mensajes de commit, documentación, mensajes de error al usuario, identificadores.

Excepciones:

- Términos técnicos sin traducción consolidada (`websocket`, `lock`, `pool`, `dispatch`, `runtime`).
- Vocabulario del protocolo (`Message`, `decode`, `encode`).
- APIs externas (`Stripe-Signature`, `Authorization`, `Bearer`).

## Comentarios

Default: NO comentarios. Solo cuando el WHY es no-obvio.

Comentarios que SÍ van:

- **Hidden constraint o invariante**: "el lock cubre check + assignación (TOCTOU BACKEND-AUDIT-0026)".
- **Workaround específico**: "pyright-python crashea sin libatomic1 (BACKEND-AUDIT-LSP-1)".
- **Decisión load-bearing**: "ID determinista (path::author_id): mientras el autor sigue tecleando, reemplaza la propuesta en vez de acumular".
- **Trampa que sorprende al lector**: "_state_consumir DEBE ser sync: el GIL hace atómico check+add; un await rompe la garantía".

Comentarios que NO van:

- "incrementa el contador" (eso lo dice el código).
- "para X feature" (decay rápido).
- "added by Y" (información para git blame).

Excepción consciente para el prototipo de Orux: comentarios **educativos dirigidos al usuario** (founder técnico), explicando arquitectura y decisiones. Decisión del usuario para acelerar onboarding suyo + futuros devs. Esto va en docstrings y comentarios de bloque.

## BACKEND-AUDIT-XXXX

Cada decisión de seguridad o robustez lleva un identificador `BACKEND-AUDIT-XXXX` en los comentarios:

```python
# Lock cubre el check + assignación (TOCTOU BACKEND-AUDIT-0026).
with self._lock:
    if u in self._usuarios:
        raise ValueError("ese usuario ya existe")
    ...
```

Permite trazabilidad:

```bash
git log -S "BACKEND-AUDIT-0026" --oneline
# → commit que introdujo la decisión, con su contexto
```

Si encontrás un comentario con BACKEND-AUDIT y querés el contexto: git log con ese identificador.

Más de 50 BACKEND-AUDITs en el backend. Cada uno es una lección documentada.

## Naming

### Funciones y métodos

`snake_case`, español:

```python
def claim(path, client_id) -> bool: ...
def calcular_impacto_save(rt, teams, ...): ...
def _es_admin_o_logear(team_id, user_id, contexto) -> bool: ...
```

Acción verbal explícita. Para funciones que devuelven bool: `es_*`, `tiene_*`, `permite_*`, `puede_*`.

Métodos privados con `_` prefix.

### Clases

`PascalCase`, español o término técnico:

```python
class TeamRuntime: ...
class Workspace: ...
class GitRepo: ...
class PgOwnershipStore: ...   # técnico OK por "Pg" + "Store"
```

### Variables

`snake_case`, español. Acepta abreviaciones comunes:

```python
team_id = "abc12345"
autor_id = "ana"
rt = self._runtimes[team_id]   # "runtime"
ws = websocket                  # "websocket"
```

`rt`, `ws`, `cmd`, `res` están aceptadas como nombres de variable locales por brevedad.

### Constantes

`UPPER_SNAKE`, en el módulo donde se usan:

```python
MAX_FRAME_BYTES = 1024 * 1024
MAX_ARCHIVOS = 50_000
INVITE_TTL_DAYS = 7
```

Subrayados para separar miles (`50_000` > `50000`).

### Identificadores del sistema (tipos de mensaje, planes, etc.)

`snake_case`:

```python
"update", "save", "delete", "claim"
"free", "premium"
"admin", "member"
```

### En Postgres

`snake_case` para tablas/columnas (convención SQL):

```sql
CREATE TABLE team_members (
    team_id TEXT,
    username TEXT,
    rol TEXT
);
```

## Estilo Python

- **`from __future__ import annotations`** en todos los archivos. Permite typing moderno (`dict[str, X]`, `X | None`) sin runtime cost.
- **Type hints siempre que aporten claridad**. No necesitamos 100%, pero sí en firmas públicas y en datos complejos.
- **Dataclasses** para shapes de datos. Usar `frozen=True` cuando son inmutables (Value Objects: `EstadoGit`, `Simbolo`, `Proposal`).
- **`async def` para todo lo del server** (incluso si no hace `await` adentro, marca el contrato).
- **`with` y `async with`** para recursos (locks, transacciones, conexiones).
- **No `__init__.py` con lógica**: solo re-exports.

## Formatting

- **`ruff format`** (similar a black, más rápido).
- **Línea máxima 88 chars** (convención black). 
- **Comillas dobles** por default (`"X"`, no `'X'`). Excepción: strings que contienen `"` usan `'`.
- **f-strings** preferidas sobre `.format()` y `%`.

## Imports

Orden:

```python
from __future__ import annotations

# 1. Stdlib
import asyncio
import logging
from pathlib import Path

# 2. Third-party
from starlette.responses import JSONResponse
from websockets.asyncio.server import ServerConnection

# 3. Local (relativos)
from ..ports import OwnershipStorePort
from .runtime import TeamRuntime
```

`isort` o `ruff --fix` ordena automáticamente.

## Asincronía

- **El server completo es `asyncio`**. Cero `time.sleep` (usar `await asyncio.sleep`).
- **IO bloqueante en hilo** (`asyncio.to_thread`): subprocess git, parser tree-sitter, JSON IO grande.
- **Locks**: `asyncio.Lock` cuando se llama desde async; `threading.Lock` solo en code path 100% sync (raro).
- **No mezclar**: si un método es sync, todo su llamado desde async usa `to_thread` si es lento.

## Errores

- **Funciones puras**: levantar `ValueError`, `TypeError`, `KeyError` según corresponda.
- **Errores del dominio**: subclases específicas (`WorkspaceLleno`, `PropuestaInvalida`, `TeamError`, `ProtocolError`).
- **Handlers del transporte**: traducen excepciones del dominio a mensajes del protocolo (`AuthErrorMessage`, `GitResultMessage(False, ...)`).
- **NUNCA tragar excepciones sin loggear**. Si capturás `Exception`: log + re-raise o log + acción explícita.
- **Defensiva en boundaries**: el dispatch atrapa `ProtocolError` del codec y manda `AuthError`, no rompe la conexión.

## Logs

- **`logging.getLogger(__name__)`** en cada módulo.
- **Niveles**:
  - `ERROR`: algo se rompió y requiere atención del operador.
  - `WARNING`: algo inesperado pero el sistema sigue (LSP no arrancó, path inseguro descartado, rate limit hit).
  - `INFO`: eventos de negocio relevantes (login, commit, plan cambió).
  - `DEBUG`: detalles para diagnosticar (cuántos archivos cargó, qué tier eligió).

- **Formato estándar** (configurado en `__main__.py`): `%(asctime)s %(levelname)s %(message)s`.

- **No leakear secrets** en logs: tokens, passwords, signing secrets. Stripe webhook log dice "evt_..." pero NO el body.

## Tests

Ver [`testing.md`](testing.md) para el detalle. Convenciones:

- Tests sync para funciones puras, async para todo lo demás.
- Fixtures locales en cada `test_*.py`; solo `sync_server` y `db_dummy` son globales (`conftest.py`).
- Naming descriptivo: `test_X_no_aplica_si_Y` mejor que `test_X_negativo`.

## Git workflow

- **Branch `main` directo** (etapa de prototipo). No feature branches.
- **Commits frecuentes**, mensajes descriptivos en español. Convención: `<scope>: <accion>` (no obligatorio):
  - `state[ownership]: agregar purgar_usuario para flujo de admin`
  - `security[B-08]: pinear imágenes Docker base por digest`
  - `arch: refactor hex Fase 1+2 (Ports + adapters JSON)`
- **NO `--no-verify`** salvo emergencia justificada.
- **NO force push a main**.

## Decisiones decretadas (no re-litigar)

Algunas decisiones del usuario que **NO se re-litigan en cada PR**:

1. **Idioma español** en todo.
2. **Cero deps preventivas**: una dep entra cuando un cuello de botella concreto la justifica.
3. **Construcción por capas**: orden estricto (estado → edición → ownership → análisis → git → ...). No agregar features fuera de la capa actual.
4. **Real-pero-mínimo**: estructura y tests desde el primer commit, nada de abstracciones para problemas que no existen.
5. **Resistir feature soup**: una capa increíble > veinte mediocres.
6. **Ownership es founder's call**: no rediseñar el mecanismo sin pedido explícito del usuario.
7. **NO CRDT por defecto**: tesis es prevenir colisión, no fusionar.
8. **NO open source / NO self-host / NO LICENSE**: producto propietario.
9. **NO mocks pesados** en tests: integración real con Mem* adapters.

Ver `CLAUDE.md` raíz del repo para el contexto completo de las decisiones.

## Lecciones generales del proyecto

1. **Documentar el por qué**, no solo el qué. Cada `BACKEND-AUDIT` es una decisión + contexto.
2. **Degradar fuerte y loud**, no silencioso. Un LSP que no arranca DEBE loguear el porqué exacto.
3. **Defender en profundidad**. Cada input no confiable pasa por 3+ validaciones (`path_seguro` en el dispatch + `_destino` en disco + filtrado al cargar).
4. **Atomicidad donde importa**: tmp + replace + fsync; SQL transactions; locks por equipo.
5. **Operacionalidad**: cada decisión técnica considera el operador (logs accionables, env vars claras, healthcheck que importa).
6. **Velocidad>perfección, hasta donde sea seguro**. Pero en seguridad: 0 tolerancia (las defensas se acumulan).

## Cuándo romper una convención

Si encontrás una razón concreta que justifica romper una convención: hacelo, pero **documentalo en el código** (comentario con el por qué) o en este doc.

Convenciones no son dogma. Si una decisión las invalida, decide.
