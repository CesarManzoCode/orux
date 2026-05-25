# Adapter: Stripe (billing)

`backend/orux/adapters/outbound/billing/stripe.py` implementa `BillingPort`. Es delgado: cierra config externa (signing secret + parámetros del producto) y delega a las funciones puras de `domain/billing.py`.

La llamada real HTTP a Stripe vive en `backend/orux/stripe_client.py` (cliente HTTP urllib) y la invocan dos lugares:

- `adapters/inbound/http/app.py:_crear_sesion_checkout` (POST a `/v1/checkout/sessions` cuando el dev clica "upgrade").
- `adapters/inbound/websocket/seats.py:disparar_ajuste` (POST a `/v1/subscription_items/{id}` cuando entra un miembro nuevo).

## El adapter

```python
class StripeBillingAdapter:
    def __init__(
        self,
        webhook_signing_secret: str,
        *,
        currency: str,
        unit_amount: int,
        interval: str,
        descripcion_producto: str,
    ): ...
```

Cierra:

- **`webhook_signing_secret`**: el `whsec_...` que firma cada webhook (env `STRIPE_WEBHOOK_SECRET`).
- **`currency`**: ISO 4217 (`"MXN"`, `"USD"`, …).
- **`unit_amount`**: precio en la unidad mínima de la moneda (centavos). `20000` = 200.00 MXN.
- **`interval`**: `"month"` o `"year"`.
- **`descripcion_producto`**: lo que el usuario ve en el Checkout (`"Orux Premium"`).

Si entra otro proveedor (Paddle, LemonSqueezy), se hace otro adapter que cumpla `BillingPort`. El composition root elige cuál cablear.

## Métodos del Port

Cada uno delega a `domain/billing.py`:

```python
def params_checkout(self, team_id, success_url, cancel_url, seats) -> dict:
    return billing_puro.params_checkout(
        team_id=team_id,
        descripcion_producto=self._descripcion_producto,
        success_url=success_url, cancel_url=cancel_url,
        currency=self._currency,
        unit_amount=self._unit_amount,
        interval=self._interval,
        seats=seats,
    )

def verificar_firma_webhook(self, payload: bytes, cabecera_firma: str) -> bool:
    return billing_puro.verificar_firma_webhook(
        payload, cabecera_firma, self._signing_secret,
    )

# ... resto igual de delgado
```

## Cliente HTTP de Stripe (`orux/stripe_client.py`)

**No es parte del adapter del Port**: el adapter es lógica pura (verificar/parsear/buildear). El cliente HTTP es **el efecto** que invoca el inbound.

```python
async def crear_sesion_checkout(secret_key, params) -> dict:
    """POST a https://api.stripe.com/v1/checkout/sessions.
    Devuelve la sesión completa (incluye 'url' a redirigir el navegador).
    """

async def get_suscripcion(secret_key, sub_id) -> dict:
    """GET /v1/subscriptions/{id}. Para sacar el item_id."""

async def actualizar_cantidad(secret_key, item_id, params) -> dict:
    """POST /v1/subscription_items/{id}. Ajuste de asientos."""
```

Usa `urllib.request` + auth con `secret_key:` en Authorization Basic. NO usa el SDK oficial `stripe` (regla de dependencias del proyecto).

## Cobro por asiento (capa 31)

Flujo completo:

### Alta (Checkout)

1. Dev clica "upgrade a Premium" → POST a `https://orux.space/api/v1/billing/checkout?team_id=X`.
2. `_billing_checkout` handler en HTTP:
   - Verifica auth (gate).
   - `seats = await teams.contar_miembros(team_id)`.
   - `params = adapter.params_checkout(team_id, success_url, cancel_url, seats)`.
   - `session = await crear_sesion_checkout(SECRET_KEY, params)`.
   - Devuelve `{url: session.url}`.
3. Cliente redirige el navegador a `session.url` (página de Stripe).
4. Dev paga en la página de Stripe (datos de tarjeta NUNCA pasan por nuestro server).
5. Stripe redirige a `success_url` con `?session_id=...`.

### Webhook (alta procesada)

1. Stripe envía `checkout.session.completed` a `https://orux.space/api/v1/billing/webhook`.
2. `_billing_webhook` handler:
   - Lee body crudo (bytes).
   - `adapter.verificar_firma_webhook(payload, header)` — anti-MITM/forgery.
   - `evento = adapter.parsear_evento(payload)`.
   - `event_id = adapter.event_id(evento)` — idempotencia.
   - `await aplicar_evento_stripe(teams, evento, webhooks=webhooks_store)` — use case.
3. `aplicar_evento_stripe`:
   - `cambio = adapter.cambio_de_plan(evento)` → `(team_id, "premium")`.
   - `await webhooks.marcar(event_id)` — si ya estaba: skip silencioso.
   - `sub_id = adapter.suscripcion_de_evento(evento)` → `sub_...`.
   - `await teams.actualizar_suscripcion(team_id, "premium", sub_id)`.

### Baja (Suscripción cancelada)

Mismo flujo del webhook con evento `customer.subscription.deleted`:

- `cambio` → `(team_id, "free")`.
- `sub_id` → `""` (limpia el id porque la suscripción ya no existe).
- `await teams.actualizar_suscripcion(team_id, "free", "")`.

### Ajuste de asientos (entra/sale miembro de equipo premium)

Disparado por `seats.disparar_ajuste(team_id)` cuando alguien redime una invitación:

1. Lee `sub_id = await teams.suscripcion(team_id)`. Si `""`: omitir.
2. `seats = await teams.contar_miembros(team_id)`.
3. `sub = await get_suscripcion(STRIPE_SECRET_KEY, sub_id)`.
4. `item_id = adapter.item_id_de_suscripcion(sub)` → `si_...`.
5. `params = adapter.params_actualizar_cantidad(seats)` → `{quantity: "3", proration_behavior: "create_prorations"}`.
6. `await actualizar_cantidad(STRIPE_SECRET_KEY, item_id, params)`.

Stripe prorratea automáticamente. Si la llamada falla: log warning, NO bloquea al usuario (el miembro entra igual; la suscripción está temporalmente desincronizada y se ajustará al siguiente miembro o en una purga manual).

Lock `_asientos_locks[team_id]` por equipo: dos miembros casi simultáneos no pisan el conteo.

## Idempotencia de webhooks

Stripe garantiza ENTREGA, no orden ni unicidad. Sin esto:

- Webhook reentregado por timeout aplica el cambio dos veces (con `actualizar_suscripcion` que fija valores no rompe en práctica, pero loguea ruido).
- Peor: `customer.subscription.deleted` llegando DESPUÉS de un evento más nuevo por demora de red → equipo queda `free` aunque siga pagando.

**Resolución**:

- `PgWebhooksStore.marcar(event_id) -> bool` insertable con `ON CONFLICT DO NOTHING RETURNING`. Atómico: la decisión "primera o replay" no tiene carrera entre dos workers procesando el mismo webhook.
- `aplicar_evento_stripe` chequea ANTES de tocar el plan: si replay, return None silencioso.

Si el evento no trae `id` (improbable con webhooks reales), se cae al comportamiento legacy: aplicar igual, confiando en que `actualizar_suscripcion` es fijar-valores. Mejor eso que ignorar silencioso.

## Purga de eventos viejos

Stripe ya no reentrega tras ~30 días. `_purgar_webhooks_periodico` corre cada 24h en el lifespan de la app HTTP:

```python
async def _purgar_webhooks_periodico(webhooks):
    while True:
        await asyncio.sleep(24 * 3600)
        try:
            n = await webhooks.purgar()
            logger.info("purgados %d webhook events viejos", n)
        except Exception as e:
            logger.warning("purga de webhooks falló: %r", e)
```

`webhooks.purgar()` borra eventos con `processed_at < now() - interval '30 days'`. Evita que la tabla crezca sin techo (después de un año son ~365 eventos por mes activo = manejable, pero la purga es trivial).

## Modo dev sin billing

Si `STRIPE_SECRET_KEY` no está seteado:

- El proceso HTTP responde 503 en `/api/v1/billing/*` (chequeado con `_billing_ok()`).
- `seats.disparar_ajuste` skipea silencioso.
- Composition root NO cablea `StripeBillingAdapter` (el `BillingPort` queda sin implementación; el inbound HTTP lo crea on-demand cuando recibe un webhook).

Por defecto cerrado. El billing es opt-in operativo.

## Tests

`backend/tests/test_billing.py` cubre todas las funciones puras (`verificar_firma_webhook`, `cambio_de_plan`, `evento_de_payload`, `params_checkout`, `params_actualizar_cantidad`). Sin red, sin Stripe sandbox — todo es vectores de bytes y dicts conocidos.

El adapter `StripeBillingAdapter` se verifica estructuralmente en `test_ports_contract.py` con `isinstance(adapter, BillingPort)`.

La validación end-to-end real (Checkout → webhook → plan cambia) se hace en el VPS con Stripe Test Mode. Ver [`flows/billing.md`](../flows/billing.md) para el detalle operativo.
