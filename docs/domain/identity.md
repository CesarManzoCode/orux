# Domain: identity

`backend/orux/domain/identity/` modela la identidad: usuarios, contraseñas, tokens de sesión, OAuth.

Es puro: passwords + tokens + OAuth son funciones puras de stdlib (HMAC, PBKDF2, hashlib). La persistencia de usuarios (`UserStore`) es memoria pura sync; los adapters (JSON local, Postgres) la envuelven.

## Archivos

| Archivo | Qué hace |
|---|---|
| `passwords.py` | `hash_password(plain)` (PBKDF2 + sal aleatoria) + `verificar_password(plain, hash)`. |
| `store.py` | `UserStore` (memoria pura), `normalizar`, `validar_nuevo_usuario`. |
| `tokens.py` | `crear_token(user, secret, ttl_seg, *, epoch, kid)` + `usuario_de_token(token, secret, *, epoch_de)`. |
| `oauth.py` | `firmar_state(secret)`, `validar_state`, `url_autorizacion(...)`, `identidad_github(perfil)`. |

## Passwords (PBKDF2)

`hash_password(plain) -> str`:

- PBKDF2-HMAC-SHA256, 600.000 iteraciones (OWASP 2023+).
- Sal aleatoria de 32 bytes.
- Formato: `pbkdf2_sha256$600000$<sal_b64>$<hash_b64>`.
- Valida tamaño: rechaza `""` (vacía), `<8` (muy corta), `>128` (DoS preventivo).

`verificar_password(plain, registro) -> bool`:

- Parsea el formato del registro y compara con `hmac.compare_digest` (timing-safe).
- Rechaza si el registro está corrupto.
- Rechaza si el registro es `MARCADOR_EXTERNO` (cuentas OAuth: no se puede entrar por contraseña).

`MARCADOR_EXTERNO = "external:no-password"` — registro especial para cuentas creadas vía OAuth. Garantiza que `verificar_password(X, MARCADOR_EXTERNO)` siempre devuelve `False`.

## `UserStore`

```python
class UserStore:
    def __init__(self, inicial: dict[str, object] | None = None): ...
    def existe(self, username: str) -> bool: ...
    def registrar(self, username: str, password: str) -> str:
        # Devuelve username normalizado. Levanta ValueError si ya existe.
    def asegurar_externo(self, username: str) -> str:
        # Idempotente. Para OAuth: crea con MARCADOR_EXTERNO si no existe.
    def admin(self) -> str | None:
        # El primer usuario registrado. Capa 12 legacy.
    def usuarios(self) -> list[str]:
        # Ordenado alfabético.
    def epoch(self, username: str) -> int:
        # Contador de sesiones (revocación).
    def revocar_sesiones(self, username: str) -> None:
        # Incrementa epoch.
    def cambiar_password(self, username: str, password: str) -> bool:
        # Nueva password + revoca sesiones.
    def verificar(self, username: str, password: str) -> bool: ...
```

Memoria pura sync con `threading.Lock` para tramos check-then-set (BACKEND-AUDIT-0026 TOCTOU).

### Normalización

`normalizar(username) = username.strip().lower()`. Garantiza que `Joaquin`, `joaquin`, `JOAQUIN`, ` Joaquin ` son **el mismo usuario** para el ownership.

### Validación al registrar (`validar_nuevo_usuario`)

Reglas DURAS solo al crear; cuentas viejas que no cumplen siguen funcionando.

| Regla | Rationale |
|---|---|
| 2-32 chars | Cabe en UI sin truncar, no es 1-char ambiguo |
| ASCII alfanumérico + `._-` | Sin lookalikes (`+`, `@` removidos por BACKEND-AUDIT-0008) |
| No empieza con `._-` | Convención (debe empezar con letra/número) |
| No prefijo `gh:` reservado | Critical: ver más abajo |

### Prefijo `gh:` reservado (anti-takeover OAuth)

Si el registro con password es público y el OAuth crea cuentas con login pelado, un atacante puede pre-registrar con password el nombre `torvalds` y, cuando el verdadero `torvalds` entre por GitHub, caer en la cuenta cuya password el atacante conoce.

**Mitigación**: el identifier OAuth lleva namespace `gh:`. Las identidades OAuth y las de contraseña viven en espacios disjuntos. `validar_nuevo_usuario` rechaza explícitamente `gh:*` al registrar.

## Tokens de sesión (HMAC)

`crear_token(user, secret, ttl_seg, *, epoch, kid) -> str`:

Formato: `<payload_b64>.<hmac_hex>`. Payload es JSON ordenado: `{user, epoch, exp?, kid?}`.

```python
crear_token("ana", "s3cr3t", ttl_seg=2592000, epoch=0)
# -> "eyJlcG9jaCI6MCwiZXhwIjoxNzE5OTk5OTk5LCJ1c2VyIjoiYW5hIn0.a1b2c3..."
```

`usuario_de_token(token, secret, *, epoch_de) -> str | None`:

- Parsea `<payload>.<firma>`.
- Recomputa la firma con `hmac.new(secret, _DOMAIN_SESSION + payload, sha256)`.
- Compara timing-safe con `hmac.compare_digest`.
- Valida `exp` (si está) — token vencido = rechazado.
- Si se pasa `epoch_de`, valida `tok_epoch >= epoch_actual(user)` — sesión revocada = rechazado.
- Devuelve `user` si todo OK, `None` en cualquier otro caso.

### Robustez crítica (cada item con su BACKEND-AUDIT)

**`exp` (expiración)** (M1):
Tokens sin `exp` se ACEPTAN con warning (legacy compat); cuando el parque rote bajo `ttl_seg`, esto deja de ocurrir.
Default `ttl_seg = 30 días` (env `ORUX_TOKEN_TTL_SEC`, clamp 0-365 días).

**`epoch` (revocación quirúrgica)** (BACKEND-AUDIT-0002):
El `UserStore` lleva un contador por usuario. `revocar_sesiones(user)` incrementa. Los tokens viejos llevan el epoch del momento; cuando el actual es mayor, no valen. Sin esto, revocar una sesión filtrada obligaba a rotar el secret global (tira TODAS las sesiones).

**`kid` (rotación atómica del secret)** (BACKEND-AUDIT-0022):
`usuario_de_token` acepta `secret` como `dict {kid: secret}`. Selecciona por `kid` del payload; cae a "current" si no hay match. Durante la rotación, ambos secrets validan; cuando los tokens viejos vencen, se descarta el viejo.

**Domain separation HMAC** (BACKEND-AUDIT-0023):
La firma incluye prefijo `b"orux-session\x00"`. Sin esto, si el mismo secret se compartiera entre contextos (token de sesión + state CSRF de OAuth), una firma de un contexto podría pasar por la del otro. El byte 0 es separador imposible en payload b64.

**`username` vacío** (BACKEND-AUDIT-0024):
`crear_token` lo rechaza ahora (antes el productor lo aceptaba y el verificador lo rechazaba; loop infinito posible). 

**`exp` no entero estricto** (BACKEND-AUDIT-0029):
`exp` debe ser `int`, no `float`, no `bool`. Un atacante con la firma podría intentar `exp=inf`.

## OAuth GitHub

`oauth.py` tiene **lógica pura, sin red**. La parte que habla con GitHub (intercambiar code por access token, leer perfil) vive en la cáscara HTTP (`adapters/inbound/http/app.py:_intercambiar`).

### `url_autorizacion(client_id, redirect_uri, state, scope)`

Pura (solo arma la query). El `state` CSRF se valida en el callback.

```python
URL_AUTORIZA = "https://github.com/login/oauth/authorize"
SCOPE = "read:user user:email"  # mínimo, sin repo
```

### `firmar_state(secret, ahora?) -> str`

Token CSRF stateless. Formato `<ts>.<hmac>`. No se guarda nada en el server: la validez se prueba con la firma + antigüedad.

### `validar_state(state, secret, max_edad=120, ahora?) -> bool`

- Verifica firma timing-safe.
- Verifica `0 <= (ahora - emitido) <= max_edad`.
- Rechaza state vencido (>120s) o "del futuro" (reloj manipulado).

**Defensa adicional contra replay** (BACKEND-AUDIT-0015): el caller (`api/app.py:_state_consumir`) mantiene un set efímero de states ya usados durante la ventana de validez. Sin esto, alguien que intercepta el callback puede reusarlo durante 120s.

### `identidad_github(perfil) -> str`

```python
identidad_github({"login": "Torvalds"})  # → "gh:torvalds"
```

Prefijo `gh:` + login normalizado. Levanta `ValueError` si el perfil no trae un login usable.

**Decisión load-bearing**: usar el `login` (mutable) y NO el `id` numérico (estable). El `id` sería más robusto ante renames, pero rompería la legibilidad en presencia/commits y los renames de handle son raros — decisión consciente.
