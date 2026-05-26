"""Las llamadas de red REALES a la API de Stripe — la cáscara de I/O.

`billing.py` es la lógica PURA del cobro (arma cuerpos, verifica firmas,
interpreta eventos, extrae ids) y se prueba al 100% en el sandbox. Acá
vive lo otro: el `urllib` que de verdad habla con `api.stripe.com`. Igual
que la cáscara HTTP de `api/app.py`, esto se ejercita en el VPS (el
sandbox no tiene internet) — por eso es fino y se apoya en `billing.py`
para todo lo testeable.

Por qué un módulo aparte y no dentro de `api/app.py`: el cobro por asiento
(capa 31) necesita estas llamadas desde DOS procesos.

  - El contenedor `api` crea la sesión de Checkout cuando un admin mejora
    su equipo a premium.
  - El servidor WebSocket (`server/sync.py`) ajusta la cantidad de
    asientos de la suscripción cuando entra un miembro nuevo a un equipo
    premium — ese evento ocurre en el server WS, no en la API.

`api/app.py` importa starlette y el server WS no debe arrastrarlo, así que
la I/O de Stripe compartida vive acá: stdlib pura (`urllib`), sin
starlette ni asyncpg, importable por ambos.

Todas las funciones son BLOQUEANTES (urllib). El caller las corre fuera
del loop de asyncio: `run_in_threadpool` en starlette, `run_in_executor`
en el server WS. Un timeout corto evita que una API de Stripe colgada
cuelgue a un worker.
"""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.parse
import urllib.request

from . import billing

logger = logging.getLogger(__name__)

# Timeout único y corto para toda llamada a Stripe. Una API colgada no
# debe colgar a un worker (ni del contenedor `api` ni del server WS).
_TIMEOUT = 15


def _post(url: str, secret: str, params: dict[str, str]) -> dict:
    """POST form-urlencoded autenticado con la clave secreta de Stripe.
    Devuelve el JSON de respuesta como dict. Levanta si la red falla o
    Stripe responde con un HTTP de error (`HTTPError` < `URLError`).

    El `TimeoutError` se loguea con la URL antes de re-propagar: sin esto,
    un Stripe lento aparece en el caller como "error sin contexto" y es
    imposible distinguir "se cayó la red" de "Stripe respondió 500".
    """
    datos = urllib.parse.urlencode(params).encode("ascii")
    req = urllib.request.Request(
        url,
        data=datos,
        headers={
            "Authorization": f"Bearer {secret}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except TimeoutError:
        logger.warning("Stripe POST %s: timeout (>%ds)", url, _TIMEOUT)
        raise


def _get(url: str, secret: str) -> dict:
    """GET autenticado contra la API de Stripe. Devuelve el JSON como dict."""
    req = urllib.request.Request(
        url, headers={"Authorization": f"Bearer {secret}"}
    )
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return json.loads(resp.read())
    except TimeoutError:
        logger.warning("Stripe GET %s: timeout (>%ds)", url, _TIMEOUT)
        raise


def crear_sesion_checkout(secret: str, params: dict[str, str]) -> str:
    """Crea una sesión de Checkout y devuelve la URL hosteada de pago.

    `params` ya viene armado por `billing.params_checkout` (incluye la
    cantidad de asientos). Levanta si Stripe falla o no devuelve una URL:
    el caller (`api/app.py`) traduce eso a un 502.
    """
    cuerpo = _post(billing.URL_CHECKOUT, secret, params)
    url = cuerpo.get("url")
    if not url:
        raise ValueError("Stripe no devolvió una URL de Checkout")
    return url


def actualizar_cantidad(
    secret: str, subscription_id: str, seats: int, *, team_id: str = ""
) -> bool:
    """Capa 31: deja la suscripción `subscription_id` en `seats` asientos
    (cobro por usuario). Devuelve True si lo logró, False si no.

    Best-effort: NUNCA levanta. Un fallo acá no debe tumbar el join de un
    miembro ni hacer reintentar un webhook — solo significa que la
    suscripción quedó con la cantidad anterior. Como la cantidad que se
    fija es ABSOLUTA (= miembros actuales), el próximo ajuste la corrige
    sola. Por eso se loguea y se sigue.

    `team_id` es opcional y SOLO para correlación en logs (no afecta la
    llamada a Stripe); el caller lo pasa con `functools.partial` desde
    `run_in_executor` para que un operador pueda rastrear qué equipo
    desencadenó el ajuste fallido.

    Dos llamadas a Stripe: (1) GET la suscripción para encontrar el id de
    su único subscription item (`si_...`); (2) POST ese item con la
    cantidad nueva. Son raras (entra un miembro a un equipo premium), así
    que dos round-trips no son un problema y evitan tener que guardar el
    id del item en la DB.
    """
    if not secret or not subscription_id:
        return False
    ctx = f" (team={team_id})" if team_id else ""
    try:
        sub = _get(
            f"{billing.URL_SUSCRIPCIONES}/{subscription_id}", secret
        )
        item_id = billing.item_id_de_suscripcion(sub)
        if not item_id:
            logger.warning(
                "Stripe: la suscripción %s no tiene items; no se ajustan "
                "asientos%s", subscription_id, ctx,
            )
            return False
        _post(
            f"{billing.URL_ITEMS}/{item_id}",
            secret,
            billing.params_actualizar_cantidad(seats),
        )
        logger.info(
            "Stripe: suscripción %s -> %d asiento(s)%s",
            subscription_id, max(1, int(seats)), ctx,
        )
        return True
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as e:
        # `URLError` engloba HTTP 4xx/5xx (HTTPError es subclase) y errores
        # de red puros — el `repr` deja claro cuál fue.
        logger.warning(
            "Stripe: no se pudo ajustar los asientos de %s%s: %r",
            subscription_id, ctx, e,
        )
        return False
