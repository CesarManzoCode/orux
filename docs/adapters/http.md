# Adapter: HTTP (inbound)

`backend/orux/adapters/inbound/http/app.py` es la app Starlette que sirve `/api/v1/*`. Es un proceso aparte del WebSocket server.

Tres roles:

1. **Panel del operador** (`/api/v1/admin/*`): login con cuenta de admin → token bearer → CRUD sobre teams/users/plans.
2. **OAuth GitHub** (`/oauth/github/login`, `/oauth/github/callback`): flujo OAuth completo.
3. **Stripe webhooks** (`/api/v1/billing/webhook`): recibe eventos verificados, cambia planes.

Más: healthcheck, `/api/v1/track` (analytics propio), `/api/v1/errors` (reportería de errores del cliente), `/api/v1/status` (público — para uptime monitoring).

## Por qué proceso aparte

Decisión load-bearing. El servidor WS lleva conexiones largas (devs editando), el HTTP lleva requests cortos (panel admin, webhooks). Mezclarlos significa:

- Un bug en el HTTP tumba la colaboración.
- Un deploy del panel admin requiere downtime del WS.
- Las dependencias se mezclan (`starlette` viaja al runtime del WS).

Separar = **un fallo en `api` no puede tumbar la colaboración**. Es la versión de bulkhead que pediría cualquier guía de Erlang/OTP.

## `crear_app(users, teams, webhooks)`

```python
def crear_app(users, teams, webhooks=None) -> Starlette:
    """Arma el Starlette ASGI con todas las rutas.
    
    `users`, `teams`, `webhooks` son los stores Postgres (PgUserStore, etc.)
    pasados desde el composition root del proceso api.
    """
    routes = [
        Route("/api/v1/login", _login, methods=["POST"]),
        Route("/api/v1/users", _usuarios),
        Route("/api/v1/teams", _teams),
        Route("/api/v1/teams/{tid}", _detalle),
        Route("/api/v1/teams/{tid}", _borrar_team, methods=["DELETE"]),
        Route("/api/v1/users/{username}", _borrar_usuario, methods=["DELETE"]),
        Route("/api/v1/teams/{tid}/plan", _plan, methods=["POST"]),
        Route("/oauth/github/login", _gh_login),
        Route("/oauth/github/callback", _gh_callback),
        Route("/api/v1/billing/checkout", _billing_checkout, methods=["POST"]),
        Route("/api/v1/billing/webhook", _billing_webhook, methods=["POST"]),
        Route("/api/v1/errors", _client_error, methods=["POST"]),
        Route("/api/v1/track", _client_track, methods=["POST"]),
        Route("/api/v1/status", _status),
        Route("/health", _health),
    ]
    middleware = [Middleware(BaseHTTPMiddleware, dispatch=_logging_middleware)]
    return Starlette(routes=routes, middleware=middleware, lifespan=_lifespan)
```

`app.state.users`, `app.state.teams`, `app.state.webhooks` se setean en `_lifespan` (Starlette inicia/limpia).

## Auth del operador (`_login` + `_gate`)

```python
async def _login(req):
    body = await req.json()
    token = await service.login_operador(
        req.app.state.users, _ADMIN_USER, _SECRET,
        body["username"], body["password"],
    )
    if token is None:
        return JSONResponse({"error": "no autorizado"}, status_code=401)
    return JSONResponse({"token": token})
```

Hubo un cambio importante: **antes** era un único `ORUX_ADMIN_TOKEN` que el cliente mandaba en cada request (un secreto compartido viajando por la red, sin identidad, sin rotación por cuenta).

**Ahora**: el operador es una CUENTA ya registrada (env `ORUX_ADMIN_USER`); entra con su usuario + contraseña normales (PBKDF2 igual que el login del IDE), recibe un token de sesión firmado con HMAC. El secreto de firma (`ORUX_ADMIN_TOKEN`, reusado y resignificado) NUNCA sale del server.

`_gate(req)` se llama al inicio de cada handler protegido:

```python
def _gate(req) -> JSONResponse | None:
    """None = pasa. Sin configurar: 503. Token inválido: 401."""
    if not _ADMIN_USER or not _SECRET:
        return JSONResponse({"error": "API no configurada"}, status_code=503)
    cab = (req.headers.get("authorization", "") or "").strip()
    if cab[:7].lower() == "bearer ":
        tok = cab[7:].strip()
    else:
        tok = ""
    if service.operador_de_token(tok, _ADMIN_USER, _SECRET) is not None:
        return None
    return JSONResponse({"error": "no autorizado"}, status_code=401)
```

Comparación case-insensitive de "Bearer " + strip de espacios: algunos proxies normalizan a `'bearer'` o agregan espacios; un cliente legítimo no debería fallar por eso.

## Rate limit del login (BACKEND-AUDIT-0003 / -0163)

```python
def _rate_limit_login(ip) -> bool:
    """3 intentos por minuto por IP."""
```

3 (no 5) tras Sprint G. Si la IP supera, devuelve `429 Too Many Requests` con `Retry-After: 60`.

Mismo patrón que el `_rate_limit_errors` y `_rate_limit_track` (cada uno con su tope y ventana).

## OAuth GitHub

### `_gh_login`

```python
async def _gh_login(_req):
    if not _oauth_ok():
        return JSONResponse({"error": "OAuth no configurado"}, status_code=503)
    state = firmar_state(_SESSION_SECRET)
    return RedirectResponse(
        url_autorizacion(_GH_CLIENT_ID, _GH_REDIRECT, state),
        status_code=302,
    )
```

302 a GitHub con `state` CSRF firmado (stateless, se valida en el callback).

### `_gh_callback`

```python
async def _gh_callback(req):
    code = req.query_params.get("code", "")
    state = req.query_params.get("state", "")
    
    if not code or not validar_state(state, _SESSION_SECRET):
        return _volver(error="state")
    if not _state_consumir(state, time.time()):
        return _volver(error="state")  # replay
    
    perfil = await run_in_threadpool(_intercambiar, code)
    usuario = identidad_github(perfil)  # "gh:torvalds"
    await req.app.state.users.asegurar_externo(usuario)
    
    ttl_seg = _env_ttl_session()
    token = crear_token(usuario, _SESSION_SECRET, ttl_seg=ttl_seg)
    return _volver(token=token)
```

Lo no obvio:

- **`_state_consumir`** mantiene un set efímero de states ya usados (anti-replay dentro de la ventana de 120s). Es local del proceso: si en el futuro hay réplicas, externalizar a Postgres.
- **`_intercambiar(code)`** es la única función con red (POST a GitHub). Vive en este módulo (no en el adapter OAuth) porque cada proveedor tiene su propio formato de respuesta y curva de errores.
- **`_volver(error?, token?)`** redirige al SPA con `#oauth=ok&token=...` o `#oauth=error&reason=state`. El cliente parsea el hash y procede.

### `_sanitizar_app_url(crudo, public_url)`

Defensa contra open redirect. El cliente pasa `?app=<url>` para que tras el OAuth lo redirijamos a una sub-página. Sin validación, un atacante manda `?app=https://evil.com/phish?token={STOLEN}` y la víctima sigue el redirect.

`_sanitizar_app_url` rechaza URLs externas (solo permite paths bajo `public_url`).

## Stripe webhook

```python
async def _billing_webhook(req):
    payload = await req.body()  # bytes CRUDOS — no re-serializar
    cabecera = req.headers.get("stripe-signature", "")
    
    if not verificar_firma_webhook(payload, cabecera, _STRIPE_WEBHOOK_SECRET):
        logger.warning("webhook con firma inválida desde %s", _ip_de(req))
        return Response(status_code=400)
    
    try:
        evento = evento_de_payload(payload)
    except ValueError:
        return Response(status_code=400)
    
    aplicado = await service.aplicar_evento_stripe(
        req.app.state.teams, evento, webhooks=req.app.state.webhooks,
    )
    
    return Response(status_code=200)  # SIEMPRE 200 si parseamos
```

Decisiones:

- **Body crudo bytes**: re-parsear y re-serializar cambia los bytes y rompe la firma.
- **200 incluso si el evento se ignora**: si devolvemos 400, Stripe reintenta el webhook. Para eventos que no nos interesan (otros tipos) o ya procesados (idempotencia), un 200 dice "lo recibí, no me lo mandes de nuevo".
- **400 solo si la firma o el formato son inválidos** (Stripe maliciosamente formado o request real con problema): ahí sí, no procesar.

## Healthcheck (`_health`)

```python
async def _health(req):
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
```

Verifica también la DB (BACKEND-AUDIT-0162). Sin DB ping, un Postgres caído post-startup quedaba invisible al orquestador (docker-compose / k8s).

## `/api/v1/status` (público)

```python
async def _status(req):
    return JSONResponse({
        "ok": True,
        "uptime_s": int(time.monotonic() - _STARTED_AT),
        "version": os.environ.get("ORUX_VERSION", "dev"),
    })
```

Para UptimeRobot / cronjobs externos. Sin auth. Sin info sensible.

## `/api/v1/errors` y `/api/v1/track` (reportería)

`_client_error`: el cliente del IDE postea errores JS no atrapados (`error-reporter.ts`). El handler loguea + responde 204. Rate-limit por IP.

`_client_track`: analytics propio. El frontend de la landing postea `pageview` con `keepalive` (fire-and-forget). Sin cookies, sin IDs persistentes. Los datos viven en logs (`docker compose logs api | grep client_track`).

## Logging middleware

```python
async def _logging_middleware(request, call_next):
    inicio = time.monotonic()
    response = await call_next(request)
    dur = time.monotonic() - inicio
    logger.info(
        "%s %s -> %d (%.0f ms) [%s]",
        request.method, request.url.path, response.status_code,
        dur * 1000, _ip_de(request),
    )
    return response
```

Cada request loguea método, path, status, duración, IP. Sin headers, sin body (PII).

## Lifespan

```python
@contextlib.asynccontextmanager
async def _lifespan(app):
    db = await Database.conectar(_DSN)
    app.state.db = db
    app.state.users = PgUserStore(db)
    app.state.teams = PgTeamStore(db)
    app.state.webhooks = PgWebhooksStore(db)
    
    # Tareas de fondo
    purga_task = asyncio.create_task(_purgar_webhooks_periodico(app.state.webhooks))
    
    yield
    
    # Cleanup
    purga_task.cancel()
    await db.close()
```

`_purgar_webhooks_periodico(webhooks)`: cada 24h borra eventos procesados con `processed_at < now() - 30 days`. Evita que la tabla crezca sin techo.

## Cómo arranca

```python
# adapters/inbound/http/__main__.py
import uvicorn
from .app import crear_app

if __name__ == "__main__":
    # crear_app via lifespan (que conecta DB y arma los stores)
    app = ...
    uvicorn.run(app, host="0.0.0.0", port=8800)
```

En docker-compose, el contenedor `api` corre este `__main__`. Caddy proxy reverso lo expone en `https://orux.space/api/v1/*`.

## Comparación con el WS

| | WS server | HTTP api |
|---|---|---|
| Puerto | 8765 | 8800 |
| Stateful por cliente | sí (TeamRuntime + roster) | no |
| Conexiones largas | sí | no |
| Cantidad de archivos | 10 (~2300 LOC) | 1 (~990 LOC) |
| Stores que usa | users, teams, ownership, proposals | users, teams, webhooks |
| Procesos | 1 (asyncio loop) | 1 (asyncio + uvicorn) |
| Si se cae | colaboración cae | panel admin cae, colaboración sigue |
