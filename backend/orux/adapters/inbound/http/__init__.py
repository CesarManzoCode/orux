"""Inbound HTTP adapter: panel del operador, OAuth callbacks, webhooks Stripe.

`crear_app(users, teams, webhooks)` arma el Starlette ASGI con todas las
rutas. Llama a use cases de `orux.application` para la lógica.
"""

from .app import crear_app

__all__ = ["crear_app"]
