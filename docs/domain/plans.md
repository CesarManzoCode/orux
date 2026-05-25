# Domain: plans

`backend/orux/domain/plans.py` define los planes del freemium (capa 22): qué permite cada uno, qué límites tienen.

## Decisión decretada (no re-litigar)

**Tiers por escala, no medidor que se agota.** El free es permanente y orux funciona de verdad ahí. La tesis no se "tiera" — se "tiera" alrededor (escala, profundidad). Los únicos límites del free son **de escala/recurso** (se sienten justos: "creciste, pagás"), NUNCA de capacidad (no es "te quitamos lo bueno").

En coordinación continua, un medidor que se agota se lee como bait-and-switch y mata el "que vean el valor total".

## Los planes

```python
PLANES = {"free", "premium"}
PLAN_DEFECTO = "free"
INF = 10**9  # "sin límite". Int gigante en vez de float('inf') por
             # BACKEND-AUDIT-0183 (NaN/float raros con < inf).
```

### `limites(plan) -> dict`

| Límite | free | premium |
|---|---|---|
| `max_devs` | 5 | INF |
| `max_langs` | 2 | INF |
| `max_workspaces` | 1 | INF |
| `impacto` | `"directo"` | `"transitivo"` |
| `rename` | `"manual"` | `"automatico"` |
| `jvm` | `False` | `True` |

### Helpers (cada uno encapsula UNA pregunta)

```python
permite_miembro(plan, miembros_actuales) -> bool
permite_lenguaje(plan, langs_activos) -> bool
permite_workspace(plan, workspaces_actuales) -> bool
permite_jvm(plan) -> bool
permite_rename(plan) -> bool
impacto_modo(plan) -> str  # "directo" o "transitivo"
```

Estos viven acá para que el código no haga `if plan == "free": ...` disperso. Si un plan nuevo entra, mover un número aquí afecta a todos los callers sin tocarlos.

## Quién pregunta qué

| Caller | Pregunta |
|---|---|
| `teams.MemTeamStore.redimir` / `PgTeamStore.redimir` | `permite_miembro(plan, len(m))` antes de consumir el código de invitación |
| `runtime.TeamRuntime.lsp_sesion` | `cap_langs = limites(plan)["max_langs"]` para decidir si arranca LSP de un lenguaje nuevo |
| `application/impacto.calcular_impacto_save` | `limites(plan)["impacto"] != "transitivo"` para early-return tras el directo |
| `application/use_cases._h_save` | `permite_rename(plan)` para decidir si propaga rename premium o solo avisa |

## Quién setea el plan

**Fuera de banda**. El módulo solo *interpreta* el plan; setearlo es decisión externa:

1. **Manual**: el operador desde el panel admin → `cambiar_plan` use case → `teams.set_plan(team_id, plan)`.
2. **Stripe webhook**: `aplicar_evento_stripe` use case mapea `checkout.session.completed → premium` y `customer.subscription.deleted → free` → `teams.actualizar_suscripcion(team_id, plan, sub_id)`.

El plan vive en la columna `teams.plan` (default `'free'`).

## Cobro por asiento (capa 31)

Premium es **suscripción mensual con cantidad = miembros del equipo**. Como ChatGPT Business.

- La factura es `unit_amount * seats` por mes.
- Cuando entra un miembro nuevo a un equipo premium, el server sube la cantidad en Stripe (`actualizar_cantidad`) y Stripe prorratea la diferencia.
- La cantidad se fija ABSOLUTA (= miembros actuales), no incremental → reaplicarla es idempotente.
- Mínimo 1 (un equipo siempre tiene al menos al creador).

Esto NO vive en `plans.py` directamente; el cobro está en `domain/billing.py` y los adapters de billing. `plans.py` solo dice "premium permite INF miembros".

## Por qué no hay límites en bytes/operaciones por mes

Tentativo en la fase de diseño, descartado:

- "Bytes del workspace por mes": opaco para el usuario; no se entiende qué es "demasiado". Y el incentivo perverso de borrar archivos para no pagar es contradictorio con la tesis.
- "Análisis por día": el análisis es lo que define al producto. Capear lo que vendés es bait-and-switch.

Los límites actuales son `max_devs`, `max_langs`, `max_workspaces`, `impacto`, `rename` — todos en términos del valor que el dev percibe.
