# Application: use cases

Los use cases viven en `backend/orux/application/`. Cada uno es una función async que recibe estado + Ports + un Command y devuelve un Result. El inbound (WebSocket dispatch o HTTP handlers) traduce el Result a sends del transporte.

Ver [`architecture/application.md`](../architecture/application.md) para el patrón general; este documento es la **referencia exhaustiva** de cada use case.

## Inventario

```
application/
├── use_cases.py         11 use cases del WS dispatch
├── impacto.py           Save (Ctrl+S) + propagar rename
└── http_use_cases.py    9 use cases del panel HTTP + Stripe webhook
```

## WebSocket use cases (`use_cases.py`)

### `update_use_case`

**Trigger**: `UpdateMessage` (cada tecla del dev).

```python
@dataclass
class UpdateCommand:
    path: str
    content: str
    autor_id: str
    autor_nombre: str

@dataclass
class UpdateResult:
    rebotar_a_autor: str | None = None       # rechazo por colisión de línea
    propuesta_para_dueno: tuple[str, Proposal] | None = None
    broadcast_update: tuple[str, str] | None = None  # (path, content)
    broadcast_ownership: dict[str, str] | None = None
```

**Lógica**:

1. Si el path tiene dueño ajeno: crear/reemplazar `Proposal`, persistir, devolver para enviar al dueño. (END)
2. Si sin dueño y la línea está ocupada por otro presente: rebotar al autor con el contenido viejo. (END)
3. Sembrar baseline del checkpoint (capa 19) si es 1ª vez sobre este path.
4. Aplicar `workspace.update(path, content)`.
5. Devolver `broadcast_update`.
6. Si el archivo era nuevo y no tenía dueño: claim automático para el autor + persistir + devolver `broadcast_ownership`.

**Tests**: `test_sync.py::test_update_*`, `test_workspace.py`, `test_robustez.py::test_path_inseguro_*`.

---

### `claim_use_case`

**Trigger**: `ClaimMessage` (click en "tomar este archivo").

```python
@dataclass
class ClaimCommand:
    path: str
    autor_id: str

@dataclass
class ClaimResult:
    broadcast_ownership: dict[str, str]
```

**Lógica**: `ownership.claim(path, autor_id)` (idempotente; no roba si tiene otro dueño) + persistir + devolver snapshot. El broadcast se manda SIEMPRE — el cliente diferencia si cambió por la diff del snapshot.

**Tests**: `test_sync.py::test_claim_*`.

---

### `delete_use_case`

**Trigger**: `DeleteMessage` (botón borrar archivo).

```python
@dataclass
class DeleteCommand:
    path: str
    autor_id: str

@dataclass
class DeleteResult:
    broadcast_delete: str | None = None       # None si no aplicó
    broadcast_ownership: dict[str, str] | None = None  # None si no cambió ownership
```

**Lógica**:

1. Si el path tiene dueño ajeno: no-op (no podés borrar lo que no es tuyo).
2. `workspace.delete(path)`. Si no existía: no-op.
3. Limpia propuestas asociadas (`proposals.drop_path` + `proposals_store.borrar_path`).
4. Limpia baseline de checkpoint (`rt._analizado.pop`).
5. Si había dueño: liberar + persistir + devolver `broadcast_ownership`.
6. Devolver `broadcast_delete = path`.

El inbound difunde delete + (opcional) ownership.

---

### `resolve_use_case`

**Trigger**: `ResolveMessage` (el dueño aprueba o rechaza una propuesta).

```python
@dataclass
class ResolveCommand:
    proposal_id: str
    autor_id: str   # quien resuelve (debe ser dueño actual)
    accept: bool

@dataclass
class ResolveResult:
    aplicado_update: tuple[str, str, str, str] | None = None
    # ^ (path, viejo, nuevo, prop_author_id) — inbound dispara impacto
    nombre_autor_propuesta: str = ""
    devolver_a_autor: tuple[str, str, str] | None = None
    # ^ (author_id, path, contenido_actual) — para rechazo
```

**Lógica**:

1. Si la propuesta no existe O el path no le pertenece a `autor_id` (carrera benigna): no-op.
2. Pop de la propuesta (memoria + persistencia).
3. Si `accept`:
   - Aplicar `workspace.update(path, prop.content)`.
   - Devolver `aplicado_update` + `nombre_autor_propuesta` → inbound dispara impacto.
4. Si rechazar:
   - Devolver `devolver_a_autor` con el contenido actual → el autor de la propuesta ve revert visual.

**Tests**: `test_sync.py::test_resolve_*`.

---

### `admin_assign_use_case` + `admin_assign_many_use_case`

**Trigger**: `AdminAssignMessage` / `AdminAssignManyMessage` (panel admin).

**Compuerta** (HACERLO EN EL INBOUND, no en el use case): `server._es_admin_o_logear(team_id, autor_id, contexto)` — necesita logging contextual con el detalle de la operación.

```python
@dataclass
class AdminAssignCommand:
    path: str
    username: str     # vacío = revocar
    autor_id: str

@dataclass
class AdminAssignManyCommand:
    paths: list[str]
    username: str
    autor_id: str

@dataclass
class AdminAssignResult:
    broadcast_ownership: dict[str, str] | None = None
```

**Lógica `admin_assign`**:

- Si `username`: normalizar; si es miembro del equipo: `ownership.asignar(path, destino)`. (Si no es miembro: no-op.)
- Si vacío: `ownership.liberar(path)`.
- Si aplicó: persistir + devolver snapshot.

**Lógica `admin_assign_many`**: igual pero itera. **Filtra path-a-path** con `path_seguro(p)` — un path inseguro en la lista no debe meter ownership fantasma ni anular el resto del reparto.

**Tests**: `test_admin.py`, `test_admin_audit.py`, `test_sync.py::test_admin_*`.

---

### `create_invite_use_case`

**Trigger**: `CreateInviteMessage` (admin clica "generar invitación").

**Compuerta**: admin del equipo (validada en el inbound).

```python
@dataclass
class CreateInviteCommand:
    autor_id: str

@dataclass
class CreateInviteResult:
    code: str | None = None  # None si carrera benigna (dejó de ser admin, etc.)
```

**Lógica**: `teams.crear_invitacion(team_id, autor_id)`. Captura `TeamError` y devuelve `None` (no es bug; es carrera benigna).

---

### `presence_use_case`

**Trigger**: `PresenceMessage` (el cursor del dev se movió).

```python
@dataclass
class PresenceCommand:
    autor_id: str
    path: str
    line: int

@dataclass
class PresenceResult:
    broadcast_presence: tuple[str, str, str, str, int] | None = None
    # ^ (client_id, name, color, path, line)
```

**Lógica**: `roster.mover(autor_id, path, line)`. Si no cambió la presencia: `None` (no broadcast). Si cambió: devolver el estado para difundir.

---

### `commit_use_case` / `clone_use_case` / `push_use_case`

**Triggers**: `CommitMessage`, `CloneMessage`, `PushMessage`.

Use cases puros: arman el autor, llaman al `GitPort` en `asyncio.to_thread`, mapean el resultado.

**El lock `rt._git_lock` lo agarra el INBOUND**, no el use case — serializa git por equipo sin contaminar la lógica del use case. Para `clone` el inbound también agarra `rt._estado_lock` (orden git→estado, nunca al revés ⇒ sin deadlock).

```python
@dataclass
class CommitCommand:
    mensaje: str
    autor_nombre: str
    autor_email: str

@dataclass
class CommitResult:
    ok: bool
    detalle: str
    git_status_cambio: bool = False  # inbound difunde git status si True
```

```python
@dataclass
class CloneCommand:
    url: str
    usuario: str
    token: str
    autor_id: str

@dataclass
class CloneResult:
    ok: bool
    detalle: str
    reiniciar_equipo: bool = False  # inbound llama _reiniciar_para_todos
```

```python
@dataclass
class PushCommand:
    url: str
    usuario: str
    token: str
    rama: str   # vacío = rama del equipo (orux/<team_id>) con force-with-lease
    autor_id: str

@dataclass
class PushResult:
    ok: bool
    detalle: str
    pr_url: str = ""
    git_status_cambio: bool = False
```

`push_use_case` decide el modo (rama del equipo vs otra) y llama `push_a_rama` o `push` del adapter. Ver [`flows/git-integration.md`](../flows/git-integration.md).

## Save y propagar rename (`impacto.py`)

### `calcular_impacto_save`

**Trigger**: `_h_save` en el dispatch tras detectar (o no) rename.

```python
async def calcular_impacto_save(
    rt: TeamRuntime,
    teams: TeamStorePort,
    path, viejo, nuevo, autor_id, autor_nombre,
    *,
    rename: Rename | None = None,
) -> ImpactoEfectos:
    ...

@dataclass
class ImpactoEfectos:
    mensajes_directos: list[tuple[str, ImpactMessage]]
    mensajes_transitivos: list[tuple[str, ImpactMessage]]
```

**Lógica**:

1. Lee `plan` del equipo, `cap_langs`.
2. Hilo: obtiene sesión LSP (cap-aware), llama `impacto + motivos + analizador_efectivo`.
3. Si `rename` viene y el plan no aplica codemod (free): reemplaza el motivo de ese símbolo por `texto_sugerencia(rename)`.
4. Reagrupa `símbolo → archivos` ↦ `archivo → símbolos`.
5. Para cada archivo afectado con dueño: arma `ImpactMessage` y lo agrega a `mensajes_directos`.
6. Si plan premium (`impacto == "transitivo"`): otra `to_thread` para la onda transitiva; descarta hops terminales y archivos que el directo ya cubrió; arma `ImpactMessage` con `cadena` y los agrega a `mensajes_transitivos`.

El inbound (`server/impacto.py`) hace `_enviar_a(dueño, encode(msg))` para cada uno.

**Tests**: `test_analysis.py`, `test_transitive.py`, `test_lsp.py`.

---

### `calcular_propagar_rename`

**Trigger**: `_h_save` cuando detecta rename Y el plan permite codemod (premium, capa 26).

```python
async def calcular_propagar_rename(
    rt: TeamRuntime,
    teams: TeamStorePort,
    proposals_store: ProposalsStorePort | None,
    path, viejo, nuevo, ren: Rename, autor_id, autor_nombre,
) -> PropagarRenameEfectos:
    ...

@dataclass
class PropagarRenameEfectos:
    updates_directos: list[tuple[str, str]]  # (path, content)
    propuestas: list[tuple[str, Proposal]]   # (dueño, prop)
```

**Lógica**:

1. Lee plan, cap_langs. Obtiene afectados del rename usando `impacto`.
2. Para cada archivo afectado donde se usa la clase renombrada:
   - `aplicar_rename(contenido, viejo, nuevo)` → propuesto.
   - Si propuesto == contenido (texto no aparece): skip.
   - Si sin dueño O propio: aplicar update directo (mutación en workspace, avanza baseline).
   - Si dueño ajeno: crear propuesta con etiqueta `"OruxBot · rename viejo→nuevo"` + persistir.

El inbound difunde `UpdateMessage` para directos y `ProposalMessage` al dueño para ajenos. El cliente VE la misma ventana aprobar/rechazar de capa 4 (sin UI nueva).

**Tests**: `test_rename.py`.

## HTTP use cases (`http_use_cases.py`)

Para el panel del operador (proceso `api`, Starlette en puerto 8800).

| Use case | Para qué |
|---|---|
| `login_operador(users, admin_user, secret, username, password, *, ttl_seg=8h)` | Login del operador. Verifica que sea el operador designado + password vía PBKDF2. Devuelve token HMAC de sesión. None si falla. |
| `operador_de_token(token, admin_user, secret) -> str \| None` | Valida el Bearer del panel. Puro/sync. |
| `listar_usuarios(users) -> list[str]` | CRUD trivial sobre el store. |
| `listar_teams(teams) -> list[dict]` | Idem. Incluye plan + #miembros. |
| `detalle_team(teams, team_id) -> dict \| None` | Equipo + miembros. |
| `borrar_team(teams, team_id) -> bool` | CASCADE en FK barre todo lo asociado. |
| `borrar_usuario(users, username, *, admin_user) -> bool` | Levanta `ValueError` si target es el operador o tiene FK pendientes (creador de equipo / ownership). |
| `cambiar_plan(teams, team_id, plan) -> dict \| None` | Setea plan manual. Valida contra `PLANES`. |
| `aplicar_evento_stripe(teams, evento, webhooks=None) -> dict \| None` | Aplica evento webhook (alta/baja). Idempotente por `event_id` si `webhooks` está. |

`api/service.py` (legacy) re-exporta de este módulo.

## Patrón compartido

**Compuertas en el inbound, lógica en el use case**: la autorización (admin del equipo, operador, …) se valida en el inbound porque necesita logging contextual o headers HTTP específicos. El use case asume que la autorización pasó y solo orquesta.

**Mutaciones del estado en el use case**: el use case mutate `rt.workspace`, `rt.ownership`, `rt.proposals` directamente. NO devuelve "comandos a aplicar" — devuelve los efectos a publicar.

**Persistencia en el use case**: tras mutar, el use case hace `await store.guardar(...)`. No deja para el inbound. Esto evita olvidos.

**Locks en el inbound**: el lock `rt._estado_lock` lo abraza el `_aplicar` del inbound (antes de llamar a `dispatch`). Los handlers NO re-toman el lock. Los locks específicos (`rt._git_lock`) también los toma el inbound porque sabe la coreografía.
