"""`BillingPort`: contrato del proveedor de pagos.

Hoy: Stripe. Si en el futuro entra Paddle / LemonSqueezy, sería otro adapter
que cumpla este Port y el composition root elige cuál cablear.

# Diseño: el adapter encapsula el signing secret y delega a `billing.py`

Las funciones de `billing.py` son PURAS (parser/serializer/HMAC verify): no
hacen I/O. El adapter cierra el `webhook_signing_secret` y la `descripcion_
producto`/`currency`/`unit_amount` (config del producto) — el dominio sólo
ve métodos de alto nivel sin tocar Stripe directamente.

La parte que SÍ hace I/O (POST a Stripe para crear el Checkout, ajustar
asientos) sigue viviendo en la cáscara HTTP por ahora; en Fase D se
mueve al adapter como cliente HTTP. El Port ya está listo para eso (los
métodos podrán pasar de "construir params" a "hacer la llamada" sin que
el caller cambie).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class BillingPort(Protocol):
    """Operaciones del proveedor de pagos. Implementación canónica:
    `adapters.billing.stripe.StripeBillingAdapter`."""

    def params_checkout(
        self,
        team_id: str,
        success_url: str,
        cancel_url: str,
        seats: int,
    ) -> dict[str, str]:
        """Body form-urlencoded para crear una sesión de Checkout."""
        ...

    def verificar_firma_webhook(
        self,
        payload: bytes,
        cabecera_firma: str,
    ) -> bool:
        """¿La firma del webhook es legítima y reciente?"""
        ...

    def parsear_evento(self, payload: bytes) -> dict:
        """Cuerpo verificado → dict del evento. Levanta ValueError si no
        es JSON o no es un objeto."""
        ...

    def event_id(self, evento: dict) -> str:
        """`evt_...` del evento (para idempotencia vía WebhooksStorePort)."""
        ...

    def cambio_de_plan(self, evento: dict) -> tuple[str, str] | None:
        """`(team_id, plan)` para los eventos que cambian plan; None si no."""
        ...

    def suscripcion_de_evento(self, evento: dict) -> str:
        """`sub_...` de la suscripción asociada al evento."""
        ...

    def params_actualizar_cantidad(self, seats: int) -> dict[str, str]:
        """Body para ajustar cantidad de asientos de un subscription item."""
        ...

    def item_id_de_suscripcion(self, suscripcion: dict) -> str:
        """`si_...` del primer item de una suscripción de Stripe."""
        ...
