# Flow: Billing (Stripe)

Capa 31. Cobro por **asiento** (un asiento por miembro), como ChatGPT Business. La factura mensual es `unit_amount × miembros_del_equipo`. Cuando entra alguien, la cantidad de la suscripción sube y Stripe prorratea.

## Estado actual (2026-05-24)

Backend de billing **completo y testeado**. Lo que falta operativamente:

- Configurar `STRIPE_SECRET_KEY` y `STRIPE_WEBHOOK_SECRET` en el VPS (env vars para `api` Y `orux` contenedores).
- Configurar endpoint de webhook en el dashboard de Stripe → `https://orux.space/api/v1/billing/webhook`.
- Validación end-to-end real con Stripe Test Mode.

## Flow 1: Upgrade (Checkout)

```
Líder del equipo            Server HTTP                          Stripe                    Server WS / Cliente
────────────────            ───────────                          ──────                    ───────────────────
  │                              │                                  │                          │
  │── clica "Premium" ──────────→│                                  │                          │
  │   POST /api/v1/billing/checkout?team_id=abc12345                │                          │
  │                              │ _gate(req) ✓                     │                          │
  │                              │ _billing_ok() ✓                  │                          │
  │                              │                                  │                          │
  │                              │ seats = await teams.contar_miembros(team_id)               │
  │                              │ → 3                              │                          │
  │                              │                                  │                          │
  │                              │ params = adapter.params_checkout(│                          │
  │                              │   team_id, success_url, cancel_url, seats=3)               │
  │                              │                                  │                          │
  │                              │── POST /v1/checkout/sessions ────→│                          │
  │                              │ (Authorization: Bearer SECRET_KEY)│                         │
  │                              │←──── 200 {url: "https://checkout.stripe.com/c/...", id} ──│
  │                              │                                  │                          │
  │←──── 200 {url} ──────────────│                                  │                          │
  │                              │                                  │                          │
  │── window.location = url ─────────────────────────────────────────│                          │
  │                                                                  │                          │
  │ (paga en la página de Stripe — datos de tarjeta NUNCA pasan      │                          │
  │  por nuestro server, cero PCI scope)                              │                          │
  │                                                                  │                          │
  │←─── 302 → success_url ───────────────────────────────────────────│                          │
  │                                                                                            │
  │ (cliente vuelve a Orux con session_id en query; muestra "¡Premium activo!")               │
```

### Por qué Checkout hosteado

- Stripe sirve la página de pago.
- Cero datos de tarjeta en nuestro server (cero PCI scope).
- La forma más simple y segura de integrar pagos.
- Stripe maneja 3DS, retries, países, currencies, regulaciones.

## Flow 2: Webhook (alta procesada)

```
Stripe                  Server HTTP                       teams           webhooks (PgWebhooks)
──────                  ───────────                       ─────           ─────────────────────
  │                          │                              │                    │
  │ (después del pago)        │                              │                    │
  │── POST /api/v1/billing/webhook ─→                       │                    │
  │   Stripe-Signature: t=...,v1=...│                       │                    │
  │   body: {type: "checkout.session.completed", ...}       │                    │
  │                          │                              │                    │
  │                          │ payload = await req.body() (bytes crudos)         │
  │                          │                              │                    │
  │                          │ adapter.verificar_firma_webhook(payload, hdr) ✓   │
  │                          │   (HMAC-SHA256 timing-safe + anti-replay 5min)    │
  │                          │                              │                    │
  │                          │ evento = adapter.parsear_evento(payload)          │
  │                          │ event_id = adapter.event_id(evento) → "evt_..."   │
  │                          │                              │                    │
  │                          │ aplicar_evento_stripe(teams, evento, webhooks):   │
  │                          │   cambio = adapter.cambio_de_plan(evento)         │
  │                          │   → ("abc12345", "premium")                       │
  │                          │   ─ webhooks.marcar(event_id) ──────────────────→ │
  │                          │   ←── True (primera vez) ──────────────────────── │
  │                          │   sub_id = adapter.suscripcion_de_evento(evento)  │
  │                          │   → "sub_xyz"                                     │
  │                          │   ─ teams.actualizar_suscripcion(             │
  │                          │       abc12345, "premium", "sub_xyz") ──────→│
  │                          │                                                   │
  │←── 200 ──────────────────│                                                   │
```

### Idempotencia

`webhooks.marcar(event_id)` devuelve True solo la primera vez. Si Stripe reentrega el webhook (timeout, dashboard manual), `marcar` devuelve False y `aplicar_evento_stripe` skipea silencioso.

Sin idempotencia, un webhook reentregado aplica el cambio dos veces — con `actualizar_suscripcion` que fija valores no rompe, pero loguea ruido y dispara side-effects extra.

### Status 200 siempre que parseamos

Si devolvemos 400, Stripe reintenta. Para eventos que no nos interesan (otros tipos) o ya procesados (idempotencia), un 200 dice "lo recibí, no me lo mandes de nuevo".

400 SOLO si la firma es inválida o el JSON no parsea (Stripe maliciosamente formado o request real con problema).

## Flow 3: Webhook (baja)

Mismo flujo con evento `customer.subscription.deleted`:

- `cambio_de_plan` → `(team_id, "free")`.
- `suscripcion_de_evento` → `""` (la suscripción ya no existe).
- `teams.actualizar_suscripcion(team_id, "free", "")` — limpia el `stripe_subscription_id`.

## Flow 4: Ajuste de asientos (entra miembro nuevo)

Disparado por `seats.disparar_ajuste(team_id)` cuando alguien redime una invitación en un equipo premium:

```
seats.disparar_ajuste(team_id):
  async with self._asientos_locks[team_id]:
    sub_id = await teams.suscripcion(team_id)
    if not sub_id: return  # equipo free o premium manual sin sub
    
    seats = await teams.contar_miembros(team_id)
    
    sub = await stripe_client.get_suscripcion(SECRET_KEY, sub_id)
    item_id = adapter.item_id_de_suscripcion(sub)  # "si_..."
    
    params = adapter.params_actualizar_cantidad(seats)
    # → {"quantity": "4", "proration_behavior": "create_prorations"}
    
    await stripe_client.actualizar_cantidad(SECRET_KEY, item_id, params)
    logger.info("asientos ajustados: equipo %s → %d", team_id, seats)
```

### Lock por equipo

`self._asientos_locks[team_id]` evita pisar conteos cuando dos miembros entran casi a la vez. Sin el lock:

1. Dos invitaciones se redimen simultáneamente.
2. Ambas tareas leen `contar_miembros` (devuelve 3, antes del INSERT del otro).
3. Ambas POSTean `quantity=4` a Stripe.
4. La suscripción queda en 4 cuando debería estar en 5.

### Proration

`proration_behavior=create_prorations`: Stripe prorratea la diferencia de precio por lo que queda del ciclo y la SUMA a la próxima factura. NO intenta un cobro inmediato (que podría fallar y habría que gestionar). Es la opción robusta para sistema desatendido.

### Cantidad absoluta

`seats` siempre es ABSOLUTO (= miembros actuales del equipo), nunca incremental. Esto significa que reaplicar el mismo ajuste es idempotente y se autocorrige:

- Si una llamada falla a la mitad: el siguiente miembro lo arregla.
- Si dos miembros entran casi juntos: el último ganará (ambos quedan correctos eventualmente).
- Si el server reinicia entre el INSERT y la llamada a Stripe: el siguiente miembro lo corrige.

### Best-effort, no bloqueante

Si la llamada a Stripe falla: loguea warning, **NO bloquea al usuario** (el miembro entra igual; la suscripción está temporalmente desincronizada y se ajustará al siguiente miembro o en una purga manual).

## Flow 5: Cambio manual de plan (operador)

El operador desde el panel admin (`/api/v1/teams/{tid}/plan`):

```
POST /api/v1/teams/abc12345/plan
Authorization: Bearer <admin_token>
Body: {"plan": "premium"}

→ cambiar_plan(teams, "abc12345", "premium")
  → if plan not in PLANES: ValueError → 400
  → if await teams.equipo(tid) is None: return None → 404
  → await teams.set_plan(tid, "premium")
  → return detalle_team(...)

← 200 {id, nombre, plan: "premium", miembros: [...]}
```

`set_plan` es la acción MANUAL del operador. NO crea suscripción Stripe; solo cambia el plan. Útil para:

- Premiar a un equipo manualmente sin pasar por Stripe.
- Compensar un downtime ("te doy 1 mes gratis").
- Pre-launch beta testers.

**Crítico**: equipos con plan premium manual (sin `stripe_subscription_id`) NO disparan ajustes de Stripe. `seats.disparar_ajuste` chequea `if not sub_id: return`.

## Purga de webhooks viejos

`_purgar_webhooks_periodico(webhooks)` corre cada 24h en el lifespan de la app HTTP:

```python
await webhooks.purgar(antes_de_segundos=30 * 24 * 3600)
```

Borra eventos con `processed_at < now() - 30 days`. Stripe ya no reentrega tras ~30 días, así que es seguro purgar. Evita que la tabla crezca sin techo.

## Modo dev sin billing

Si `STRIPE_SECRET_KEY` no está seteado:

- HTTP responde 503 en `/api/v1/billing/*`.
- `seats.disparar_ajuste` skipea silencioso.
- Cero llamadas a Stripe.

Por defecto cerrado. El billing es opt-in operativo.

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| `POST /billing/checkout` → 503 | `STRIPE_SECRET_KEY` no seteado |
| Webhook → 400 "firma inválida" | `STRIPE_WEBHOOK_SECRET` env distinto del configurado en Stripe Dashboard |
| Webhook → 200 pero plan no cambia | Evento de tipo no relevante (sí o sí no lo procesamos) o webhook_id ya procesado |
| Asientos no se ajustan tras un miembro nuevo | Lock contendido o equipo es premium manual (sin sub_id) |
| Tabla `processed_webhooks` crece | Verificar que `_purgar_webhooks_periodico` corre. `docker compose logs api \| grep purga` |

Ver [`domain/billing.md`](../domain/billing.md) y [`adapters/stripe.md`](../adapters/stripe.md).
