# Domain: billing

`backend/orux/domain/billing.py` tiene la lógica PURA de Stripe: HMAC verify, parsers de eventos, builders de form-data. **Sin red.**

La llamada real a la API de Stripe (POST a `/v1/checkout/sessions`, POST a `/v1/subscription_items/{id}`) vive en `orux/stripe_client.py` (cliente HTTP) y se invoca desde `adapters/inbound/http/app.py` (Checkout) y `adapters/inbound/websocket/seats.py` (ajuste de asientos).

Mismo patrón que `identity/oauth.py`: separar lo que se puede probar sin internet de la cáscara HTTP.

## Por qué SIN el SDK oficial `stripe`

Regla de dependencias del proyecto: una dep entra cuando un usuario real choca con un cuello de botella concreto. Stripe son **dos operaciones** (crear Checkout, verificar webhook) y las dos son stdlib (`urllib` para POST, `hmac`/`hashlib` para firma). orux ya habla con GitHub así. El SDK es cómodo pero es superficie y peso que no hace falta.

## Modelo de cobro elegido (decisión decretada con el usuario)

**Suscripción mensual por ASIENTO**. El equipo es premium mientras la suscripción viva; la factura mensual es `unit_amount * miembros_del_equipo`. Cuando entra alguien, la cantidad de la suscripción sube. Mismo modelo que ChatGPT Business.

La cantidad se fija ABSOLUTA (= miembros actuales), no incremental → reaplicarla es idempotente y se autocorrige.

## Endpoints de Stripe usados

```python
URL_CHECKOUT = "https://api.stripe.com/v1/checkout/sessions"
URL_SUSCRIPCIONES = "https://api.stripe.com/v1/subscriptions"
URL_ITEMS = "https://api.stripe.com/v1/subscription_items"
```

Usamos **Checkout hosteado**: Stripe sirve la página de pago; nosotros solo generamos la sesión y redirigimos el navegador a `session.url`. Los datos de tarjeta NUNCA pasan por nuestro server — cero PCI scope propio.

## `params_checkout(...) -> dict[str, str]`

Construye el body form-urlencoded para crear una sesión de Checkout de SUSCRIPCIÓN.

```python
params_checkout(
    team_id="abc12345",
    descripcion_producto="Orux Premium",
    success_url="https://orux.space/billing/ok?session_id={CHECKOUT_SESSION_ID}",
    cancel_url="https://orux.space/billing/cancel",
    currency="MXN",
    unit_amount=20000,   # 200.00 MXN en centavos
    interval="month",
    seats=3,
)
# →
# {
#     "mode": "subscription",
#     "success_url": "...",
#     "cancel_url": "...",
#     "client_reference_id": "abc12345",
#     "metadata[team_id]": "abc12345",
#     "subscription_data[metadata][team_id]": "abc12345",
#     "line_items[0][quantity]": "3",
#     "line_items[0][price_data][currency]": "MXN",
#     "line_items[0][price_data][unit_amount]": "20000",
#     "line_items[0][price_data][recurring][interval]": "month",
#     "line_items[0][price_data][product_data][name]": "Orux Premium",
# }
```

Decisiones:

- **`price_data` inline** (no objeto Price del dashboard): así no hay que crear nada en el dashboard para probar.
- **`metadata[team_id]` en SESIÓN Y en SUSCRIPCIÓN**: el webhook necesita el `team_id`. Lo guardamos en los dos lugares para que tanto `checkout.session.completed` como `customer.subscription.deleted` lo traigan.
- **`client_reference_id`**: campo "oficial" de Stripe — aparece en el dashboard, segundo lugar de donde leerlo en el webhook.
- **`seats=max(1, ...)`**: un equipo siempre tiene al creador.

## `verificar_firma_webhook(payload, cabecera_firma, secret, *, tolerancia_seg=300, ahora?) -> bool`

¿Este webhook lo mandó Stripe de verdad y nadie lo manipuló?

Stripe firma cada webhook con HMAC-SHA256 sobre `"{t}.{payload}"` usando el `whsec_...` del endpoint. Lo que hacemos:

1. Parsea `t` y firmas `v1` del header `Stripe-Signature`.
2. Recomputa HMAC sobre el cuerpo CRUDO (`payload` debe ser bytes sin re-serializar — volver a parsear y serializar cambia los bytes y rompe la firma).
3. Compara timing-safe con `hmac.compare_digest` contra cada firma `v1` (Stripe puede mandar varias durante rotación del signing secret).
4. Chequea `abs(ahora - ts) <= tolerancia_seg` (anti-replay, default 5 min).

Sin esto, cualquiera que conozca la URL del webhook podría volver premium a un equipo con un simple POST. La firma es la ÚNICA autenticación del webhook — Stripe no manda Bearer.

## `evento_de_payload(payload) -> dict`

Parsea el JSON del webhook a dict. Llamar SOLO después de `verificar_firma_webhook`. Levanta `ValueError` si no es JSON o no es un objeto.

## `cambio_de_plan(evento) -> tuple[str, str] | None`

Traduce un evento de Stripe a `(team_id, plan)`, o `None` si el evento no nos interesa.

**Solo dos eventos mueven el plan** (alcance mínimo y deliberado):

- `checkout.session.completed` → el equipo pagó → `premium`.
- `customer.subscription.deleted` → se canceló → `free`.

Otros eventos (pago fallido, `past_due`, reintentos, dunning) NO se manejan a propósito: son una capa de billing más fina que se construye cuando haya cobro real. Acá lo que importa es el flujo alta/baja andando de punta a punta.

## `suscripcion_de_evento(evento) -> str`

Extrae el id `sub_...` del evento:

- `checkout.session.completed`: el objeto es la sesión; la suscripción que creó viene en `.subscription`.
- `customer.subscription.*`: el objeto ES la suscripción; su `.id`.

Lo usa el adapter de seats para guardar QUÉ suscripción es la del equipo (`teams.actualizar_suscripcion`).

## `item_id_de_suscripcion(suscripcion) -> str`

Dado un objeto Subscription completo (lo que devuelve `GET /v1/subscriptions/{id}`), extrae el id `si_...` de su PRIMER subscription item. Ese id es lo que la API de Stripe pide para cambiar la cantidad (`POST /v1/subscription_items/{id}`). La suscripción de un equipo tiene un único item: un solo precio, "Orux Premium".

## `params_actualizar_cantidad(seats) -> dict[str, str]`

Body para `POST /v1/subscription_items/{id}`:

```python
{
    "quantity": "3",
    "proration_behavior": "create_prorations",
}
```

**`proration_behavior=create_prorations`**: Stripe prorratea la diferencia por lo que queda del ciclo y la SUMA a la próxima factura (no intenta un cobro inmediato, que podría fallar y habría que gestionar). Robusto para sistema desatendido.

## `event_id_de(evento) -> str`

Extrae el id `evt_...` del evento (o `""` si no lo trae). Cada evento de Stripe tiene un id único y estable; si Stripe reentrega el webhook (timeout, dashboard manual), el id es el mismo. Es la base para idempotencia vía `WebhooksStorePort`.

## `MemWebhooksStore` (in-memory)

```python
class MemWebhooksStore:
    async def marcar(self, event_id: str) -> bool: ...  # True = primera vez
    async def purgar(self, antes_de_segundos=0) -> int: ...  # no-op
```

Cumple `WebhooksStorePort` para tests y dev. No persiste cross-restart — ese es el caso del `PgWebhooksStore` real (con limpieza periódica vía `_purgar_webhooks_periodico` cada 24h en el lifespan de la app HTTP).

## Estado actual (2026-05-24)

Backend de billing **completo y testeado**. Lo que falta operativamente:

- Configurar `STRIPE_SECRET_KEY` en el VPS (env vars para los contenedores `api` Y `orux`).
- Configurar webhook endpoint en el dashboard de Stripe → apunta a `https://orux.space/api/v1/billing/webhook`.
- Validación end-to-end en producción (probar Checkout, recibir webhook, verificar plan cambia).

Ver `RUNBOOK.md` raíz del repo para los detalles operativos.
