# Seguridad: autenticación

Detalle de las defensas del sistema de identidad: passwords, tokens, rate limits, revocación.

## Password hashing

`hash_password(plain) -> str` (PBKDF2-HMAC-SHA256):

- **600.000 iteraciones** (OWASP 2023+).
- **Sal aleatoria de 32 bytes** por password.
- Formato `pbkdf2_sha256$600000$<sal_b64>$<hash_b64>`.

**Tamaño validado al hashear** (no al verificar — cuentas viejas que no cumplen siguen funcionando):

- `len(plain) < 8`: rechazado (OWASP).
- `len(plain) > 128`: rechazado (DoS preventivo — PBKDF2 sobre 10MB cuesta minutos de CPU).

`verificar_password(plain, registro)` usa `hmac.compare_digest` (timing-safe). Rechaza si:

- Registro corrupto (formato inválido).
- Registro es `MARCADOR_EXTERNO` (cuentas OAuth: no se puede entrar por contraseña).

## Tokens de sesión HMAC

Formato: `<payload_b64>.<hmac_hex>`. Payload JSON: `{user, epoch, exp?, kid?}`.

### Firma con domain separation (BACKEND-AUDIT-0023)

```python
_DOMAIN_SESSION = b"orux-session\x00"

def _firma(payload_b64, secret):
    msg = _DOMAIN_SESSION + payload_b64.encode("ascii")
    return hmac.new(secret.encode("utf-8"), msg, sha256).hexdigest()
```

**Por qué**: el mismo secret puede estar compartido entre contextos (sesión + OAuth state). Sin prefijo, una firma del state CSRF (`<ts>.<hmac>`) podría pasar por la del token de sesión (`<payload>.<hmac>`) si el payload b64 casualmente equivale a un ts numérico. Imposible en práctica, pero defensa en profundidad.

El byte `\x00` es separador imposible en payload b64.

**Compat legacy** (`_firma_legacy`): tokens emitidos antes del fix se siguen aceptando (loguea warning). Cuando el parque rote, se puede eliminar.

### `exp` (expiración) (BACKEND-AUDIT-M1)

`crear_token(user, secret, ttl_seg=ttl)` agrega `exp = int(now + ttl)`.

`usuario_de_token` rechaza si `time.time() >= exp`.

Default operativo: `ORUX_TOKEN_TTL_SEC=2592000` (30 días). Clamp 0-365 días.

`exp` debe ser **`int` estricto**, NO `bool`, NO `float` (BACKEND-AUDIT-0029). Un atacante con la firma podría intentar `exp=inf` o `exp=True` (= 1) para que el chequeo `time.time() >= exp` se comporte raro.

Tokens sin `exp` se ACEPTAN con warning ("token aceptado sin exp para usuario=X, legacy"). Razón: degradar es la única forma de no tumbar sesiones vivas. Cuando los nuevos `ttl_seg` rotan, el legacy desaparece.

### `epoch` por usuario (BACKEND-AUDIT-0002)

`UserStore` lleva un contador por usuario. `crear_token(user, secret, epoch=N)` lo embebe en el payload.

`usuario_de_token(token, secret, *, epoch_de)` chequea `tok_epoch >= epoch_de(user)`. Si el actual es mayor, rechaza.

`UserStore.revocar_sesiones(user)` incrementa el epoch sin tocar password. Casos de uso:

- Cambio de password.
- Sospecha de fuga (operador llama desde el panel).
- Logout-all desde el cliente (futuro).

Sin epoch, revocar una sesión filtrada obligaba a rotar el secret global → tira TODAS las sesiones del sistema.

`tok_epoch` también debe ser `int` estricto (no `bool`).

### `kid` (key id) — rotación atómica del secret (BACKEND-AUDIT-0022)

`usuario_de_token` acepta `secret` como `dict {kid: secret}`. Selecciona por `kid` del payload; cae a `"current"` si no hay match.

Workflow de rotación:

1. Estado normal: server arranca con `secret = "K1"`. Tokens nuevos llevan `kid: "K1"`.
2. Inicio rotación: server arranca con `secret = {"current": "K2", "K1": "K1"}`. Tokens nuevos llevan `kid: "K2"`; los viejos con `kid: "K1"` siguen validando.
3. Tras TTL del más viejo (30 días): `secret = {"current": "K2"}`. Tokens K1 dejan de validar (ya vencieron por TTL igual).

Sin `kid`, rotar el secret requiere coordinación: o tirás todas las sesiones, o aceptás ventana de N días donde no podés cambiar el secret aunque haya fuga.

## Username y validación

`normalizar(username) = username.strip().lower()`. Aplica SIEMPRE (registro, login, comparaciones).

**Garantía**: `Joaquin`, `joaquin`, ` JOAQUIN ` son **el mismo usuario** para el ownership. Sin esto, alguien que escribe "Joaquin" en su username Y tu archivo dice "owner: joaquin" → confusión persistente.

### `validar_nuevo_usuario` (solo al registrar)

Reglas duras solo al crear; cuentas viejas que no cumplen siguen funcionando.

| Regla | Por qué |
|---|---|
| 2-32 chars | Cabe en UI, no es 1-char ambiguo |
| ASCII alfanumérico + `._-` | Sin lookalikes (`+`, `@` removidos por BACKEND-AUDIT-0008) |
| No empieza con `._-` | Convención clara |
| No prefijo `gh:` | Namespace reservado (ver siguiente) |

### Prefijo `gh:` reservado (anti-takeover OAuth)

Si el registro es público Y la identidad OAuth usa el login pelado:

```
1. Atacante: register("torvalds", "password_atacante")
2. Verdadero torvalds entra por OAuth GitHub
3. Server: asegurar_externo("torvalds") → "ya existe" → token para torvalds
4. Verdadero torvalds cae en la cuenta cuya password el atacante conoce
```

**Mitigación**: el OAuth crea cuentas con prefijo `gh:torvalds`. `validar_nuevo_usuario` RECHAZA registrar usernames con `gh:`. Las identidades OAuth y las de contraseña viven en espacios disjuntos garantizados.

### `asegurar_externo` (OAuth)

```python
def asegurar_externo(self, username):
    u = normalizar(username)
    if len(u) > _USUARIO_GH_MAX:  # 42 = 39 GitHub max + 3 ('gh:')
        raise ValueError("usuario externo demasiado largo")
    cuerpo = u[len("gh:"):] if u.startswith("gh:") else u
    for c in cuerpo:
        if c not in _USUARIO_CHARS:
            raise ValueError("usuario externo con caracteres no permitidos")
    with self._lock:
        if u not in self._usuarios:
            self._usuarios[u] = {"hash": MARCADOR_EXTERNO, "epoch": 0}
    return u
```

Defiende contra un identifier externo manipulado (BACKEND-AUDIT-0009): aunque GitHub manda solo logins legítimos, validamos por defensa en profundidad.

## Rate limits

| Ventana | Tope | Endpoint | Env override |
|---|---|---|---|
| 10 min/IP | 20 | `Register` WS | `ORUX_REGISTRO_MAX_POR_IP` |
| 1 min/IP | 3 | `Login` WS (post-Sprint G, antes 5) | n/a |
| 1 min/IP | 3 | `POST /api/v1/login` HTTP | n/a |
| 1 min/IP | 60 | `POST /api/v1/errors` HTTP | n/a |
| 1 min/IP | 30 | `POST /api/v1/track` HTTP | n/a |

**Ventana deslizante** (no bucket fijo): mantiene `dict[ip, list[timestamps]]`, limpia perezoso, descarta entradas con bucket vacío O cuyo registro más nuevo venció la ventana.

```python
def _throttle(buckets, ip, tope, ventana):
    ahora = time.monotonic()
    corte = ahora - ventana
    bucket = buckets.setdefault(ip, [])
    bucket[:] = [t for t in bucket if t > corte]
    if len(bucket) >= tope:
        return False
    bucket.append(ahora)
    # GC perezoso si > 10k IPs
    if len(buckets) > 10_000:
        for k in [k for k, v in buckets.items() if not v or v[-1] <= corte]:
            buckets.pop(k, None)
    return True
```

GC pesado (cada N ops) NO solo de vacíos, sino de obsoletos (último timestamp < corte): si solo borrara vacíos, un atacante rotando 10k IPs con un goteo las mantiene no-vacías y el dict crece sin control.

## Rate limit cap del registro

```python
async def _autenticar(self, websocket, ip):
    if mensaje_type == "register":
        if not self._throttle_registro(ip):
            return None  # AuthError "rate_limit"
        if len(await self.users.usuarios()) >= MAX_USUARIOS_PLATFORMA:
            return None  # AuthError "registro_cerrado"
```

Cap absoluto de usuarios en la plataforma (env `ORUX_MAX_USUARIOS`, default 10000). Si se rebasa, registros nuevos se bloquean (BACKEND-AUDIT-0224). El operador del VPS gestiona.

## XFF (X-Forwarded-For) trust (BACKEND-AUDIT M-04)

El server WS está detrás de Caddy. La IP real del usuario va en `X-Forwarded-For`; el peer TCP es el contenedor Caddy.

**Confiamos en XFF SOLO cuando el peer TCP es un proxy de confianza** (red privada / loopback de Docker compose). Antes, cualquier conexión que mandara XFF podía pisar la IP usada para los buckets — un atacante con acceso directo al contenedor (mal config, pod vecino comprometido, port forward olvidado) rotaba el XFF y evadía el rate-limit.

```python
def ip_cliente(websocket):
    socket_ip = ...  # del socket
    if ip_proxy_confiable(socket_ip):
        xff = websocket.request.headers.get("X-Forwarded-For", "")
        if xff:
            return xff.split(",")[0].strip()
    return socket_ip or "desconocida"
```

Ese atacante ahora queda fijado a la IP del socket (su propia IP) — no puede evadir el rate-limit rotando un header.

## Secreto del server (`~/.orux/secret`)

Generación + persistencia:

```python
def _secreto(base):
    env = os.environ.get("ORUX_SESSION_SECRET", "").strip()
    f = base / "secret"
    
    if env and f.exists():
        try:
            del_archivo = f.read_text().strip()
            if del_archivo and del_archivo != env:
                logger.warning(  # BACKEND-AUDIT-0290
                    "ORUX_SESSION_SECRET difiere del archivo %s: "
                    "los tokens firmados antes de este boot dejaron de valer", f,
                )
        except OSError as e:
            logger.warning("no se pudo leer %s: %s", f, e)  # BACKEND-AUDIT-0292
    
    if env: return env
    if f.exists():
        try:
            return f.read_text().strip()
        except OSError as e:
            raise SystemExit(f"no se pudo leer el secreto de firma {f}: {e}")
    
    # Generar nuevo + atomico
    base.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        os.chmod(base, 0o700)  # BACKEND-AUDIT-0267
    except OSError as e:
        logger.warning("no se pudo chmod 0700 a %s: %s", base, e)
    
    s = token_hex(32)
    try:
        fd = os.open(f, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        # BACKEND-AUDIT-0287: race con otro proceso arrancando
        return f.read_text().strip()
    try:
        os.write(fd, s.encode())
    finally:
        os.close(fd)
    return s
```

Decisiones:

- **Prioridad env > archivo**: el env existe para OAuth (proceso `api` y `orux` comparten secret). Sin env: archivo (modo dev).
- **Divergencia env vs archivo**: log warning ALTO. El operador debe notar que cambió el secret y los tokens viejos no validan.
- **`O_EXCL`**: race entre dos procesos arrancando simultáneamente. El primero crea; el segundo lee lo que el primero escribió.
- **Permisos 0600 + dir 0700**: nadie más lee el secret. `chmod` defensivo (algunos FS no soportan; loguea pero no aborta).

## Auth del operador (panel admin)

Antes: un único `ORUX_ADMIN_TOKEN` que el cliente MANDABA en cada request. Secreto compartido viajando por red, sin identidad por cuenta, sin rotación.

Ahora: el operador es una CUENTA ya registrada (env `ORUX_ADMIN_USER`); entra con su username + contraseña normales (PBKDF2). El server emite token HMAC de sesión con TTL 8h (turno de oficina).

```python
async def login_operador(users, admin_user, secret, username, password, *, ttl_seg=8*3600):
    if not admin_user or not secret:
        return None
    if normalizar(username) != normalizar(admin_user):
        return None  # no es el operador
    if not await users.verificar(username, password):
        return None  # password mala
    return crear_token(normalizar(username), secret, ttl_seg=ttl_seg)
```

`operador_de_token(token, admin_user, secret)`: valida firma HMAC + que el `user` del payload sea el `admin_user`. Sync (verificar firma no toca IO).

`_gate(req)` envuelve todo el panel `/api/v1/admin/*`:

- Sin `ORUX_ADMIN_USER` o `ORUX_ADMIN_TOKEN` (secret): 503.
- Sin Bearer válido: 401.
- OK: deja pasar.

## Topes adicionales

- **`MAX_USUARIOS_PLATFORMA`** (env, default 10000): cap absoluto de usuarios. Tope operativo.
- **Topes propuestas/workspace**: ver [`flows/edit-and-coordinate.md`](../flows/edit-and-coordinate.md).
- **Topes git**: ver [`security/git.md`](git.md).

## Lecciones generales

1. **Defensa en profundidad**: si una capa falla, otra atrapa. Ejemplo: las URL del cliente pasan por (1) allowlist regex, (2) `GIT_ALLOW_PROTOCOL`, (3) `protocol.ext.allow=never`. Cualquiera sola es insuficiente.
2. **Degradación silenciosa = invisible en producción**. Si una defensa falla, hay que LOGUEAR la razón exacta (ver `arrancar_lsp`, ver `_secreto`, ver `_es_admin_o_logear`).
3. **Tipos estrictos en payloads**: `isinstance(v, int) and not isinstance(v, bool)` cuando `int` es lo esperado. Bool es subtype de int en Python.
4. **Timing-safe siempre que se compara con un secret**: `hmac.compare_digest`, no `==`.
5. **Validación en la FRONTERA del mensaje**, no solo al escribir. Un path inseguro no debe entrar al estado en memoria ni difundirse.
