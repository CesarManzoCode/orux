# Seguridad: Webhooks y cross-origin

## Webhooks Stripe

### Threat model

- La URL del webhook (`https://orux.space/api/v1/billing/webhook`) es pública (Stripe necesita poder POSTear).
- Sin autenticación, cualquiera puede POSTear un body falso y volver a un equipo premium gratis.
- Stripe NO manda Bearer token. La autenticación ES la firma HMAC del body.

### Mitigación: verificación HMAC firmada

```python
def verificar_firma_webhook(payload, cabecera_firma, secret, *, tolerancia_seg=300, ahora=None):
    """HMAC-SHA256 sobre "{t}.{payload}" con secret whsec_...
    Tolerancia 5min anti-replay.
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
    
    firmado = t.encode() + b"." + payload
    esperada = hmac.new(secret.encode(), firmado, sha256).hexdigest()
    
    # timing-safe comparison contra cada v1 firma
    return any(hmac.compare_digest(esperada, f) for f in firmas)
```

### Lo crítico

1. **Body en bytes crudos** (`req.body()`): re-parsear y re-serializar cambia los bytes y rompe la firma. El handler HTTP es:

```python
async def _billing_webhook(req):
    payload = await req.body()  # bytes, NO req.json()
    cabecera = req.headers.get("stripe-signature", "")
    if not verificar_firma_webhook(payload, cabecera, _STRIPE_WEBHOOK_SECRET):
        return Response(status_code=400)
    evento = evento_de_payload(payload)  # json.loads acá, no antes
```

2. **`hmac.compare_digest`** (timing-safe): un atacante que intenta forge la firma no puede inferir bytes correctos por timing.

3. **Tolerancia 5 min**: anti-replay. Un webhook interceptado y reusado tras 5 min se rechaza por timestamp.

4. **Varias firmas v1**: Stripe puede mandar múltiples durante rotación del signing secret. Aceptamos si alguna coincide.

### Mitigación: idempotencia por event_id

```python
async def aplicar_evento_stripe(teams, evento, webhooks=None):
    event_id = event_id_de(evento)
    if webhooks is not None and event_id:
        nuevo = await webhooks.marcar(event_id)
        if not nuevo:
            logger.info("Stripe: evento %s ya procesado (replay), se ignora", event_id)
            return None
    # ... resto del procesamiento
```

`PgWebhooksStore.marcar` con `INSERT ... ON CONFLICT DO NOTHING RETURNING event_id`: atómico, sin race entre dos workers procesando el mismo webhook.

Sin idempotencia, un webhook reentregado por Stripe (timeout, dashboard manual) aplicaba el cambio dos veces → ruido en logs, side-effects extra (ajuste de asientos, etc.).

### Status 200 siempre que parseamos

Si devolvemos 400, Stripe reintenta. Para eventos:

- **Tipo no relevante** (`charge.succeeded`, etc.): 200 (lo recibimos, no nos lo mandes de nuevo).
- **Ya procesado** (idempotencia): 200.
- **Equipo inexistente** (mal config, otro entorno): 200 + logger warning.

400 SOLO si:

- Firma inválida.
- JSON no parsea.

### Anti-MITM con re-serialización

Tema sutil: si el handler hace `req.json()` y luego `json.dumps(evento)` para algo, los bytes cambian. Si un atacante interceptó la firma original Y modificó el body en la red (atacante con MITM), la firma sigue siendo válida sobre los bytes originales, pero NO sobre los modificados.

Pero nosotros verificamos sobre bytes CRUDOS, no re-serializados. Si el atacante modifica un byte, la firma falla. Buena.

## Cross-origin para WebSocket (anti-CSRF WS)

### Threat model

Un sitio malicioso `evil.com` que visita la víctima puede:

- Abrir un WebSocket a `ws://orux.space:8765/` desde el browser (cookies no aplican a WS, pero un token de sesión en localStorage de orux SÍ).
- Forjar requests con el token de la víctima.

A diferencia de fetch/XHR donde CORS protege, WebSocket NO tiene preflight. La defensa es validar el `Origin` header del handshake.

### Mitigación: whitelist de origins

```python
# config.py
WS_ORIGINS = _env_list("ORUX_WS_ORIGINS", default=[
    "https://orux.space",
    "http://localhost:5173",
    "http://localhost:8080",
])

def _origen_permitido(origen):
    if not WS_ORIGINS or "*" in WS_ORIGINS:
        return True  # debug puntual
    if not origen:
        return True  # no-browser (tests, healthcheck, Electron)
    return origen in WS_ORIGINS
```

En el handshake del WS:

```python
async def _atender_conexion(self, websocket):
    origen = websocket.request.headers.get("origin", "")
    if not self._origen_permitido(origen):
        await websocket.close(code=4001, reason="origin no permitido")
        return
```

### Por qué funciona

El `Origin` header lo manda el browser AUTOMÁTICAMENTE en handshake WS y NO se puede falsificar desde JavaScript. Si la víctima visita `evil.com` y el JS abre `new WebSocket("ws://orux.space:8765/")`, el browser pone `Origin: https://evil.com`. El server lo rechaza.

### Por qué NO bloqueamos origin vacío

Conexiones sin `Origin` header:

- **Tests** (`websockets.connect` programático no lo manda por default).
- **Healthcheck** del docker-compose (TCP connect + handshake mínimo).
- **Electron / Tauri apps**: no son browsers; no aplican CSRF.
- **Plugins futuros de IDE** (VS Code extension).

Bloquearlos rompería todos estos casos legítimos. Es un trade-off documentado: confiamos en no-browser por construcción.

### REGLA OPERATIVA

**Cada cliente nuevo del navegador debe sumarse a `ORUX_WS_ORIGINS`** o el handshake responde 403.

Hoy producción: `ORUX_WS_ORIGINS=https://orux.space`. Si mañana hay app.orux.space u otro dominio, agregarlo:

```yaml
# docker-compose.yml
environment:
  ORUX_WS_ORIGINS: "https://orux.space,https://app.orux.space"
```

`ORUX_WS_ORIGINS=*` desactiva el filtro (solo debug puntual; NUNCA en producción).

## Cross-origin para HTTP

Starlette tiene middleware CORS configurable. Hoy: **NO usado** (el panel admin se sirve desde el mismo origin). Si en el futuro hay frontend en otro dominio que llame a `api.orux.space`, agregar:

```python
from starlette.middleware.cors import CORSMiddleware

middleware = [
    Middleware(CORSMiddleware,
        allow_origins=["https://app.orux.space"],
        allow_credentials=False,  # no usamos cookies, usamos Bearer
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    ),
    ...
]
```

`allow_credentials=False`: usamos Bearer token, no cookies. Sin cookies, CSRF clásico no aplica.

## Headers de seguridad

Caddy (proxy reverso) agrega headers en producción. Ver `Caddyfile` de la raíz del repo:

- `Strict-Transport-Security: max-age=31536000; includeSubDomains`
- `X-Frame-Options: DENY` (anti-clickjacking)
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: strict-origin-when-cross-origin`
- `Content-Security-Policy: ...` (configurado por-ruta — capa M-03)

El backend no setea estos headers; los pone Caddy.

## CSP (Content Security Policy) — M-03

Caddy setea CSP en respuestas HTML del frontend. Bloquea inline scripts, iframe embed, etc.

`/app/?demo=1` (el embed del IDE en la landing) tiene CSP relajado (permite iframe del SPA). Configuración por-ruta en `Caddyfile`.

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| Webhook → 400 "firma inválida" | `STRIPE_WEBHOOK_SECRET` distinto del configurado en dashboard de Stripe |
| Webhook llega 2 veces y aplica 2 cambios | `aplicar_evento_stripe` no recibe `webhooks` store (modo legacy sin idempotencia) |
| WS handshake → 403 | Origin no en `ORUX_WS_ORIGINS`. Agregar y reiniciar `orux` |
| Cliente nuevo no conecta tras agregar dominio | Cache de docker-compose: `docker compose up -d --force-recreate orux` |
| Replay de webhook no detectado | `webhooks.marcar` no se llama (verificar que `app.state.webhooks = PgWebhooksStore(db)`) |

Ver [`adapters/stripe.md`](../adapters/stripe.md), [`adapters/postgres.md`](../adapters/postgres.md) para el detalle de los stores.
