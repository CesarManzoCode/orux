"""Cáscara ASGI (starlette) de la API de operador — capa 23.

Solo traduce HTTP <-> `service.py` (donde vive la lógica, ya testeada en
sandbox). starlette se importa acá a propósito: este módulo solo lo carga
uvicorn en el deploy; el sandbox (sin internet/sin starlette) NUNCA lo
importa — los tests prueban `service.py`, no esto. Mismo patrón que
pyright/asyncpg/tree-sitter: la cáscara de I/O se verifica en el VPS.

Montado en `/api/v1` (lo pidió el usuario; versionar el path ahora es
gratis). NO es API pública: token de OPERADOR de plataforma (vos), rol
distinto del admin-de-equipo de capa 12/15.

Seguridad (una vez): el operador es una CUENTA ya registrada
(`ORUX_ADMIN_USER`) que entra con su usuario+contraseña normales y
recibe un token de SESIÓN firmado (HMAC; secreto `ORUX_ADMIN_TOKEN` que
NUNCA sale del server — solo firma/verifica). Antes el cliente mandaba el
secreto crudo en cada request; ahora no transmite ningún secreto. Sin
`ORUX_ADMIN_USER` o sin `ORUX_ADMIN_TOKEN` la API queda CERRADA (503),
nunca abierta. La lógica (PBKDF2 + firmar/validar) vive en `service.py` y
se prueba 100% en sandbox; acá solo HTTP. Los stores viven en `app.state`
(deploy: Postgres en startup; tests: inyectados) — UN set de handlers.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import os
import time
import urllib.error
import urllib.parse
import urllib.request

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse, RedirectResponse, Response
from starlette.routing import Route

from orux import billing, stripe_client
from orux._net import ip_proxy_confiable
from orux.db.pool import Database
from orux.db.stores import PgUserStore, PgWebhooksStore
from orux.identity import (
    crear_token,
    firmar_state,
    identidad_github,
    url_autorizacion,
    usuario_de_token,
    validar_state,
)
from orux.identity.oauth import URL_PERFIL, URL_TOKEN
from orux.teams import PgTeamStore
from orux.api import service  # legacy: service vive en orux.api (re-export de application/http_use_cases)

logger = logging.getLogger(__name__)

# Quién es el operador (una cuenta registrada) y el secreto de FIRMA de sus
# tokens de sesión (nunca se manda al cliente). Faltando cualquiera: 503.
_ADMIN_USER = os.environ.get("ORUX_ADMIN_USER", "")
_SECRET = os.environ.get("ORUX_ADMIN_TOKEN", "")


# --- Rate limiting + security headers (BACKEND-AUDIT-0003, -0163) ---------
#
# Sin esto, /api/v1/login está expuesto a fuerza bruta sobre la cuenta
# más privilegiada de la plataforma. Implementado in-process (sin Redis):
# diccionario IP -> deque de timestamps, ventana deslizante. Para deploy
# multi-réplica habría que externalizar; nota dejada arriba del bucket.

_LOGIN_RPM = 3  # requests por minuto por IP (capa 35: bajado de 5→3 antes
                # del anuncio; el operador `ORUX_ADMIN_USER` es target
                # obvio y PBKDF2 600k iteraciones ya hace caro el ataque,
                # esto es defensa en profundidad)
_ERRORS_RPM = 60  # tope generoso de reportes de error por IP (es para
                  # debugging propio, los errores legítimos pueden ser
                  # muchos en una sesión problemática; el cliente además
                  # debounce-a antes de mandar).
_TRACK_RPM = 120  # más permisivo: la landing puede generar varios eventos
                  # legítimos (pageview + cta_click + ...) en una sola
                  # visita. 120/min sigue siendo asfixiante para un bot.

# Ventana deslizante (en segundos) sobre la que se cuentan los buckets.
# El sufijo "_RPM" en las constantes de arriba mide "por minuto" — sin esta
# constante con nombre, el `60.0` aparecía suelto en tres funciones y un
# cambio de minuto a (por ejemplo) 30s habría requerido grep manual.
_VENTANA_RPM_SEG = 60.0

# Capacidad máxima de cada bucket-dict antes de gc perezoso. Cuando un
# atacante rota IPs (>10k), purgar dicts vacíos no basta — el GC también
# tira buckets cuya última muestra ya venció la ventana (ver _rate_limit_*).
_TOPE_BUCKETS = 10_000

_login_buckets: dict[str, list[float]] = {}
_error_buckets: dict[str, list[float]] = {}
_track_buckets: dict[str, list[float]] = {}

# Capa 36: timestamp del arranque del proceso para calcular uptime en
# /api/v1/status. monotonic() no retrocede aunque el reloj del host se
# ajuste (NTP), así que la métrica es honesta.
_INICIO_MONO = time.monotonic()


def _ip_de(req: Request) -> str:
    """IP del cliente. Confiamos en X-Forwarded-For SOLO cuando la conexión
    TCP viene de un proxy de confianza (red privada / loopback de Docker
    compose). Si alguien llega directo al contenedor (mal config, otro pod
    comprometido en la red, port forward olvidado), su XFF se ignora y la
    IP de bucketing es la del socket — sin esto, rotar XFF evadía el
    rate-limit de login del operador (BACKEND-AUDIT M-04).

    Caddy en el deploy concatena al XFF existente; tomamos el PRIMERO de
    la cadena (la IP más cercana al cliente original) PERO solo cuando el
    salto inmediato (transporte) es confiable. Sin Caddy / sin proxy:
    `req.client.host` siempre.
    """
    transport_ip = req.client.host if req.client is not None else ""
    xff = req.headers.get("x-forwarded-for", "")
    if xff and ip_proxy_confiable(transport_ip):
        return xff.split(",")[0].strip()
    return transport_ip or "unknown"


def _purgar_buckets(buckets: dict[str, list[float]], corte: float) -> None:
    """GC perezoso de un bucket-dict: solo se activa si el dict superó el
    tope `_TOPE_BUCKETS`. Descarta buckets cuya última muestra venció la
    ventana (no solo los vacíos): un atacante rotando >10k IPs con goteo
    los mantendría no-vacíos y el dict crecería sin control."""
    if len(buckets) <= _TOPE_BUCKETS:
        return
    muertas = [k for k, v in buckets.items() if not v or v[-1] <= corte]
    for k in muertas:
        buckets.pop(k, None)


def _rate_limit(
    buckets: dict[str, list[float]], ip: str, tope_rpm: int,
) -> bool:
    """Núcleo del rate limiter por IP. True = OK; False = superó el tope.
    Bucket por IP con limpieza perezosa de muestras + gc del dict. Tres
    consumidores (login, errors, track) que solo difieren en su tope.
    Antes este bloque vivía duplicado en 3 funciones; consolidar evita
    drift (e.g. cambiar la ventana en una y olvidar las otras)."""
    ahora = time.monotonic()
    corte = ahora - _VENTANA_RPM_SEG
    bucket = buckets.setdefault(ip, [])
    bucket[:] = [t for t in bucket if t > corte]
    if len(bucket) >= tope_rpm:
        return False
    bucket.append(ahora)
    _purgar_buckets(buckets, corte)
    return True


def _rate_limit_login(ip: str) -> bool:
    """True = OK; False = está superando el tope."""
    return _rate_limit(_login_buckets, ip, _LOGIN_RPM)


def _rate_limit_errors(ip: str) -> bool:
    """Mismo patrón que login, pero más permisivo. Los errores son señal
    útil para nosotros — preferimos perder algunos si una IP se vuelve
    abusiva, antes que floodear los logs."""
    return _rate_limit(_error_buckets, ip, _ERRORS_RPM)


def _rate_limit_track(ip: str) -> bool:
    """Tope para /api/v1/track. Más permisivo aún: una visita normal puede
    generar varios eventos legítimos. Si una IP se pasa, la silenciamos
    (el analytics local pierde algunas señales, no es crítico)."""
    return _rate_limit(_track_buckets, ip, _TRACK_RPM)


class _SeguridadHeaders(BaseHTTPMiddleware):
    """Headers de seguridad mínimos en TODAS las respuestas (BACKEND-AUDIT
    grupo API). CSP estricta para los endpoints JSON: no servimos HTML.
    Para /oauth/* que sí redirige, los headers no rompen (302 igual los
    lleva)."""

    async def dispatch(self, request: Request, call_next) -> Response:
        resp = await call_next(request)
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "no-referrer")
        resp.headers.setdefault(
            "Strict-Transport-Security",
            "max-age=31536000; includeSubDomains",
        )
        resp.headers.setdefault(
            "Content-Security-Policy", "default-src 'none'; frame-ancestors 'none'",
        )
        return resp


# Tope de body para POSTs JSON (BACKEND-AUDIT-0193). Starlette no lo impone
# por defecto. 64KB es holgado para el login del operador y los planes; un
# body más grande es ruido o ataque.
_MAX_BODY_BYTES = 64 * 1024


class _LimiteBody(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        # El webhook de Stripe se exime del tope chico: su cuerpo puede
        # traer eventos algo más grandes que un login, y además debe
        # llegar EXACTO (byte a byte) para verificar la firma HMAC. Su
        # tamaño real lo acota Stripe del otro lado.
        if request.url.path == "/api/v1/billing/webhook":
            return await call_next(request)
        cl = request.headers.get("content-length")
        if cl is not None:
            try:
                if int(cl) > _MAX_BODY_BYTES:
                    return JSONResponse(
                        {"error": "body demasiado grande"},
                        status_code=413,
                    )
            except ValueError:
                pass
        return await call_next(request)

# --- GitHub OAuth (capa nueva, superficie PÚBLICA, no la de operador) -----
#
# Cerrado por defecto: faltando cualquier pieza, /oauth/github/* responde
# 503 y NUNCA inicia un flujo a medias (mismo principio que la consola de
# operador). `_SESSION_SECRET` es el MISMO que verifica el server WS
# (ORUX_SESSION_SECRET inyectado a ambos contenedores): el token que se
# emite acá lo acepta `SessionMessage` tal cual, sin tocar el protocolo.
_GH_CLIENT_ID = os.environ.get("ORUX_GITHUB_CLIENT_ID", "")
_GH_CLIENT_SECRET = os.environ.get("ORUX_GITHUB_CLIENT_SECRET", "")
# URL EXACTA registrada en la OAuth App de GitHub. Explícita a propósito:
# derivarla del header Host sería spoofeable (open redirect / robo de code).
_GH_REDIRECT = os.environ.get("ORUX_OAUTH_REDIRECT", "")
_SESSION_SECRET = os.environ.get("ORUX_SESSION_SECRET", "")
# A dónde vuelve el navegador con el token ya emitido. El front (otra
# sesión) lo lee de `?session=` y manda `SessionMessage`, igual que el
# auto-login con `orux_session`. Default razonable: el SPA en /app/.
#
# BACKEND-AUDIT-0294: si el operador setea `ORUX_APP_URL=https://atacante`
# por error de config, el callback de OAuth redirige ahí con el token de
# sesión (open redirect). Forzamos rutas RELATIVAS (mismo origen) o
# absolutas con el MISMO host de `ORUX_PUBLIC_URL`. Fail-open al default
# si la cadena es maliciosa: nunca dejamos que `_volver()` mande a otro
# origen.
def _sanitizar_app_url(crudo: str, public_url: str) -> str:
    s = (crudo or "/app/").strip()
    if not s:
        return "/app/"
    # Sin esquema y arrancando con `/` o sin path absoluto remoto: es
    # relativa al origen del callback. Seguro.
    if "://" not in s and not s.lstrip().startswith("//"):
        return s
    # Cadena absoluta: solo se acepta si comparte host con ORUX_PUBLIC_URL.
    try:
        u = urllib.parse.urlparse(s)
        p = urllib.parse.urlparse(public_url or "")
    except (ValueError, TypeError):
        logger.warning(
            "ORUX_APP_URL inválido (%r); usando /app/ por seguridad", s,
        )
        return "/app/"
    if p.netloc and u.netloc == p.netloc and u.scheme in ("http", "https"):
        return s
    logger.warning(
        "ORUX_APP_URL apunta a otro origen (%r vs %r); usando /app/ por "
        "seguridad (open redirect)", u.netloc, p.netloc,
    )
    return "/app/"


_APP_URL = _sanitizar_app_url(
    os.environ.get("ORUX_APP_URL", "/app/"),
    os.environ.get("ORUX_PUBLIC_URL", ""),
)


def _oauth_ok() -> bool:
    return bool(
        _GH_CLIENT_ID and _GH_CLIENT_SECRET
        and _GH_REDIRECT and _SESSION_SECRET
    )


# --- Stripe (cobro de la suscripción Premium) ----------------------------
#
# Cerrado por defecto, igual que OAuth y la consola de operador: si falta
# cualquier pieza, /api/v1/billing/* responde 503 y el botón de upgrade
# del Hub no hace nada. No rompe nada dejarlo sin configurar.
#
# - STRIPE_SECRET_KEY (`sk_test_...` / `sk_live_...`): autentica NUESTRAS
#   llamadas a la API de Stripe (crear la sesión de Checkout). Secreto:
#   nunca sale del server.
# - STRIPE_WEBHOOK_SECRET (`whsec_...`): el secreto con el que Stripe
#   firma cada webhook; con él verificamos que un POST a /billing/webhook
#   lo mandó Stripe de verdad (sin esto, cualquiera haría premium gratis).
# - ORUX_PUBLIC_URL: el origen público (https://tu-dominio). Arma las URLs
#   de retorno de Stripe (success/cancel). Explícito a propósito: derivarlo
#   del header Host sería manipulable, igual que con ORUX_OAUTH_REDIRECT.
_STRIPE_SECRET = os.environ.get("STRIPE_SECRET_KEY", "")
_STRIPE_WEBHOOK_SECRET = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
_PUBLIC_URL = os.environ.get("ORUX_PUBLIC_URL", "").rstrip("/")
# Precio POR ASIENTO de la suscripción (capa 31: cobro por usuario). Se
# define INLINE en cada sesión de Checkout (no es un Price del dashboard
# de Stripe): así no hace falta crear nada en Stripe para probar. El
# default 1000 = 10.00 MXN es un precio de PRUEBA por asiento; el real se
# pone después subiendo STRIPE_PRICE_AMOUNT. La factura mensual del equipo
# sale STRIPE_PRICE_AMOUNT * (número de miembros).
_STRIPE_CURRENCY = os.environ.get("STRIPE_PRICE_CURRENCY", "mxn")
_STRIPE_INTERVAL = os.environ.get("STRIPE_PRICE_INTERVAL", "month")
_STRIPE_PRODUCTO = os.environ.get("STRIPE_PRICE_NAME", "Orux Premium")


def _stripe_amount() -> int:
    """Monto POR ASIENTO de la suscripción, en centavos. Default 1000
    (= 10.00 MXN), precio de prueba. Robusto ante un env mal puesto -> cae
    al default."""
    try:
        v = int(os.environ.get("STRIPE_PRICE_AMOUNT", "1000"))
    except (TypeError, ValueError):
        v = 1000
    return max(1, v)


def _billing_ok() -> bool:
    """Billing configurado = las tres piezas presentes. Fail-closed: si
    falta una, /api/v1/billing/* da 503 (nunca a medias). En la práctica
    se configuran juntas (ver .env.example)."""
    return bool(_STRIPE_SECRET and _STRIPE_WEBHOOK_SECRET and _PUBLIC_URL)


def _crear_sesion_checkout(
    team_id: str, team_nombre: str, seats: int
) -> str:
    """Llama a la API de Stripe (vía `stripe_client`) y devuelve la URL de
    la página de pago hosteada. Bloqueante (urllib, stdlib); el caller la
    corre en el threadpool. Se ejercita en el VPS (el sandbox no tiene
    internet) — mismo patrón que `_intercambiar` del OAuth.

    `seats` (capa 31): cantidad de asientos = miembros del equipo. El cobro
    es por usuario, así que la suscripción arranca con esa cantidad y la
    factura mensual sale `precio_por_asiento * seats`."""
    success = f"{_PUBLIC_URL}{_APP_URL}?stripe=success"
    cancel = f"{_PUBLIC_URL}{_APP_URL}?stripe=cancel"
    params = billing.params_checkout(
        team_id,
        f"{_STRIPE_PRODUCTO} · {team_nombre}",
        success,
        cancel,
        currency=_STRIPE_CURRENCY,
        unit_amount=_stripe_amount(),
        interval=_STRIPE_INTERVAL,
        seats=seats,
    )
    return stripe_client.crear_sesion_checkout(_STRIPE_SECRET, params)


def _volver(error: str = "", token: str = ""):
    """Redirige el navegador de vuelta al SPA. Con token (éxito) o con un
    código de error legible (el front decide qué mostrar). 302.

    BACKEND-AUDIT-0019: el token va en FRAGMENT (`#session=...`), no en
    query (`?session=...`). El fragmento NO se manda al server en peticiones
    siguientes, NO aparece en Referer, NO queda en logs de proxy/CDN — el
    SPA lo lee desde `window.location.hash` y lo guarda. El error sí va en
    query porque no es sensible y conviene en logs para diagnóstico.
    """
    if token:
        sep = "#"
        return RedirectResponse(
            f"{_APP_URL}{sep}{urllib.parse.urlencode({'session': token})}",
            status_code=302,
        )
    sep = "&" if "?" in _APP_URL else "?"
    return RedirectResponse(
        f"{_APP_URL}{sep}{urllib.parse.urlencode({'oauth_error': error})}",
        status_code=302,
    )


def _intercambiar(code: str) -> dict:
    """Bloqueante (urllib, stdlib — cero deps): canjea `code` por un token y
    lee el perfil de GitHub. Vive en la cáscara y se corre en el threadpool;
    se ejercita en el VPS (sandbox sin internet), igual que toda la I/O de
    `api/app.py`. Timeouts cortos: un GitHub colgado no cuelga al worker.

    Errores propagados (los atrapa el caller en `_gh_callback`):
    - `urllib.error.URLError`: GitHub inalcanzable / DNS / TLS.
    - `TimeoutError`: respuesta por encima del timeout.
    - `ValueError`: body no-JSON o GitHub devolvió un error en el body
      (p.ej. `{"error":"bad_verification_code"}` con HTTP 200).
    - `KeyError`: body JSON pero sin `access_token` (forma inesperada).
    El mensaje del error incluye la etapa (token/perfil) para diagnóstico.
    Nunca se loguean ni `code` ni `tok`: son material sensible.
    """
    datos = urllib.parse.urlencode({
        "client_id": _GH_CLIENT_ID,
        "client_secret": _GH_CLIENT_SECRET,
        "code": code,
        "redirect_uri": _GH_REDIRECT,
    }).encode("ascii")
    r1 = urllib.request.Request(
        URL_TOKEN, data=datos, headers={"Accept": "application/json"}
    )
    with urllib.request.urlopen(r1, timeout=10) as resp:
        body = resp.read()
    try:
        token_payload = json.loads(body)
    except ValueError as e:
        raise ValueError(f"OAuth token: respuesta no-JSON ({e})") from e
    if not isinstance(token_payload, dict):
        raise ValueError("OAuth token: payload no es objeto JSON")
    if "access_token" not in token_payload:
        # GitHub señala fallos con campo `error` (p.ej. bad_verification_code).
        # Lo logueamos como contexto pero NO el body completo (puede traer
        # `error_description` con URLs/IDs internos).
        motivo = token_payload.get("error", "campo access_token ausente")
        raise ValueError(f"OAuth token: {motivo}")
    tok = token_payload["access_token"]
    r2 = urllib.request.Request(
        URL_PERFIL,
        headers={
            "Authorization": f"Bearer {tok}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "orux",
        },
    )
    with urllib.request.urlopen(r2, timeout=10) as resp:
        body = resp.read()
    try:
        perfil = json.loads(body)
    except ValueError as e:
        raise ValueError(f"OAuth perfil: respuesta no-JSON ({e})") from e
    if not isinstance(perfil, dict):
        raise ValueError("OAuth perfil: payload no es objeto JSON")
    return perfil


async def _gh_login(_req: Request):
    """Arranca el flujo: 302 a GitHub con un `state` CSRF firmado (stateless,
    se valida en el callback). Sin configurar: 503, no a medias."""
    if not _oauth_ok():
        return JSONResponse(
            {"error": "GitHub OAuth no configurado"}, status_code=503
        )
    state = firmar_state(_SESSION_SECRET)
    return RedirectResponse(
        url_autorizacion(_GH_CLIENT_ID, _GH_REDIRECT, state),
        status_code=302,
    )


# BACKEND-AUDIT-0015: set efímero de states ya consumidos para evitar replay
# dentro de la ventana de validez (120s). Es un set local del proceso: si en
# el futuro hay réplicas múltiples (uvicorn --workers >1 o multi-pod), esto
# se externaliza a Postgres. GC perezoso.
#
# Seguridad de concurrencia: `_state_consumir` es 100% sync (cero `await`),
# por lo que el event-loop de asyncio NO la puede pre-emptar a mitad. El
# patrón "comprobar si está, agregar si no" es atómico dentro de un mismo
# proceso CPython. Si algún día se introduce un `await` aquí adentro, hay
# que añadir un `asyncio.Lock` o externalizar el estado.
_oauth_states_usados: dict[str, float] = {}


def _state_consumir(state: str, ahora: float) -> bool:
    """True si pudo consumir (primer uso); False si ya estaba usado (replay).
    Limpia entradas viejas (>5min) en cada llamada.

    INVARIANTE: esta función debe permanecer 100% sync (sin `await`) — ver
    nota sobre `_oauth_states_usados` arriba. Si necesita I/O async, hay
    que añadir un `asyncio.Lock` global o externalizar el set."""
    # GC: borra states con >300s de antigüedad.
    if len(_oauth_states_usados) > 1024:
        corte = ahora - 300.0
        for k, v in list(_oauth_states_usados.items()):
            if v < corte:
                _oauth_states_usados.pop(k, None)
    if state in _oauth_states_usados:
        return False
    _oauth_states_usados[state] = ahora
    return True


async def _gh_callback(req: Request):
    """GitHub vuelve acá. Valida `state`, canjea `code`, deriva la identidad
    `gh:<login>`, asegura la cuenta (sin password) y emite el MISMO token de
    sesión de la capa 7. Cualquier fallo -> vuelve al SPA con un error
    legible, nunca un 500 crudo (esto lo ve un humano en el navegador)."""
    if not _oauth_ok():
        return JSONResponse(
            {"error": "GitHub OAuth no configurado"}, status_code=503
        )
    if req.query_params.get("error"):
        # El usuario canceló el consentimiento en GitHub.
        return _volver(error="cancelado")
    code = req.query_params.get("code", "")
    state = req.query_params.get("state", "")
    if not code or not validar_state(state, _SESSION_SECRET):
        # state ausente/falso/vencido: posible CSRF o link viejo.
        return _volver(error="state")
    if not _state_consumir(state, time.time()):
        # Replay: alguien intercepta el callback y lo reusa. La firma es
        # válida y está fresca, pero ya consumimos este state — denegar.
        logger.warning("OAuth state replay detectado")
        return _volver(error="state")
    from starlette.concurrency import run_in_threadpool

    try:
        perfil = await run_in_threadpool(_intercambiar, code)
        usuario = identidad_github(perfil)
    except (urllib.error.URLError, KeyError, ValueError, TimeoutError) as e:
        logger.warning("OAuth GitHub falló: %r", e)
        return _volver(error="github")
    await req.app.state.users.asegurar_externo(usuario)
    # Token de sesión con TTL: 30 días por default, el mismo que el WS server.
    ttl_seg = _env_ttl_session()
    token = crear_token(usuario, _SESSION_SECRET, ttl_seg=ttl_seg)
    logger.info("OAuth GitHub OK: %s", usuario)
    return _volver(token=token)


def _env_ttl_session() -> int:
    """Mismo default y clamp que el SyncServer."""
    try:
        v = int(os.environ.get("ORUX_TOKEN_TTL_SEC", 30 * 24 * 3600))
    except (TypeError, ValueError):
        v = 30 * 24 * 3600
    return max(0, min(365 * 24 * 3600, v))


def _gate(req: Request) -> JSONResponse | None:
    """None = pasa. Sin configurar: cerrado (503). Token de sesión inválido
    o no es el operador: 401. La validación (firma HMAC + que el usuario
    SEA el operador) la hace `service.operador_de_token` (pura, testeada).

    Bearer: comparación case-INsensitive del prefijo + strip de espacios
    (BACKEND-AUDIT grupo api). Algunos proxies normalizan a 'bearer' o
    agregan espacios; un cliente legítimo no debería caerse por eso.
    """
    if not _ADMIN_USER or not _SECRET:
        return JSONResponse(
            {"error": "API de operador no configurada (falta "
                      "ORUX_ADMIN_USER / ORUX_ADMIN_TOKEN)"},
            status_code=503,
        )
    cab = (req.headers.get("authorization", "") or "").strip()
    if cab[:7].lower() == "bearer ":
        tok = cab[7:].strip()
    else:
        tok = ""
    if service.operador_de_token(tok, _ADMIN_USER, _SECRET) is not None:
        return None
    return JSONResponse({"error": "no autorizado"}, status_code=401)


async def _login(req: Request) -> JSONResponse:
    """POST {username, password} -> {token}. La compuerta real: verifica
    credenciales (PBKDF2 vía el store) y que sea el operador; si OK emite
    un token de sesión firmado. 401 genérico si algo falla (no filtra qué
    cuenta es el operador). 503 si no está configurado. 429 si supera el
    rate-limit por IP (BACKEND-AUDIT-0003 / -0163)."""
    if not _ADMIN_USER or not _SECRET:
        return JSONResponse(
            {"error": "API de operador no configurada"}, status_code=503
        )
    ip = _ip_de(req)
    if not _rate_limit_login(ip):
        logger.warning("rate-limit login: IP %s", ip)
        return JSONResponse(
            {"error": "demasiados intentos, esperá un minuto"},
            status_code=429,
            headers={"Retry-After": "60"},
        )
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001 - body no-JSON
        return JSONResponse({"error": "body JSON inválido"},
                            status_code=400)
    token = await service.login_operador(
        req.app.state.users, _ADMIN_USER, _SECRET,
        str(body.get("username", "")), str(body.get("password", "")),
    )
    if token is None:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    return JSONResponse({"token": token})


async def _health(req: Request) -> JSONResponse:
    """Healthcheck que verifica también la DB si está disponible
    (BACKEND-AUDIT-0162). Sin DB ping, un Postgres caído post-startup
    quedaba invisible al orquestador."""
    db = getattr(req.app.state, "db", None)
    ok_db = True
    if db is not None:
        try:
            ok_db = await db.ping()
        except Exception:
            ok_db = False
    return JSONResponse(
        {"ok": ok_db, "db": ok_db},
        status_code=200 if ok_db else 503,
    )


async def _usuarios(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    return JSONResponse(await service.listar_usuarios(req.app.state.users))


async def _teams(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    return JSONResponse(await service.listar_teams(req.app.state.teams))


async def _detalle(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    d = await service.detalle_team(req.app.state.teams,
                                   req.path_params["tid"])
    if d is None:
        return JSONResponse({"error": "equipo inexistente"},
                            status_code=404)
    return JSONResponse(d)


async def _borrar_team(req: Request) -> JSONResponse:
    """Capa 23: DELETE /api/v1/teams/{tid}. Borra el equipo (CASCADE en FK
    barre members/invites/ownership/proposals). Idempotente: si ya no
    existía, 404. NO toca el workspace en disco — el operador, si quiere,
    corre `rm -rf /data/ws/<tid>` aparte (ver RUNBOOK / comando de reset
    pre-anuncio)."""
    if (g := _gate(req)) is not None:
        return g
    tid = req.path_params["tid"]
    ok = await service.borrar_team(req.app.state.teams, tid)
    if not ok:
        return JSONResponse({"error": "equipo inexistente"}, status_code=404)
    logger.info("operador borró equipo: %s", tid)
    return JSONResponse({"borrado": True, "team_id": tid})


async def _borrar_usuario(req: Request) -> JSONResponse:
    """Capa 23: DELETE /api/v1/users/{username}. Borra un usuario. 400 si:
    es el operador (no te disparas en el pie), o es creador de un equipo /
    dueño de archivos en ownership (la FK RESTRICT lo bloquea — borra los
    equipos primero). 404 si el usuario no existía."""
    if (g := _gate(req)) is not None:
        return g
    username = req.path_params["username"]
    try:
        ok = await service.borrar_usuario(
            req.app.state.users, username, admin_user=_ADMIN_USER,
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if not ok:
        return JSONResponse({"error": "usuario inexistente"}, status_code=404)
    logger.info("operador borró usuario: %s", username)
    return JSONResponse({"borrado": True, "username": username})


async def _plan(req: Request) -> JSONResponse:
    if (g := _gate(req)) is not None:
        return g
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001 - body no-JSON
        return JSONResponse({"error": "body JSON inválido"},
                            status_code=400)
    try:
        d = await service.cambiar_plan(
            req.app.state.teams, req.path_params["tid"],
            str(body.get("plan", "")),
        )
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=400)
    if d is None:
        return JSONResponse({"error": "equipo inexistente"},
                            status_code=404)
    return JSONResponse(d)


# --- Stripe: checkout (inicia el pago) + webhook (confirma) ---------------


async def _billing_checkout(req: Request) -> JSONResponse:
    """POST {team_id} -> {url}. El Hub redirige el navegador a esa `url`
    (la página de pago hosteada de Stripe).

    Auth: el token de SESIÓN del usuario — el MISMO `orux_session` que usa
    el IDE, firmado con ORUX_SESSION_SECRET (este contenedor lo comparte
    con el server WS). No es la auth de operador: es un usuario normal.
    Solo el ADMIN del equipo puede iniciar el upgrade — gestionar el plan
    es gestión del equipo, igual que invitar."""
    if not _billing_ok():
        return JSONResponse({"error": "pagos no configurados"},
                            status_code=503)
    cab = (req.headers.get("authorization", "") or "").strip()
    tok = cab[7:].strip() if cab[:7].lower() == "bearer " else ""
    usuario = usuario_de_token(tok, _SESSION_SECRET) if _SESSION_SECRET else None
    if usuario is None:
        return JSONResponse({"error": "no autenticado"}, status_code=401)
    try:
        body = await req.json()
    except Exception:  # noqa: BLE001 - body no-JSON
        return JSONResponse({"error": "body JSON inválido"}, status_code=400)
    team_id = str(body.get("team_id", ""))
    if not team_id:
        return JSONResponse({"error": "falta team_id"}, status_code=400)
    teams = req.app.state.teams
    if await teams.rol(team_id, usuario) != "admin":
        # No es admin de ese equipo (o ni siquiera es miembro). Mismo
        # criterio que invitar: solo el admin gestiona el equipo.
        return JSONResponse(
            {"error": "solo el admin del equipo puede gestionar el plan"},
            status_code=403,
        )
    equipo = await teams.equipo(team_id)
    if equipo is None:
        return JSONResponse({"error": "equipo inexistente"}, status_code=404)
    if equipo.get("plan") == "premium":
        # Ya es premium: evita crear una segunda suscripción por error.
        return JSONResponse({"error": "el equipo ya es premium"},
                            status_code=400)
    # Capa 31 (cobro por asiento): la suscripción arranca con tantos
    # asientos como miembros tenga el equipo ahora. Si después entran más,
    # el server WS sube la cantidad de la suscripción al redimir la invitación.
    seats = await teams.contar_miembros(team_id)
    from starlette.concurrency import run_in_threadpool

    try:
        url = await run_in_threadpool(
            _crear_sesion_checkout, team_id, equipo["nombre"], seats,
        )
    except (urllib.error.URLError, ValueError, KeyError, TimeoutError) as e:
        logger.warning("Stripe checkout falló: %r", e)
        return JSONResponse({"error": "no se pudo iniciar el pago"},
                            status_code=502)
    return JSONResponse({"url": url})


async def _billing_webhook(req: Request) -> JSONResponse:
    """Stripe -> acá. Verifica la firma, interpreta el evento y mueve el
    plan del equipo. SIN auth de operador: Stripe no manda un Bearer, la
    firma HMAC del cuerpo ES la autenticación.

    Códigos de respuesta pensados para el reintentador de Stripe:
    - firma inválida / payload roto -> 400 (reintentar no sirve);
    - evento aplicado o ignorado    -> 200 (un 4xx/5xx haría reintentar a
      Stripe por días — y un evento que ignoramos no es un fallo);
    - error nuestro al persistir    -> 500 a propósito: ahí el reintento
      de Stripe SÍ sirve (p. ej. Postgres caído un momento)."""
    if not _billing_ok():
        return JSONResponse({"error": "pagos no configurados"},
                            status_code=503)
    payload = await req.body()
    firma = req.headers.get("stripe-signature", "")
    if not billing.verificar_firma_webhook(
        payload, firma, _STRIPE_WEBHOOK_SECRET,
    ):
        # Intentamos extraer event_id sin validar firma (best-effort, solo
        # para correlación en logs; el evento NO se aplica).
        evt_id = ""
        try:
            evt_id = billing.event_id_de(billing.evento_de_payload(payload))
        except ValueError:
            pass
        logger.warning(
            "webhook de Stripe con firma inválida (event_id=%s)",
            evt_id or "?",
        )
        return JSONResponse({"error": "firma inválida"}, status_code=400)
    try:
        evento = billing.evento_de_payload(payload)
    except ValueError:
        logger.warning("webhook de Stripe con payload inválido")
        return JSONResponse({"error": "payload inválido"}, status_code=400)
    evt_id = billing.event_id_de(evento)
    evt_tipo = str(evento.get("type", "?"))
    try:
        res = await service.aplicar_evento_stripe(
            req.app.state.teams, evento,
            webhooks=getattr(req.app.state, "webhooks", None),
        )
    except Exception:  # noqa: BLE001
        # Falló persistir el cambio (DB caída, etc.). Devolvemos 500 a
        # propósito: Stripe reintenta el webhook con backoff y el upgrade
        # se aplica cuando la DB vuelva. El evento es reproducible desde
        # el dashboard de Stripe si hiciera falta.
        logger.exception(
            "error aplicando evento Stripe (id=%s type=%s); Stripe reintentará",
            evt_id or "?", evt_tipo,
        )
        return JSONResponse({"error": "error interno"}, status_code=500)
    return JSONResponse({"recibido": True, "aplicado": res is not None})


async def _client_error(req: Request) -> Response:
    """Recibe errores JS del cliente y los loguea en el container `api` para
    que el operador los vea con `docker compose logs api`. Sin auth: cualquier
    visitante puede reportar (la info no es sensible — son stack traces — y
    no exigir auth maximiza la captura de bugs que rompen el login mismo).

    Defensas:
    - rate limit por IP (60/min: errores legítimos pueden ser muchos en una
      sesión problemática, pero un atacante igual no puede inundar);
    - `_LimiteBody` ya recorta el body a 64KB (suficiente para un stack);
    - cap por campo acá adentro (no nos importa el último kilobyte del
      stack; importa que un campo no se vaya a 200KB);
    - 204 sin cuerpo: nada útil que devolverle al cliente, y dejar el
      response chico ayuda con el ancho de banda en sesiones que están
      mandando errores en serie."""
    ip = _ip_de(req)
    if not _rate_limit_errors(ip):
        return Response(status_code=429)
    try:
        data = await req.json()
    except Exception:  # noqa: BLE001 — body inválido = descartar
        return Response(status_code=400)
    if not isinstance(data, dict):
        return Response(status_code=400)
    msg = str(data.get("message", ""))[:500]
    stack = str(data.get("stack", ""))[:4000]
    url = str(data.get("url", ""))[:500]
    ua = str(data.get("userAgent", ""))[:300]
    kind = str(data.get("kind", "error"))[:32]
    logger.warning(
        "client_error: kind=%s ip=%s url=%r ua=%r msg=%r stack=%r",
        kind, ip, url, ua, msg, stack,
    )
    return Response(status_code=204)


async def _client_track(req: Request) -> Response:
    """Analytics propio minimalista. Mismo patrón que `_client_error`: sin
    auth, sin cookies, sin IDs persistentes. La IP se usa SOLO para rate
    limit, no se loguea con el evento. UA y referrer se cortan a tamaños
    pequeños — son señales agregadas (qué browser, de dónde llegan), no
    datos personales.

    Eventos pensados: "pageview" al cargar la landing. Si en el futuro
    sumamos `cta_click` o similar, el endpoint los acepta sin cambios.
    """
    ip = _ip_de(req)
    if not _rate_limit_track(ip):
        return Response(status_code=429)
    try:
        data = await req.json()
    except Exception:  # noqa: BLE001
        return Response(status_code=400)
    if not isinstance(data, dict):
        return Response(status_code=400)
    event = str(data.get("event", ""))[:32]
    url = str(data.get("url", ""))[:300]
    referrer = str(data.get("referrer", ""))[:300]
    ua = str(req.headers.get("user-agent", ""))[:300]
    # log estructurado: la línea es la fuente de verdad del dato. Se ve con
    # `docker compose logs api | grep client_track`.
    logger.info(
        "client_track: event=%s url=%r referrer=%r ua=%r",
        event, url, referrer, ua,
    )
    return Response(status_code=204)


async def _status(req: Request) -> JSONResponse:
    """Endpoint público de "está vivo". Para UptimeRobot, cronjobs externos,
    o debugging rápido desde la línea de comandos (`curl /api/v1/status`).
    Devuelve uptime del proceso (no del host) y versión si el operador la
    seteó vía `ORUX_VERSION` — útil para confirmar qué deploy está activo.
    Sin auth: nada sensible acá."""
    uptime_s = int(time.monotonic() - _INICIO_MONO)
    version = os.environ.get("ORUX_VERSION", "dev")
    return JSONResponse({
        "ok": True,
        "uptime_s": uptime_s,
        "version": version,
    })


_RUTAS = [
    Route("/api/v1/health", _health),
    Route("/api/v1/status", _status),
    Route("/api/v1/errors", _client_error, methods=["POST"]),
    Route("/api/v1/track", _client_track, methods=["POST"]),
    Route("/api/v1/login", _login, methods=["POST"]),
    Route("/api/v1/users", _usuarios),
    Route("/api/v1/teams", _teams),
    Route("/api/v1/teams/{tid}", _detalle),
    Route("/api/v1/teams/{tid}", _borrar_team, methods=["DELETE"]),
    Route("/api/v1/teams/{tid}/plan", _plan, methods=["POST"]),
    Route("/api/v1/users/{username}", _borrar_usuario, methods=["DELETE"]),
    # Stripe: cobro de la suscripción Premium. Superficie distinta de la
    # de operador (sin `_gate`): /checkout lo autentica el token de
    # sesión del usuario; /webhook lo autentica la firma HMAC de Stripe.
    Route("/api/v1/billing/checkout", _billing_checkout, methods=["POST"]),
    Route("/api/v1/billing/webhook", _billing_webhook, methods=["POST"]),
    # GitHub OAuth: superficie PÚBLICA (sin _gate; no es la API de
    # operador). Caddy proxya /oauth/* a este contenedor.
    Route("/oauth/github/login", _gh_login),
    Route("/oauth/github/callback", _gh_callback),
]


_MIDDLEWARE = [
    Middleware(_LimiteBody),
    Middleware(_SeguridadHeaders),
]


def crear_app(users, teams, webhooks=None) -> Starlette:
    """App con stores inyectados directo (DI; útil para tests con starlette
    instalado). `webhooks=None` deja el endpoint /billing/webhook sin
    idempotencia por event_id (sólo "fijar valores"); pasar un store
    activa la garantía exactly-once. El deploy usa `app` (Postgres en
    startup)."""
    a = Starlette(routes=_RUTAS, middleware=_MIDDLEWARE)
    a.state.users = users
    a.state.teams = teams
    a.state.webhooks = webhooks
    return a


# --- App de deploy: stores Postgres desde env (uvicorn carga esto) -------
#
# Starlette >=0.36 quitó on_startup/on_shutdown: el ciclo de vida va por un
# `lifespan` (async context manager). Conectamos Postgres al entrar y lo
# cerramos al salir; los stores quedan en app.state (un solo set de
# handlers los lee de ahí).


async def _purgar_webhooks_periodico(webhooks) -> None:
    """BACKEND-AUDIT B-07: barre la tabla `processed_webhooks` cada 24h
    para que no crezca monótonamente. Stripe ya no reentrega eventos
    tras ~30d, así que purgar lo más viejo no rompe la idempotencia (un
    evento que reapareciera tras un mes sería ruido independiente).

    Robustez igual que `barrer_*_ociosos` del server WS: el loop nunca
    muere por una excepción en una vuelta; CancelledError sí propaga al
    shutdown del lifespan."""
    DIA_SEG = 24 * 3600
    while True:
        try:
            await asyncio.sleep(DIA_SEG)
            n = await webhooks.purgar(antes_de_segundos=30 * DIA_SEG)
            if n:
                logger.info("webhooks purgados (>30d): %d", n)
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001 — el loop sobrevive
            logger.exception("purgar_webhooks_periodico: error en la vuelta")


@contextlib.asynccontextmanager
async def _lifespan(app: Starlette):
    dsn = os.environ.get("ORUX_DB_DSN", "")
    if not dsn:
        raise RuntimeError("ORUX_DB_DSN requerido para la API de operador")
    db = await Database.conectar(dsn)
    app.state.db = db
    app.state.users = PgUserStore(db)
    app.state.teams = PgTeamStore(db)
    # Idempotencia de webhooks de Stripe: tabla `processed_webhooks` ya
    # creada por `_aplicar_schema`. Cada webhook recibido se marca antes
    # de aplicarse — un evento ya procesado se ignora silenciosamente.
    app.state.webhooks = PgWebhooksStore(db)
    # BACKEND-AUDIT B-07: tarea de fondo que purga webhooks viejos cada
    # 24h. Sin esto la tabla crece sin techo (la función `purgar` existía
    # pero nadie la llamaba).
    purga = asyncio.create_task(_purgar_webhooks_periodico(app.state.webhooks))
    app.state.tarea_purga = purga
    try:
        yield
    finally:
        purga.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await purga
        await db.cerrar()


app = Starlette(routes=_RUTAS, lifespan=_lifespan, middleware=_MIDDLEWARE)
