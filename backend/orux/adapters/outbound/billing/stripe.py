"""`StripeBillingAdapter`: cumple `BillingPort` cerrando la config del producto
y el signing secret del webhook.

Delegado a las funciones puras de `orux.billing` (HMAC verify, parser de
eventos, builders de form-data). Sólo encapsula:

- `webhook_signing_secret`: el `whsec_...` que firma cada webhook.
- `currency`, `unit_amount`, `interval`, `descripcion_producto`: la
  definición del producto del Checkout (sería raro tener varias, pero el
  adapter lo permite si entra otra suscripción).

Si entra otro proveedor (Paddle, LemonSqueezy), se hace otro adapter que
cumpla el mismo Port. El caller (composition root + api/app.py) inyecta
cuál.
"""

from __future__ import annotations

from orux.domain import billing as billing_puro


class StripeBillingAdapter:
    def __init__(
        self,
        webhook_signing_secret: str,
        *,
        currency: str,
        unit_amount: int,
        interval: str,
        descripcion_producto: str,
    ) -> None:
        self._signing_secret = webhook_signing_secret
        self._currency = currency
        self._unit_amount = unit_amount
        self._interval = interval
        self._descripcion_producto = descripcion_producto

    def params_checkout(
        self,
        team_id: str,
        success_url: str,
        cancel_url: str,
        seats: int,
    ) -> dict[str, str]:
        return billing_puro.params_checkout(
            team_id=team_id,
            descripcion_producto=self._descripcion_producto,
            success_url=success_url,
            cancel_url=cancel_url,
            currency=self._currency,
            unit_amount=self._unit_amount,
            interval=self._interval,
            seats=seats,
        )

    def verificar_firma_webhook(
        self,
        payload: bytes,
        cabecera_firma: str,
    ) -> bool:
        return billing_puro.verificar_firma_webhook(
            payload, cabecera_firma, self._signing_secret,
        )

    def parsear_evento(self, payload: bytes) -> dict:
        return billing_puro.evento_de_payload(payload)

    def event_id(self, evento: dict) -> str:
        return billing_puro.event_id_de(evento)

    def cambio_de_plan(self, evento: dict) -> tuple[str, str] | None:
        return billing_puro.cambio_de_plan(evento)

    def suscripcion_de_evento(self, evento: dict) -> str:
        return billing_puro.suscripcion_de_evento(evento)

    def params_actualizar_cantidad(self, seats: int) -> dict[str, str]:
        return billing_puro.params_actualizar_cantidad(seats)

    def item_id_de_suscripcion(self, suscripcion: dict) -> str:
        return billing_puro.item_id_de_suscripcion(suscripcion)
