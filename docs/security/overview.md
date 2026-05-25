# Seguridad: overview

Modelo de amenazas y mitigaciones del backend de Orux. La filosofía: **defensa en profundidad sin convertir el código en una jungla de validaciones**. Cada validación tiene un BACKEND-AUDIT-XXXX asociado en los comentarios del código.

## Actores

| Actor | Capacidades | Confianza |
|---|---|---|
| Dev autenticado en su equipo | Lee/edita workspace, ve presencia de otros, propone cambios, commitea con su autor | Alta (es miembro del equipo) |
| Dev miembro de equipo ajeno | Aislado completamente — no ve nada del otro equipo | Confianza scopeada |
| Atacante con cuenta | Puede registrar, hacer rate-limit abuse, propuesta floodear, intentar takeover OAuth, intentar RCE por git | Bajo control |
| Atacante sin cuenta | Puede intentar registro/login bruto, escanear endpoints públicos | Bajo control (rate-limits, gates) |
| Operador de la plataforma | Panel admin: ver/borrar usuarios/teams, cambiar planes | Total |
| Stripe (webhooks) | Manda eventos firmados HMAC con `whsec_...` | Verificada por firma |

## Amenazas concretas y dónde se mitigan

### Identidad y sesión

| Amenaza | Mitigación | Doc |
|---|---|---|
| Robo de password en transit | HTTPS obligatorio en producción (Caddy TLS) | RUNBOOK.md |
| Token de sesión filtrado | `exp` (TTL 30 días default) + `epoch` por usuario (revocación quirúrgica) | [auth.md](auth.md) |
| Rotación del secret HMAC sin tirar sesiones | `kid` (key id) en payload + `usuario_de_token(secret: dict[kid, secret])` | [auth.md](auth.md) |
| Domain confusion HMAC (token sesión vs state OAuth) | Prefijo de dominio `b"orux-session\x00"` antes del HMAC | [auth.md](auth.md) |
| Brute force de password en login | Rate limit 3/min/IP + PBKDF2 600k iteraciones | [auth.md](auth.md) |
| Brute force de registro (creación de cuentas) | Rate limit 20/10min/IP | [auth.md](auth.md) |
| OAuth account takeover (`gh:<login>` colisiona con cuenta password) | Namespace `gh:` reservado en `validar_nuevo_usuario` | [oauth.md](oauth.md) |
| OAuth CSRF (callback inducido) | State HMAC firmado (`firmar_state`) + validación timing-safe | [oauth.md](oauth.md) |
| OAuth replay del state | Set efímero de states usados (`_state_consumir`) | [oauth.md](oauth.md) |
| OAuth open redirect | `_sanitizar_app_url`: rechaza URLs externas a `public_url` | [oauth.md](oauth.md) |

### Inputs del cliente

| Amenaza | Mitigación | Doc |
|---|---|---|
| Path traversal (`../etc/passwd`) | `path_seguro(p)` aplicado en el dispatch ANTES de tocar memoria/disco | [paths.md](paths.md) |
| Symlink dentro del workspace que escapa | `DiskStorage._destino` resuelve y verifica que cae bajo root | [paths.md](paths.md) |
| Filename con NUL / control chars / invisibles Unicode | Rechazado por `path_seguro` | [paths.md](paths.md) |
| Frame WebSocket gigante (DoS) | `MAX_FRAME_BYTES = 1MB` en codec | [domain/protocol.md](../domain/protocol.md) |
| Mensaje WS malformado (campos faltantes / tipos malos) | `validation.py` levanta `ProtocolError`; server ignora el mensaje |
| Workspace flood (50k+ archivos) | `MAX_ARCHIVOS`, `MAX_BYTES_TOTAL` con `WorkspaceLleno` | [domain/state.md](../domain/state.md) |
| Propuesta flood por usuario | `MAX_POR_AUTOR = 50` propuestas/autor/equipo | [domain/state.md](../domain/state.md) |
| Username inválido (XSS, lookalike) | `validar_nuevo_usuario`: ASCII alfanum + `._-`, sin prefijo reservado | [auth.md](auth.md) |
| Nombre de equipo (HTML, invisibles) | `validar_nombre_equipo`: sin `<>`, sin control, sin invisibles Unicode | [domain/teams.md](../domain/teams.md) |

### Git (la pieza más expuesta)

| Amenaza | Mitigación | Doc |
|---|---|---|
| RCE por URL maliciosa (`ext::sh -c ...`) | Allowlist positiva de schemes + `GIT_ALLOW_PROTOCOL` + `protocol.ext.allow=never` | [git.md](git.md) |
| RCE por CVE-2017-1000117 (URL con `-oProxyCommand`) | Regex SCP-like estricto (user/host sin opciones) | [git.md](git.md) |
| RCE por hooks del repo clonado | `core.hooksPath=/dev/null` + purga de `.git/hooks` post-clone | [git.md](git.md) |
| Exfiltración de secrets via hook leakeado | Env allowlist (no `**os.environ`); filtra `ORUX_*` / `STRIPE_*` / DSN | [git.md](git.md) |
| Token expuesto en `ps` (vía argv) | `GIT_ASKPASS` temporal — secret en env solamente | [git.md](git.md) |
| Token expuesto en `.git/config` | `origin` se setea SIN credenciales (askpass las pasa) | [git.md](git.md) |
| Token cacheado por git | `git -c credential.helper=` (vacío) | [git.md](git.md) |
| Anti-traversal en rename de clone | Solo movemos hijos cuyo `realpath` queda en `destino` real | [git.md](git.md) |
| URL local que escapa con `..` | `_url_segura` rechaza CUALQUIER `..` en URL local | [git.md](git.md) |
| Refspec malicioso (`rama --upload-pack=...`) | `_rama_segura`: regex `[A-Za-z0-9._/-]+`, sin `..`, no empieza con `-` | [git.md](git.md) |
| Mensaje de commit gigante (DoS) | Tope 8KB, rechaza `\x00`/`\n` en autor | [git.md](git.md) |
| Token leakeado en error de git | `_scrubear` reemplaza el token literal + URLs con cred embebidas | [git.md](git.md) |

### Webhooks (Stripe)

| Amenaza | Mitigación | Doc |
|---|---|---|
| Forgery: alguien que conoce la URL del webhook fuerza un upgrade | `verificar_firma_webhook` HMAC-SHA256 timing-safe | [webhooks.md](webhooks.md) |
| Replay de webhook viejo | Tolerancia 5min en `verificar_firma_webhook` + `webhooks.marcar(event_id)` | [webhooks.md](webhooks.md) |
| MITM con re-serialización del body | El body se lee en BYTES crudos (no re-serializar) | [webhooks.md](webhooks.md) |
| Webhook duplicado por reintento de Stripe | `PgWebhooksStore.marcar` con UPSERT atómico | [webhooks.md](webhooks.md) |

### Cross-origin (anti-CSRF para WS)

| Amenaza | Mitigación | Doc |
|---|---|---|
| Sitio malicioso abre WS al server desde el browser de la víctima | Whitelist de origins (`ORUX_WS_ORIGINS`) | [webhooks.md](webhooks.md) (sección Origins) |

### Concurrencia y race conditions

| Amenaza | Mitigación | Doc |
|---|---|---|
| TOCTOU al crear usuario (dos requests con mismo username) | Lock interno + `INSERT ... ON CONFLICT DO NOTHING RETURNING` | [auth.md](auth.md) |
| TOCTOU al redimir invitación (dos requests con mismo code) | Lock interno + `FOR UPDATE` en SQL | [domain/teams.md](../domain/teams.md) |
| Lost update al editar (dos handlers concurrentes con foto vieja) | `rt._estado_lock` por equipo en `_aplicar` | [adapters/websocket.md](../adapters/websocket.md) |
| Ajuste de asientos pisado entre dos miembros simultáneos | `_asientos_locks[team_id]` por equipo | [flows/billing.md](../flows/billing.md) |
| Carrera al construir TeamRuntime (dos handshakes simultáneos al mismo team) | `_rt_locks[team_id]` por team_id | [adapters/websocket.md](../adapters/websocket.md) |

### Almacenamiento en disco

| Amenaza | Mitigación | Doc |
|---|---|---|
| Otros usuarios del host leen `users.json` (PBKDF2 hashes) | `os.open(..., 0o600)` + chmod defensivo | [adapters/json-local.md](../adapters/json-local.md) |
| Archivo truncado por crash entre write y replace | `atomic_write` con tmp + `os.replace` + `fsync` | [adapters/json-local.md](../adapters/json-local.md) |
| `.tmp` huérfanos acumulados tras SIGKILL | Cleanup al boot (`DiskStorage._limpiar_tmps_huerfanos`) | [domain/state.md](../domain/state.md) |
| `~/.orux/secret` 0644 accesible | Crea con `os.open(O_CREAT \| O_EXCL, 0o600)` + dir 0700 | [auth.md](auth.md) |

## Compuertas opt-in

Tres servicios externos están **cerrados por defecto**. Sin las env vars correspondientes, el endpoint responde 503 ("no configurado") en vez de hacer nada a medias:

| Servicio | Var env | Sin la var |
|---|---|---|
| Panel admin (`/api/v1/admin/*`) | `ORUX_ADMIN_USER` + `ORUX_ADMIN_TOKEN` (HMAC secret) | 503 |
| OAuth GitHub (`/oauth/github/*`) | `ORUX_GH_CLIENT_ID` + `ORUX_GH_CLIENT_SECRET` + `ORUX_GH_REDIRECT` | 503 |
| Billing Stripe (`/api/v1/billing/*`) | `STRIPE_SECRET_KEY` + `STRIPE_WEBHOOK_SECRET` + `STRIPE_PRICE_*` | 503 |

Esto significa que un deploy "vanilla" sin estas vars NO expone vulnerabilidades por config incompleta — solo no tiene ese servicio.

## Lo que NO está protegido (limitaciones conocidas)

- **DDoS volumétrico**: los rate-limits son por IP, sin pesos. Un atacante con miles de IPs (botnet) puede agotar el server. Mitigación operativa: Caddy detrás de Cloudflare/proxy con DDoS protection.
- **Acción sostenida por usuario autenticado autorizado**: si un dev autenticado decide flood propuestas (sub-cap), no hay mitigación en el dominio — es responsabilidad del equipo del usuario (despedirlo).
- **Stripe Test Mode**: en producción usar Live Mode. El backend no diferencia (es responsabilidad del operador setear las keys correctas).
- **Réplicas múltiples del WS server**: el set efímero `_oauth_states_usados` y `MemWebhooksStore` (dev) NO se comparten entre procesos. Producción usa Postgres para webhooks; OAuth state es local.

## Auditoría continua

Cada decisión de seguridad lleva un identificador `BACKEND-AUDIT-XXXX` en los comentarios del código. Permite trazar el cambio histórico (`git log -S "BACKEND-AUDIT-0234"`) y entender el contexto.

Códigos vistos en este overview: 0001 (TTL legacy), 0002 (epoch revocación), 0008 (charset username), 0013 (perms 0600), 0015 (state TTL 120s), 0022 (kid rotación), 0023 (domain separation), 0024 (username vacío en token), 0026 (TOCTOU registrar), 0029 (exp no-bool), 0064 (tmp con uuid), 0066 (path peligroso al cargar), 0070 (workspace topes), 0071/0238 (proposals topes), 0076 (anti-symlink), 0152 (env filter), 0153 (hooks purge), 0154/0155 (tmpdir hermano), 0156 (URL allowlist), 0157 (anti-traversal rename), 0158 (commit msg topes), 0159 (timeout split), 0161 (URL scrub), 0162 (DB ping), 0163 (rate-limit login 3/min), 0177 (diff ownership), 0178 (atomic UPSERT user), 0179 (id retry cap), 0181 (lock check-then-set), 0183 (INF int), 0205 (root resolve), 0214 (invite TTL), 0220 (rt lock), 0224 (cap registro), 0229 (clone tmp cleanup), 0230 (clone size), 0231 (rename guard vacío), 0236 (tmp filter), 0237 (invite lock), 0263 (timeout clamp), 0267 (dir 0700), 0287 (secret race), 0290 (secret divergence log), 0292 (git not found log), 0293 (signal handler), B-08 (Docker pinear digest), M-04 (XFF proxy trust).

Más de 50 BACKEND-AUDITs documentados. El que vea uno en un comentario y quiera contexto: `git log -S "BACKEND-AUDIT-XXXX" --oneline`.
