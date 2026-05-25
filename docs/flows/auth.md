# Flow: Autenticación

Tres caminos para que un dev quede autenticado: registro/login con password, OAuth GitHub, o reconexión con token de sesión.

Todos terminan emitiendo el **mismo token HMAC de sesión** que el server WS verifica. La maquinaria del WS (lobby → equipo) es byte-idéntica entre los tres orígenes.

## 1. Registro con password (cuenta nueva)

```
Cliente IDE                   Server WS (8765)              UserStorePort
─────────                     ─────────────                 ─────────────
  │                                │                              │
  │── ws://host:8765 ─────────────→│                              │
  │                                │ (valida Origin, IP rate-limit)
  │                                │                              │
  │── RegisterMessage ────────────→│                              │
  │    {username, password}        │                              │
  │                                │── existe(u) ─────────────────→│
  │                                │←─── False ───────────────────│
  │                                │── registrar(u, password) ────→│
  │                                │   (PBKDF2 + sal + lock TOCTOU)│
  │                                │←─── "username" (normalizado) ──│
  │                                │                              │
  │                                │ (crear_token: ttl_seg=30días) │
  │                                │                              │
  │←── AuthOkMessage ──────────────│                              │
  │    {client_id, name, token}    │                              │
```

`registrar` falla con `ValueError` si:

- Username ya existe.
- Username no pasa `validar_nuevo_usuario` (longitud, charset, prefijo reservado).
- Password no pasa `hash_password` (vacía / corta <8 / larga >128).

El server traduce a `AuthErrorMessage{code, mensaje}` legible.

**Rate limit**: 20 registros por IP en 10 min (env `ORUX_REGISTRO_MAX_POR_IP`). El registro es PÚBLICO y el backoff por-conexión no lo frena: un bot que hace connect → register → disconnect arranca cada conexión con 0 fallos.

## 2. Login con password (cuenta existente)

Mismo flujo, mensaje `LoginMessage{username, password}` en lugar de Register. El server hace `users.verificar(u, p)` (compara PBKDF2 timing-safe).

**Rate limit**: 3 logins fallidos por IP por minuto (BACKEND-AUDIT-0163, Sprint G — bajado de 5).

## 3. Reconexión con token de sesión

```
Cliente IDE                   Server WS
─────────                     ─────────
  │── ws://... ──────────────→│
  │                            │
  │── SessionMessage ─────────→│
  │    {token}                 │
  │                            │
  │                            │ usuario_de_token(token, secret, epoch_de=users.epoch)
  │                            │   1. parsea payload.firma
  │                            │   2. verifica HMAC + domain separator
  │                            │   3. verifica exp (si está)
  │                            │   4. verifica epoch >= users.epoch(user)
  │                            │                            
  │                            │ si OK:
  │←── AuthOkMessage ──────────│
  │    {client_id, name, token}│  ← rehidrata token (mismo si válido, nuevo si rotó)
  │                            │
  │ si NO OK:
  │←── AuthErrorMessage ───────│ {code: "token_inválido"}
```

El cliente guarda el token en localStorage. Al volver al SPA (refresh, nueva pestaña), prueba `SessionMessage` antes de mostrar login.

## 4. OAuth GitHub

Proceso aparte del WS — corre en el contenedor `api` (puerto 8800 → Caddy proxy → `https://orux.space`).

```
Navegador                    Server HTTP                  GitHub                    Server WS
─────────                    ───────────                  ──────                    ─────────
  │                              │                          │                          │
  │── click "Entrar con GH" ────→│                          │                          │
  │                              │ firmar_state(secret)     │                          │
  │                              │ → CSRF token             │                          │
  │←──── 302 + Location ─────────│                          │                          │
  │      https://github.com/...  │                          │                          │
  │                              │                          │                          │
  │── GET /login/oauth/auth ────────────────────────────────→│                          │
  │      ?state=... &scope=...                              │                          │
  │                              │                          │                          │
  │ (usuario aprueba en GitHub) ─────────────────────────────│                          │
  │                              │                          │                          │
  │←─── 302 + ?code=... ─────────────────────────────────────│                          │
  │      &state=...              │                          │                          │
  │                              │                          │                          │
  │── GET /oauth/github/callback→│                          │                          │
  │      ?code=... &state=...    │                          │                          │
  │                              │                          │                          │
  │                              │ validar_state(state) ✓   │                          │
  │                              │ _state_consumir(state) ✓ │                          │
  │                              │                          │                          │
  │                              │── POST /access_token ────→│                          │
  │                              │←──── {access_token}──────│                          │
  │                              │── GET /api/user ─────────→│                          │
  │                              │←──── {login: "torvalds"}─│                          │
  │                              │                          │                          │
  │                              │ identidad_github(perfil) │                          │
  │                              │ → "gh:torvalds"          │                          │
  │                              │ users.asegurar_externo() │                          │
  │                              │ crear_token(usuario, secret, ttl_seg=30d)            │
  │                              │                          │                          │
  │←─── 302 + Location ──────────│                          │                          │
  │      /app/#oauth=ok&token=...│                          │                          │
  │                              │                          │                          │
  │ (SPA lee el hash, guarda)    │                          │                          │
  │── ws://host:8765 ──────────────────────────────────────────────────────────────────→│
  │── SessionMessage{token} ────────────────────────────────────────────────────────────→│
  │←── AuthOkMessage ─────────────────────────────────────────────────────────────────────│
```

**Decisión load-bearing**: el token HMAC que emite el callback HTTP es **idéntico** al que emite el WS. Mismo secret (`ORUX_SESSION_SECRET` env compartido entre `api` y `orux` contenedores), mismo formato, misma verificación. Toda la maquinaria del WS queda sin cambios. Cero protocolo nuevo.

### Anti-CSRF (state firmado)

`firmar_state(secret, ahora?) -> "<ts>.<hmac>"`. Stateless: no se guarda nada en el server.

`validar_state(state, secret, max_edad=120, ahora?)`:

- Verifica firma timing-safe.
- Verifica `0 <= (now - ts) <= 120s` (vencido o "del futuro" = rechazado).

Sin esto, un atacante puede iniciar el flujo OAuth desde otro sitio y forzar a la víctima al callback con su propio `code`.

### Anti-replay del state (BACKEND-AUDIT-0015)

`_state_consumir(state, ahora)`: set local del proceso de states ya consumidos. La firma sigue siendo válida 120s después; si alguien intercepta el callback, podría reusarlo durante esa ventana.

GC perezoso (>1024 states → barre los >300s).

INVARIANTE: `_state_consumir` es 100% sync (sin `await`). El patrón "check si está, agregar si no" es atómico dentro de un mismo proceso CPython. Si entra un `await` adentro, hay que añadir lock o externalizar a Postgres.

### Namespace `gh:<login>` (anti-takeover)

La identidad OAuth lleva prefijo `gh:`. Sin esto, si un atacante pre-registra con password el username `torvalds`, cuando el verdadero `torvalds` entre por GitHub caería en la cuenta cuya password el atacante conoce.

`identidad_github` SIEMPRE devuelve `gh:<login>`. `validar_nuevo_usuario` RECHAZA registrar usernames con prefijo `gh:`. Espacios disjuntos garantizados.

## 5. Lobby

Tras AuthOk (cualquier camino), el server manda `LobbyMessage{equipos}`:

```python
equipos = await teams.equipos_de(usuario)
# [{id, nombre, rol, plan, miembros}, ...]
```

El cliente muestra el Hub: lista de equipos del usuario. Cuatro opciones:

1. **Crear equipo** (`CreateTeamMessage{nombre}`) — quedo como admin.
2. **Redimir invitación** (`RedeemInviteMessage{code}`) — me uno como member (chequea TTL, plan, etc.).
3. **Seleccionar** (`SelectTeamMessage{team_id}`) — entro a uno del que ya soy miembro.
4. **Salir** (cerrar conexión).

Tras `Create/Redeem/Select`: server responde `TeamReadyMessage{team_id, nombre, rol}` y entra al handshake de equipo.

## Cierre de sesión

`LeaveMessage` (del cliente) o close del websocket: el server limpia presencia (`Roster.quitar`), borra propuestas del autor (`Proposals.drop_author`), notifica a los demás presentes.

**El ownership NO se libera**: el dueño sigue siendo dueño aunque cierre la pestaña. Vuelve a entrar y recupera su zona.

## Revocación de sesión

Tres formas:

1. **Token vencido** (`exp`): el cliente vuelve a ver login. Por default a los 30 días.
2. **Cambio de password**: `UserStore.cambiar_password` incrementa `epoch`. Los tokens viejos llevan `epoch` viejo → rechazados.
3. **`UserStore.revocar_sesiones(user)`**: incrementa `epoch` sin cambiar password. Para revocar manualmente.

Ver [`security/auth.md`](../security/auth.md) para el detalle.

## Diagnóstico

| Síntoma | Causa probable |
|---|---|
| `AuthErrorMessage{code: "credenciales"}` | Username/password inválidos. Sin filtrar cuál falló (no decimos "el username existe pero la password no"). |
| `AuthErrorMessage{code: "username_invalido"}` | No pasa `validar_nuevo_usuario` (longitud, charset, gh:). |
| `AuthErrorMessage{code: "rate_limit"}` | IP supera 20 registros/10min o 3 logins/1min. Reintentar más tarde. |
| `AuthErrorMessage{code: "token_invalido"}` | Token vencido, firma inválida, o sesión revocada. Volver a login. |
| OAuth: `_volver(error="state")` | State CSRF inválido/vencido/replay. Reintentar el flujo. |
| OAuth: `_volver(error="github")` | El intercambio code→token falló (rate limit GitHub, app deshabilitada, token expirado). Revisar logs del proceso `api`. |
| OAuth: `_volver(error="cancelado")` | Usuario canceló el consentimiento en GitHub. |

Los logs del WS van a stdout del contenedor `orux`; los del HTTP al contenedor `api`. `docker compose logs orux api | grep -iE 'auth|login|oauth'`.
