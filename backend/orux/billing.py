"""Integración con Stripe — la lógica PURA del cobro.

Orux ya tiene un modelo freemium (`plans.py`): un equipo es `free` o
`premium`, y `teams.set_plan(...)` es el enganche "fuera de banda" que
sube o baja el plan. Hasta ahora ese enganche lo accionaba a mano el
operador desde el panel `/admin`. Esta capa lo AUTOMATIZA con Stripe: el
equipo paga una suscripción y su plan salta a `premium` solo; si la
suscripción se cancela, vuelve a `free`.

Por qué este módulo es PURO (sin red): igual que `identity/oauth.py`
separó la lógica testeable de la cáscara HTTP, acá vive todo lo que se
puede probar sin internet — armar el cuerpo del Checkout, verificar la
firma del webhook (HMAC) e interpretar el evento. La única llamada de red
real (crear la sesión de Checkout contra la API de Stripe) vive en
`api/app.py` y se ejercita en el VPS. Mismo patrón que pyright/asyncpg:
la I/O verificable solo en deploy se aísla en la cáscara.

Por qué SIN el SDK oficial `stripe`: la regla de dependencias del
proyecto dice que una dep entra cuando un usuario real choca con un
cuello de botella concreto. Acá no hay tal cuello — Stripe son dos
operaciones (crear una sesión de Checkout, verificar un webhook) y las
dos son stdlib: `urllib` para el POST, `hmac`/`hashlib` para la firma.
orux ya habla con la API de GitHub así (`identity/oauth.py`). El SDK es
cómodo pero es superficie y peso que no hace falta para esto.

El cobro elegido (decisión del usuario): SUSCRIPCIÓN mensual. El equipo
es premium mientras la suscripción viva — es el modelo natural del tier
free/premium ("creciste, pagás"). Un pago único sería una variante de
`params_checkout` (`mode=payment`, sin `recurring`); no se hizo porque no
genera ingreso recurrente.
"""

from __future__ import annotations

import hmac
import json
import time
from hashlib import sha256

# Endpoint REST de Stripe para crear una sesión de Checkout. Usamos
# Checkout HOSTEADO: Stripe sirve la página de pago; nosotros solo
# generamos la sesión y redirigimos el navegador a `session.url`. Los
# datos de tarjeta NUNCA pasan por nuestro server — es la forma más
# simple y segura de integrar pagos (cero PCI scope propio).
URL_CHECKOUT = "https://api.stripe.com/v1/checkout/sessions"


def params_checkout(
    team_id: str,
    descripcion_producto: str,
    success_url: str,
    cancel_url: str,
    *,
    currency: str,
    unit_amount: int,
    interval: str,
) -> dict[str, str]:
    """Construye el cuerpo (form-urlencoded) para crear una sesión de
    Checkout de SUSCRIPCIÓN. Puro: el caller hace el `urlencode` + POST.

    El precio se define INLINE (`price_data`), no como un objeto Price del
    dashboard de Stripe: así no hay que crear nada en el dashboard para
    probar. `unit_amount` va en la unidad mínima de la moneda (centavos):
    1000 = 10.00 MXN. El precio "real" se pone después subiendo la
    variable de entorno del monto.

    Las claves anidadas estilo `line_items[0][price_data][...]` son el
    formato EXACTO que la API REST de Stripe espera como form encoding;
    `urllib.parse.urlencode` las manda tal cual.

    `metadata[team_id]` y `subscription_data[metadata][team_id]`: el
    webhook necesita saber QUÉ equipo pagó. Lo guardamos en la metadata de
    la sesión Y de la suscripción — así el evento de alta
    (`checkout.session.completed`) y el de baja
    (`customer.subscription.deleted`) traen el `team_id` por igual.
    """
    return {
        "mode": "subscription",
        "success_url": success_url,
        "cancel_url": cancel_url,
        # `client_reference_id` es el campo "oficial" de Stripe para atar
        # una sesión a algo nuestro; aparece en el dashboard y es un
        # segundo lugar de donde leer el team_id en el webhook.
        "client_reference_id": team_id,
        "metadata[team_id]": team_id,
        "subscription_data[metadata][team_id]": team_id,
        "line_items[0][quantity]": "1",
        "line_items[0][price_data][currency]": currency,
        "line_items[0][price_data][unit_amount]": str(int(unit_amount)),
        "line_items[0][price_data][recurring][interval]": interval,
        "line_items[0][price_data][product_data][name]": descripcion_producto,
    }


def _firmas_de_cabecera(cabecera: str) -> tuple[str, list[str]]:
    """Parsea la cabecera `Stripe-Signature`. Formato:
    `t=1700000000,v1=abc...,v1=def...`. Devuelve `(timestamp, [firmas v1])`;
    `("", [])` si la cabecera no tiene lo que esperamos."""
    t = ""
    v1: list[str] = []
    for parte in cabecera.split(","):
        clave, sep, valor = parte.strip().partition("=")
        if not sep:
            continue
        if clave == "t":
            t = valor
        elif clave == "v1":
            v1.append(valor)
    return t, v1


def verificar_firma_webhook(
    payload: bytes,
    cabecera_firma: str,
    secret: str,
    *,
    tolerancia_seg: int = 300,
    ahora: float | None = None,
) -> bool:
    """¿Este webhook lo mandó Stripe de verdad y nadie lo manipuló?

    Stripe firma cada webhook con HMAC-SHA256 sobre `"{t}.{payload}"`
    usando el "signing secret" del endpoint (`whsec_...`). Acá:
    1. parseamos `t` y las firmas `v1` de la cabecera,
    2. recomputamos el HMAC sobre el cuerpo CRUDO y comparamos timing-safe,
    3. chequeamos que `t` sea reciente (anti-replay: un webhook viejo
       interceptado no se puede reusar pasada la ventana de tolerancia).

    Sin esto, cualquiera que conozca la URL del webhook podría volver
    premium a un equipo gratis con un simple POST. La firma es la ÚNICA
    autenticación del webhook — Stripe no manda un Bearer.

    Importante: `payload` debe ser el cuerpo EXACTO recibido (bytes sin
    re-serializar); volver a parsear y serializar el JSON cambiaría los
    bytes y rompería la firma.
    """
    if not secret or not cabecera_firma:
        return False
    t, firmas = _firmas_de_cabecera(cabecera_firma)
    if not t or not firmas:
        return False
    try:
        ts = int(t)
    except ValueError:
        return False
    actual = time.time() if ahora is None else ahora
    if abs(actual - ts) > tolerancia_seg:
        return False
    firmado = t.encode("utf-8") + b"." + payload
    esperada = hmac.new(secret.encode("utf-8"), firmado, sha256).hexdigest()
    # `compare_digest` contra cada `v1`: timing-safe. Aceptamos si alguna
    # coincide — Stripe puede mandar varias firmas durante una rotación
    # del signing secret.
    return any(hmac.compare_digest(esperada, f) for f in firmas)


def evento_de_payload(payload: bytes) -> dict:
    """Parsea el cuerpo del webhook a dict. Llamar SOLO después de
    `verificar_firma_webhook` (un payload sin verificar no es de fiar).
    Levanta `ValueError` si no es JSON o no es un objeto."""
    datos = json.loads(payload)
    if not isinstance(datos, dict):
        raise ValueError("el evento de Stripe debe ser un objeto JSON")
    return datos


def cambio_de_plan(evento: dict) -> tuple[str, str] | None:
    """Traduce un evento de Stripe a `(team_id, plan)`, o `None` si el
    evento no nos interesa.

    Solo dos eventos mueven el plan (alcance mínimo y deliberado):
    - `checkout.session.completed`     -> el equipo pagó  -> `premium`.
    - `customer.subscription.deleted`  -> se canceló      -> `free`.

    Otros eventos de suscripción (pago fallido, `past_due`, reintentos)
    NO se manejan a propósito: son una capa de billing más fina (período
    de gracia, dunning) que se construye cuando haya cobro real. Acá lo
    que importa es el flujo alta/baja andando de punta a punta.
    """
    tipo = evento.get("type")
    obj = (evento.get("data") or {}).get("object") or {}
    if not isinstance(obj, dict):
        return None
    meta = obj.get("metadata") or {}
    team_id = ""
    if isinstance(meta, dict):
        team_id = meta.get("team_id") or ""
    if not team_id:
        # La sesión de Checkout también lo trae en `client_reference_id`.
        team_id = obj.get("client_reference_id") or ""
    if not isinstance(team_id, str) or not team_id:
        return None
    if tipo == "checkout.session.completed":
        return (team_id, "premium")
    if tipo == "customer.subscription.deleted":
        return (team_id, "free")
    return None
