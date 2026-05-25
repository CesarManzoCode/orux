# Application layer (use cases)

El application layer vive en `backend/orux/application/`. Es donde **orquesta** la lógica: mutar el dominio + llamar a Ports para persistir + devolver los efectos para que el inbound los publique.

```
application/
├── use_cases.py        11 use cases del WS dispatch
├── impacto.py          Save + propagar rename (los más complejos)
└── http_use_cases.py   9 use cases del panel admin HTTP + Stripe webhook
```

## La regla central

Un use case NO sabe que existe WebSocket. Recibe estado + Ports + Command y devuelve un Result. El inbound (dispatch del WS o handlers HTTP) es quien traduce el Result a sends.

Esto significa que **si mañana el transporte cambia (WS → SSE, REST → gRPC), los use cases no se tocan**.

## Patrón Command/Result

Cada use case tiene:

- Un **Command** dataclass con los datos de entrada.
- Un **Result** dataclass con los efectos a publicar (campos opcionales que el inbound revisa).
- Una **función async** que recibe `rt: TeamRuntime`, los Ports inyectados, y el Command; devuelve el Result.

Ejemplo (`claim_use_case`):

```python
@dataclass
class ClaimCommand:
    path: str
    autor_id: str

@dataclass
class ClaimResult:
    broadcast_ownership: dict[str, str]

async def claim_use_case(
    rt: "TeamRuntime",
    ownership_store: OwnershipStorePort | None,
    cmd: ClaimCommand,
) -> ClaimResult:
    rt.ownership.claim(cmd.path, cmd.autor_id)
    if ownership_store is not None:
        await ownership_store.guardar(rt.team_id, rt.ownership.snapshot())
    return ClaimResult(broadcast_ownership=rt.ownership.snapshot())
```

El inbound:

```python
async def _h_claim(server, rt, websocket, yo, team_id, message):
    res = await claim_use_case(
        rt,
        server._ownership_store,
        ClaimCommand(path=message.path, autor_id=yo.client_id),
    )
    await server._broadcast_todos(
        rt, encode(OwnershipMessage(owners=res.broadcast_ownership)),
    )
```

## Por qué Result con campos opcionales (no Domain Events)

Pensamos varios patrones:

1. **Lista de Domain Events** (`list[DomainEvent]`): muy puro pero requiere una jerarquía de clases por evento.
2. **Result con campos opcionales**: el use case llena los campos que correspondan; el inbound revisa cada uno con `if res.X is not None`.
3. **Mutaciones implícitas con observers**: descartado por opaco.

Elegimos (2) porque es declarativo: el shape del Result dice qué puede pasar tras este use case, y el inbound es un translator obvio. Para 11 use cases simples es la opción más legible.

## Los 11 use cases del WS (`use_cases.py`)

### Update
**Command**: `{path, content, autor_id, autor_nombre}`.
**Lógica**: si dueño ajeno → propuesta. Si sin dueño y línea ocupada por otro presente → rebote. Resto → aplicar + difundir + claim si es nuevo.
**Result**: `{rebotar_a_autor?, propuesta_para_dueno?, broadcast_update?, broadcast_ownership?}`.

### Claim
**Command**: `{path, autor_id}`. **Result**: ownership snapshot. Idempotente.

### Delete
**Command**: `{path, autor_id}`. Solo el dueño borra (o cualquiera si no tiene dueño). Borra propuestas asociadas, libera ownership.
**Result**: `{broadcast_delete?, broadcast_ownership?}`.

### Resolve (aprobar/rechazar propuesta)
**Command**: `{proposal_id, autor_id, accept}`. Solo el dueño actual resuelve. Si aprueba: aplica el update + dispara impacto. Si rechaza: devuelve al autor el contenido actual.
**Result**: `{aplicado_update?, devolver_a_autor?}`.

### AdminAssign + AdminAssignMany
Admin del equipo reparte ownership. La compuerta de admin se valida en el inbound (necesita logging contextual); el use case asume que ya pasó.

### CreateInvite
Admin genera código de un solo uso. **Result**: `{code?}` (None si carrera benigna).

### Presence
Mueve al usuario en el roster. **Result**: `{broadcast_presence?}` (None si no cambió).

### Commit / Clone / Push
Operaciones git (cada una abraza `rt._git_lock` para serializar git del equipo). Use cases puros: arman el autor, llaman al `GitPort` en `asyncio.to_thread`, mapean el resultado.
**Result**: `{ok, detalle, ...}` + flags (git_status_cambio, reiniciar_equipo, pr_url).

## Impacto y rename (`impacto.py`)

Los más complejos. Salen del `_h_save` del dispatch porque:

- El save dispara el análisis semántico (Ctrl+S, capa 19).
- En premium, si hay rename detectado, se propaga como propuestas (capa 26).
- En premium, hay onda transitiva por interfaz contaminada (capa 24).

`calcular_impacto_save(rt, teams, path, viejo, nuevo, autor_id, autor_nombre, *, rename=None) -> ImpactoEfectos`:

- Llama al motor de análisis en un hilo (`asyncio.to_thread`).
- Devuelve `ImpactoEfectos { mensajes_directos: list[(dueño, ImpactMessage)], mensajes_transitivos: list[(dueño, ImpactMessage)] }`.

`calcular_propagar_rename(rt, teams, proposals_store, path, viejo, nuevo, ren, autor_id, autor_nombre) -> PropagarRenameEfectos`:

- Para cada archivo afectado: si sin dueño o propio → update directo (mutación en workspace). Si ajeno → propuesta tentativa.
- Devuelve `PropagarRenameEfectos { updates_directos: list[(path, content)], propuestas: list[(dueño, Proposal)] }`.

`server/impacto.py` (translator del inbound) los llama y traduce los efectos a `_enviar_a` y `_broadcast_todos`.

## Use cases HTTP (`http_use_cases.py`)

Para el panel del operador (Starlette en puerto 8800). Son async sobre los stores duck-typed:

- `login_operador(users, admin_user, secret, username, password, *, ttl_seg)`: verifica que sea el operador designado + password vía PBKDF2, emite token HMAC de sesión.
- `operador_de_token(token, admin_user, secret)`: valida el bearer del panel.
- `listar_usuarios`, `listar_teams`, `detalle_team`, `borrar_team`, `borrar_usuario`, `cambiar_plan`: CRUD trivial sobre los stores.
- `aplicar_evento_stripe(teams, evento, webhooks=None)`: aplica un cambio de plan Stripe ya verificado al equipo. Idempotente por `event_id` si `webhooks` está presente.

`api/service.py` (legacy) queda como re-export de este módulo para no romper imports externos.

## Lo que falta para 100% puro

Hoy todavía hay 2-3 handlers HTTP con lógica inline en `adapters/inbound/http/app.py`:

- `_gh_callback`: OAuth callback. Mezcla decode + `_state_consumir` + `_intercambiar` + `identidad_github` + `crear_token` + `_volver`. Para 100% puro, extraer un `oauth_callback_use_case`.
- `_billing_checkout`: crea sesión de Checkout en Stripe. Mezcla auth + POST a Stripe + redirect. Extraer un `crear_checkout_use_case`.
- `_billing_webhook`: ya usa `aplicar_evento_stripe` (que sí es use case); el wrapper HTTP es mínimo.

Ver [`architecture/overview.md`](overview.md) — "Lo que falta para purista 100%" para el detalle.
