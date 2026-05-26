# Auditoría de seguridad de Orux

**Fecha:** 2026-05-25
**Estado:** **REMEDIACIÓN COMPLETA — 2026-05-26.** Bloques 1, 2 y 3 aplicados, autor_git OAuth fix, 541 tests verdes (subió de 513 → 541). Detalle abajo en sección [Estado de remediación](#estado-de-remediación-2026-05-26).
**Próxima sesión:** validar manualmente en VPS (rotar password Postgres, smoke test, npm install para fontsource).

---

## Cómo retomar mañana

1. Leer la sección [Resumen ejecutivo](#1-resumen-ejecutivo) (1 min).
2. Mirar [Conteo final](#conteo-final) y la [Tabla de hallazgos priorizada](#tabla-de-hallazgos-priorizada-vista-rápida) (2 min).
3. Decidir las 3 preguntas abiertas:
   - **Rama:** `security/audit-2026-05-25` o `main`?
   - **Alcance:** Bloque 1 solamente, o Bloque 1+2 sin pausa?
   - **Diferidos:** ¿algún hallazgo a no tocar (e.g. mantener `prismjs ^1.30.0`, postponer auto-host Google Fonts)?
4. Confirmar con: *"sí, aplicá Bloque 1 en rama X, diferir Y"*.
5. Yo aplico los cambios del [Bloque 1](#corregir-inmediatamente-bloque-1) (5 fixes, ~30 min) y corro `pytest`.
6. Tras revisar tus diffs, decidir si seguir con Bloque 2.

### Contexto del trabajo de ayer

- 6 sub-agentes especializados auditaron (auth, HTTP API, WebSocket, persistencia/git, frontend IDE, landing/admin) + revisión directa de Docker/Caddy/scripts/dependencias.
- Lectura completa de >50 archivos clave (no solo grep): tokens.py, oauth.py, passwords.py, sync.py, dispatch.py, validation.py, paths.py, storage.py, git/binary.py, postgres/teams.py, postgres/stores.py, http/app.py, billing.py, stripe_client.py, store.ts, error-reporter.ts, App.tsx (landing+IDE), admin.html, Dockerfile, Caddyfile, docker-compose.yml, scripts/.
- `git log --all -p -- .env` confirma que `.env` NUNCA fue commiteado (bien).
- Ningún secreto en historial git.

---

## 1. Resumen ejecutivo

**Estado general:** Sólido. El backend de Orux ha pasado por ~300 ciclos de hardening documentados (`BACKEND-AUDIT-XXXX`) y muestra disciplina de seguridad notable: PBKDF2-SHA256 600k, HMAC con domain separation, validación estricta de paths, allowlist de URLs/protocolos git, env scrubbing en subprocesses, security headers + CSP por-ruta, rate limiting multi-capa, idempotencia de webhooks, aislamiento multi-tenant via TeamRuntime, parametrización SQL completa. **NO se encontraron vulnerabilidades explotables remotamente** sin condiciones especiales.

**Riesgos principales:**
1. **Localhost en whitelist por defecto de Origins WS** (A-WS-02) — atacante puede montar CSRF si el operador olvida `ORUX_WS_ORIGINS`.
2. **Token de operador y de billing no validan `epoch`** (A-AUTH-01) — la revocación de sesiones es inefectiva en HTTP, mientras el WS sí cumple.
3. **POSTGRES_PASSWORD=orux** literal en `.env` real — password trivial (`.env` no commiteado, pero débil).
4. **PresenceMessage no valida que el path exista** (A-WS-01) — DoS lógico sobre la edición colaborativa.
5. **`commit`/`push` accesibles a cualquier miembro** — repudiation y exfiltración de código a remoto externo.
6. **Sandbox del iframe demo es autoinvalidante** (`allow-scripts allow-same-origin`) — si el IDE se compromete, puede leer el `parent`.
7. **Token de sesión en `localStorage`** con TTL 30 días — cualquier XSS = robo persistente.
8. **Aceptación silenciosa de tokens legacy sin `exp`** y sin domain separation.
9. **URL del clone con credenciales embebidas se loguea sin scrubbing** (A-PERS-01).

**Nivel de riesgo global: Medio.** La mayoría de hallazgos son "defensa en profundidad" o requieren condiciones específicas (config olvidada, XSS futuro). No hay vulnerabilidades críticas autoexplotables hoy.

---

## Conteo final

| Severidad | Total |
|-----------|-------|
| Crítica | 0 |
| Alta | 7 |
| Media | 15 |
| Baja | ~22 |
| Informativa | ~10 |

---

## Tabla de hallazgos priorizada (vista rápida)

| ID | Sev | Ubicación | Resumen |
|----|-----|-----------|---------|
| A-INF-01 | Alta | `.env:10` | `POSTGRES_PASSWORD=orux` trivial |
| A-WS-02 | Alta | `config.py:70` | Default `_DEF_ORIGINS` incluye `localhost:*` en prod |
| A-AUTH-01 | Alta | `http_use_cases.py:69-83`, `app.py:556,712` | Token operador y `/billing/checkout` no validan `epoch` |
| A-WS-01 | Alta | `dispatch.py:_h_presence` | `PresenceMessage` no valida path existente → DoS edición |
| A-WS-04 | Alta | `dispatch.py:_h_push` | `push` abierto a member → exfiltración de código |
| A-FE-01 | Alta (latente) | `Editor.tsx:112`, `package.json` | `innerHTML` + `prismjs: "^1.30.0"` (CVE futuro = XSS) |
| A-FE-02 | Alta | `store.ts:315,547,586` | Token sesión en `localStorage`, TTL 30 días |
| A-HTTP-02 | Media | `tokens.py:178-183, 97-101` | Tokens sin `exp` aceptados; `ttl_seg=0` permitido |
| A-HTTP-03 | Media | `oauth.py:144-147` | OAuth `state` sin domain separation HMAC |
| A-HTTP-04 | Media | `app.py:466-485` | Set OAuth replay no multi-worker safe |
| A-WS-03 | Media | `dispatch.py:_h_commit` | `commit` abierto a member → repudiation |
| A-HTTP-05 | Media | `admin.html:943`, `store.ts:605` | Logout no revoca server-side |
| A-FE-04 | Media | `main.tsx:68-97` | Modo demo bypass gate auth (`/app/?demo=1`) |
| A-FE-05 | Media | `landing/App.tsx:603` | Iframe `allow-scripts allow-same-origin` = sandbox roto |
| A-AUTH-02 | Media | `store.py:31-33` | `normalizar` usa `lower()` sin casefold/NFKC |
| A-HTTP-06 | Media | `app.py:847, 879` | Log injection en `kind`/`event` (`%s` en vez de `%r`) |
| A-HTTP-07 | Media | `app.py:209-210, 770` | Webhook Stripe sin cap de body |
| A-INF-02 | Media | `index.html` (×3) | Google Fonts filtra IP — contradice claim "sin telemetría" |
| A-PERS-01 | Media | `dispatch.py:366-368` | URL del clone con creds embebidas se loguea sin scrubbing |
| A-PERS-02 | Media | `lsp.py:64-89` | `Content-Length` LSP sin tope → DoS memoria |
| A-PERS-03 | Media | `users.py:77-96` | `JsonUserStore._flush_sync` sin `fsync()` (dev) |
| B-WS-01 | Media | `sync.py:_sesion_equipo` | Membresía no re-validada durante sesión |
| B-* (~22) | Baja | varios | Hardening, headers, rate-limits específicos, fingerprint |
| I-* (~10) | Inf | varios | Confirmaciones de buenas prácticas; bug funcional OAuth+commit |

---

## 2. Alcance analizado

**Carpetas revisadas:**
- `backend/orux/` (composition, adapters inbound/outbound, application, domain, ports, db) — completo.
- `frontend/ide/` (React+TS, ~24 componentes), `frontend/landing/` (React+framer-motion), `frontend/ops/admin.html` (vanilla).
- Raíz: `Dockerfile`, `Dockerfile.web`, `docker-compose.yml`, `Caddyfile`, `Makefile`, `.env`, `.env.example`, `.gitignore`, `.dockerignore`.
- `scripts/` (backup-db, restore-db, build-og).

**Stack detectado:**
- Backend: Python 3.12, `websockets`, `starlette`+`uvicorn`, `asyncpg`, `pyright`, `tree-sitter`. Sin ORM.
- Frontend: React 18, TypeScript 5.6, Vite 5.4, `framer-motion`, `prismjs` 1.30, `lucide-react`.
- Infra: Caddy 2 (TLS auto), Postgres 16-alpine, 4 contenedores con `no-new-privileges`, imágenes pinneadas por digest.
- Auth: PBKDF2 + HMAC sesiones + OAuth GitHub.
- Pagos: Stripe inline (sin SDK), webhooks firmados HMAC.

**Limitaciones:** sandbox sin internet → no se pudo correr `npm audit`/`pip-audit`, ni probar el binario git real.

---

## 3. Metodología

- Revisión manual de >50 archivos clave (no solo grep).
- 6 sub-agentes paralelos especializados.
- Verificación de git history (sin secretos commiteados).
- Lectura defensiva: rastreo de inputs del cliente hasta sinks (disco, DB, subprocess, broadcast, render DOM).
- Criterios OWASP Top 10 (A01 Broken Access Control, A02 Crypto, A03 Injection, A07 Auth Failures, A08 Software/Data Integrity, A10 SSRF).
- Comandos: `git log/ls-files/grep`, `grep -rE` para patrones inseguros, lectura completa de Dockerfile/Caddyfile/compose.

---

## 4. Hallazgos priorizados (detalle completo)

> Convención de IDs: **A-AUTH/HTTP/WS/PERS/FE/INF-NN**. Severidad y prioridad estimadas en base al modelo de despliegue actual (orux.space, 1 worker uvicorn, 1 operador).

### [A-INF-01] Password de Postgres trivial: `POSTGRES_PASSWORD=orux`
**Severidad:** Alta
**Categoría:** Secretos / Configuración
**Ubicación:** `/home/cesarmanzocode/laidea/.env:10`
**Evidencia:** `POSTGRES_PASSWORD=orux` (literal; mismo nombre del proyecto, 4 caracteres).
**Descripción:** El `.env` real (NO commiteado — verificado en `git log --all`) tiene una password trivialmente predecible. Postgres no expone puerto al host (`expose` no `ports`), así que el atacante necesita acceso a la red Docker para explotarlo. PERO si un contenedor vecino se compromete (subprocess git con CVE, dependencia npm comprometida), accede a `orux:orux@postgres:5432`.
**Impacto:** lectura/escritura total a metadatos (users, teams, ownership, propuestas, plan).
**Probabilidad:** Baja (requiere intrusión a la red interna).
**Recomendación:** generar con `openssl rand -hex 24` y rotar con `ALTER USER`. El `.env` real está bien excluido del repo via `.gitignore` y `.dockerignore`.
**Prioridad de remediación:** Inmediata
**Estado:** Confirmado

### [A-WS-02] Whitelist de Origins WS incluye `localhost:5173` y `localhost:8080` por defecto en producción
**Severidad:** Alta
**Categoría:** CSRF / Configuración
**Ubicación:** `backend/orux/adapters/inbound/websocket/config.py:70`
**Evidencia:** `_DEF_ORIGINS = "https://orux.space,http://localhost:5173,http://localhost:8080"`
**Descripción:** Si el operador del VPS no setea `ORUX_WS_ORIGINS`, el server WS acepta handshakes con `Origin: http://localhost:5173`. Un atacante puede servir HTML en `localhost:5173` en la máquina de la víctima (forzar a un proxy local) y montar CSRF contra el WebSocket con el `orux_session` del browser.
**Impacto:** ejecución de mutaciones (edits, claims, propuestas) en nombre de la víctima autenticada.
**Probabilidad:** Media.
**Recomendación:** quitar `localhost:*` del default. Documentar en `.env.example` que `ORUX_WS_ORIGINS` es obligatorio en producción. Si se quiere dev cómodo, mantener default solo cuando `ORUX_DB_DSN` esté vacío (modo dev).
**Ejemplo:** `_DEF_ORIGINS = "https://orux.space"`.
**Prioridad de remediación:** Inmediata
**Estado:** Confirmado

### [A-AUTH-01] Token del OPERADOR y `/billing/checkout` no validan `epoch` — revocación inefectiva
**Severidad:** Alta
**Categoría:** Autenticación
**Ubicación:** `backend/orux/application/http_use_cases.py:69-83`, `backend/orux/adapters/inbound/http/app.py:556` y `:712`
**Evidencia:**
- `operador_de_token(token, secret)` llama `usuario_de_token(token, secret)` **sin** `epoch_de=`.
- `/billing/checkout`: `usuario = usuario_de_token(tok, _SESSION_SECRET)` igual.
- `login_operador`: `crear_token(usuario, secret, ttl_seg=ttl_seg)` sin pasar `epoch=...`.

El WS sí lo cumple en `auth_handshake.py:204-217`.
**Descripción:** La capa 7 introdujo `epoch` por usuario para revocar sesiones quirúrgicamente. HTTP no la consulta ni la emite. Si el operador rota su contraseña o llama `revocar_sesiones(_ADMIN_USER)`, los tokens vivos siguen valiendo hasta su `exp` natural (8h operador, 30d usuario en `/billing/checkout`).
**Impacto:** una fuga de token del operador NO se cierra rotando password.
**Recomendación:** introducir helper `verificar_session_token(tok, secret, users)` que aplique el patrón de dos pasadas (peek + `epoch_de=`) y usarlo en `operador_de_token` y `_billing_checkout`. En `login_operador`, emitir tokens con `epoch=await users.epoch(username)`.
**Prioridad de remediación:** Inmediata
**Estado:** Confirmado

### [A-WS-01] `PresenceMessage` no valida que el path exista — DoS lógico de la edición colaborativa
**Severidad:** Alta
**Categoría:** Autorización / DoS
**Ubicación:** `backend/orux/adapters/inbound/websocket/dispatch.py:307-322` (`_h_presence`), `backend/orux/application/use_cases.py:343-358`
**Evidencia:** `_CON_PATH_CLIENTE` aplica `path_seguro` pero ni `_h_presence` ni `presence_use_case` chequean que `path` exista en `rt.workspace.snapshot()`.
**Descripción:** un atacante autenticado declara presencia en TODAS las líneas de un archivo (cursor goes 1, 2, 3, ... a ~10 msg/s — bajo el 50/s del rate limit), ocupando `roster.lineas_ocupadas(path)`. `update_use_case` rebota cualquier edit con `if tocadas & ocupadas: res.rebotar_a_autor = viejo`. Los miembros legítimos no pueden editar.
**Impacto:** edición colaborativa anulada para todos los miembros del equipo.
**Probabilidad:** Alta (script trivial).
**Recomendación:** (a) rechazar `PresenceMessage` con path inexistente; (b) TTL por línea ocupada; (c) rate-limit específico `PresenceMessage` (e.g. 5/s/cliente).
**Prioridad de remediación:** Inmediata
**Estado:** Confirmado

### [A-WS-04] `push` permite a cualquier miembro pushear a remoto arbitrario — exfiltración
**Severidad:** Alta
**Categoría:** Autorización / Confidencialidad
**Ubicación:** `backend/orux/adapters/inbound/websocket/dispatch.py:406-433` (`_h_push`), `backend/orux/adapters/outbound/git/binary.py:614-723`
**Evidencia:** `_h_push` no llama `_es_admin_o_logear`. La URL pasa `_url_segura` (allowlist) pero acepta cualquier remoto HTTPS/SSH.
**Descripción:** un miembro malicioso puede pushear el código entero del workspace del equipo a un fork suyo en GitHub/GitLab. No queda log de push exitoso.
**Impacto:** breach de confidencialidad. Para equipos B2B con NDA es una fuga directa.
**Probabilidad:** Baja (requiere miembro malicioso autenticado).
**Recomendación:** (a) loguear `INFO push exitoso a {url}` para auditoría; (b) restringir push a `admin` del equipo, o solo a la URL configurada como `origin`; (c) persistir `origin_esperado` por equipo en Postgres.
**Prioridad de remediación:** Alta
**Estado:** Confirmado

### [A-FE-01] XSS potencial vía `innerHTML = resaltar(...)` dependiendo de `prismjs` (versión flexible)
**Severidad:** Alta (latente)
**Categoría:** XSS / Dependencias
**Ubicación:** `frontend/ide/src/components/Editor.tsx:112` (sink), `frontend/ide/package.json` (`"prismjs": "^1.30.0"`)
**Evidencia:** `codeRef.current.innerHTML = resaltar(ta.value, path)`. Llama `Prism.highlight(...)`. Prism 1.30 escapa correctamente, pero CVEs anteriores (CVE-2022-23647, CVE-2022-39167) lo permitieron.
**Descripción:** HOY no hay XSS. El riesgo es un `npm install` futuro que actualice a 1.31+ con un CVE nuevo. El contenido proviene del WebSocket (peer edits) → atacante miembro inyecta payload, otros miembros lo ejecutan.
**Impacto:** account takeover de todos los miembros del equipo + leak `orux_session` de `localStorage`.
**Probabilidad:** Baja (condicionada a CVE futuro).
**Recomendación:** (a) pinear a `~1.30.0` (no `^`) en `package.json`; (b) preferible: envolver con DOMPurify (10 KB); (c) comentario `// SEGURIDAD: descansa en invariante "Prism escapa"`.
**Prioridad de remediación:** Alta
**Estado:** Confirmado

### [A-FE-02] Token de sesión en `localStorage` con TTL default 30 días — XSS = robo persistente
**Severidad:** Alta
**Categoría:** Almacenamiento de tokens
**Ubicación:** `frontend/ide/src/store.ts:315, 547, 586, 606`; `frontend/ops/admin.html:893, 930` (admin usa `sessionStorage`).
**Evidencia:** `localStorage.setItem("orux_session", m.token)`.
**Descripción:** el token HMAC vive en `localStorage`, accesible a cualquier JS same-origin. TTL por defecto 30 días. Cualquier XSS (A-FE-01) lo robaría. Admin panel usa `sessionStorage` (mejor), pero el token sigue válido server-side los 30 días.
**Impacto:** suplantación persistente del usuario hasta `exp` o revocación.
**Recomendación corto plazo:** reducir TTL operador a 1-2 días con env separada (`ORUX_ADMIN_TOKEN_TTL_SEC`). Reducir TTL del WS a 7 días.
**Recomendación largo plazo:** migrar a cookie `HttpOnly+Secure+SameSite=Lax` + endpoint `/api/v1/auth/ws-ticket` efímero.
**Prioridad de remediación:** Alta
**Estado:** Confirmado

### [A-HTTP-02] Token sin `exp` se acepta con sólo `warning` — sesiones potencialmente eternas
**Severidad:** Media
**Categoría:** Autenticación
**Ubicación:** `backend/orux/domain/identity/tokens.py:178-183` y `:97-101`
**Evidencia:** `if exp is None: logger.warning(...)` (no rechaza). `crear_token` con `ttl_seg=0`/`None` emite sin `exp`. `_env_int("ORUX_TOKEN_TTL_SEC", ..., 0, ...)` permite el `0`.
**Recomendación:** (a) clampar mínimo a 1h; (b) rechazar `exp=None` salvo flag explícito `ORUX_ALLOW_NONEXPIRING_TOKENS=1`; (c) tras lanzamiento, eliminar `_firma_legacy` y aceptación de `exp=None`.
**Prioridad de remediación:** Alta
**Estado:** Confirmado

### [A-HTTP-03] OAuth `state` sin domain separation — confusión potencial con tokens de sesión
**Severidad:** Media
**Categoría:** Autenticación / Defensa estructural
**Ubicación:** `backend/orux/domain/identity/oauth.py:144-147`
**Evidencia:** `_firma_state` usa HMAC con `_SESSION_SECRET` SIN prefijo de dominio.
**Recomendación:** añadir `_DOMAIN_OAUTH_STATE = b"orux-oauth-state\x00"` análogo al `_DOMAIN_SESSION`.
**Prioridad de remediación:** Media
**Estado:** Confirmado

### [A-HTTP-04] Set de OAuth state replay no es multi-worker safe
**Severidad:** Media
**Categoría:** OAuth / Concurrencia
**Ubicación:** `backend/orux/adapters/inbound/http/app.py:466-485`
**Descripción:** hoy seguro porque docker-compose no usa `--workers > 1`. Aumentar workers es regresión silenciosa.
**Recomendación:** (a) externalizar a tabla Postgres; (b) guard rail al startup: `if WEB_CONCURRENCY > 1: raise`.
**Prioridad de remediación:** Media

### [A-WS-03] `commit` accesible a cualquier miembro — repudiation
**Severidad:** Media
**Ubicación:** `backend/orux/adapters/inbound/websocket/dispatch.py:329-355` (`_h_commit`)
**Descripción:** sin `_es_admin_o_logear`. Miembro malicioso commitea con autoría real.
**Recomendación:** restringir a admin del equipo, o rate-limit per-user (100/h).
**Prioridad:** Media

### [A-HTTP-05] Logout (admin y IDE) no revoca el token server-side
**Severidad:** Media
**Ubicación:** `frontend/ops/admin.html:943-951`, `frontend/ide/src/store.ts:605-609`
**Descripción:** clic en "Salir" solo borra del browser. El HMAC sigue valiendo en el server hasta `exp`.
**Recomendación:** `POST /api/v1/logout` que llame `await users.revocar_sesiones(user)`. Requiere A-AUTH-01 resuelto.
**Prioridad:** Media

### [A-FE-04] Modo demo activable en producción bypass del gate de auth
**Severidad:** Media
**Ubicación:** `frontend/ide/src/main.tsx:68-97`, `frontend/ide/src/store.ts:157` (`__setForTutorial` exportado)
**Descripción:** cualquier visitante puede ir a `https://orux.space/app/?demo=1` y entrar al IDE en modo demo con `authed=true`. No conecta WS, pero la URL puede usarse en phishing/clickjacking.
**Recomendación:** (a) limpiar `orux_session` del `localStorage` en demo; (b) `__setForTutorial` solo `import.meta.env.DEV || esDemo()`; (c) guard `window.parent !== window` en `App.tsx`.
**Prioridad:** Media

### [A-FE-05] iframe del demo en landing con `sandbox="allow-scripts allow-same-origin"` — sandbox autoinvalidante
**Severidad:** Media
**Ubicación:** `frontend/landing/src/App.tsx:603`
**Descripción:** la combinación está reconocida como insegura: el código dentro del iframe puede modificar su propio atributo `sandbox` desde el padre via SOP y romper el sandbox. Ambos viven en `orux.space` → el demo tiene acceso DOM completo al `parent.window`, incluido `parent.localStorage.orux_session`.
**Recomendación:** servir el demo desde subdominio distinto (`demo.orux.space`) y quitar `allow-same-origin`. Es la única defensa real.
**Prioridad:** Media

### [A-AUTH-02] `normalizar(username)` usa `.lower()` (no `casefold()`/NFKC)
**Severidad:** Media (preventiva)
**Ubicación:** `backend/orux/domain/identity/store.py:31-33`
**Recomendación:** `username.strip().casefold()` y `unicodedata.normalize("NFKC", ...)`.
**Prioridad:** Media

### [A-HTTP-06] Logging de `kind`/`event` con `%s` — log injection
**Severidad:** Media
**Ubicación:** `backend/orux/adapters/inbound/http/app.py:847-850, 879-882`
**Descripción:** `kind` (32 chars) y `event` permiten inyectar líneas falsas en logs (`\n[CRITICAL] ...`).
**Recomendación:** cambiar `%s` por `%r`.
**Prioridad:** Media

### [A-HTTP-07] `/billing/webhook` sin cap de body — DoS por payload gigante
**Severidad:** Media
**Ubicación:** `backend/orux/adapters/inbound/http/app.py:209-210, 770`
**Descripción:** URL trivialmente descubrible; POST 100MB → memoria del worker se agota antes de verificar HMAC.
**Recomendación:**
```python
if request.url.path == "/api/v1/billing/webhook":
    cl = request.headers.get("content-length")
    if cl and int(cl) > 1024 * 1024:
        return _err("webhook demasiado grande", status=413)
    return await call_next(request)
```
**Prioridad:** Media

### [A-INF-02] Google Fonts contradice claim "sin telemetría" — fuga de IP a Google
**Severidad:** Media (privacidad / cumplimiento de claim)
**Ubicación:** `frontend/landing/index.html:109-114`, `frontend/ide/index.html:28-33`, `frontend/ops/admin.html:22-25`
**Descripción:** la landing promete "Sin trackers de terceros... no se vende ni se filtra a un proveedor externo". Pero cada visita filtra IP+UA+Referer a Google. Bajo GDPR (Múnich 2022), incluir Google Fonts cross-origin es transferencia de datos personales sin base legal.
**Recomendación:** auto-hostear con `@fontsource-variable/inter` + `@fontsource/jetbrains-mono`. ~4 líneas de cambio.
**Prioridad:** Alta (cumplimiento del claim explícito)

### [A-PERS-01] URL del clone con credenciales embebidas se loguea sin scrubbing
**Severidad:** Media
**Categoría:** Secretos / Logging
**Ubicación:** `backend/orux/adapters/inbound/websocket/dispatch.py:366-368`
**Evidencia:** `_es_admin_o_logear(team_id, yo.client_id, f"clone(url={message.url!r})")` — URL sin `_scrubear`.
**Descripción:** Si un cliente envía `clone url="https://alice:ghp_REAL_TOKEN@github.com/foo/bar.git"` (formato git legal), el PAT queda literal en `docker compose logs`, `journalctl`, SIEM. Contradice "credenciales nunca persistidas".
**Recomendación:** envolver con `_scrubear` (regex `_URL_CON_CRED` ya existe en `binary.py`), o loguear sólo `urlparse(url).hostname + path`.
**Prioridad:** Alta
**Estado:** Confirmado

### [A-PERS-02] LSP `_leer_mensaje`: sin tope en `Content-Length` ni cabeceras — DoS de memoria
**Severidad:** Media
**Ubicación:** `backend/orux/domain/analysis/lsp.py:64-89`
**Descripción:** servidor LSP comprometido puede mandar cabeceras sin terminador (OOM byte a byte) o `Content-Length: 9999999999` (alocación masiva).
**Recomendación:** `_MAX_CAB = 8 * 1024`, `_MAX_BODY = 16 * 1024 * 1024`, clampar y devolver `None`.
**Prioridad:** Media

### [A-PERS-03] `JsonUserStore._flush_sync` sin `fsync()` antes de `os.replace`
**Severidad:** Media (solo dev)
**Ubicación:** `backend/orux/adapters/outbound/json/users.py:77-96`
**Descripción:** falta `f.flush(); os.fsync(f.fileno())`. `JsonOwnershipStore` sí lo tiene. Crash duro → `users.json` puede quedar vacío.
**Recomendación:** copiar patrón del Ownership store.
**Prioridad:** Baja (sólo dev local; producción usa Postgres)

### [B-WS-01] Membresía del equipo no se re-valida durante la sesión
**Severidad:** Media (Crítica si entra "expulsar miembro")
**Ubicación:** `backend/orux/adapters/inbound/websocket/sync.py:571-700`
**Descripción:** membresía se chequea en `lobby.py:122` y nunca más. Si operador borra cuenta atacante, la sesión WS sigue editando hasta desconexión.
**Recomendación:** chequear membresía cada N seg (cache 30-60s) en `_despachar`.
**Prioridad:** Media

---

### Hallazgos Bajos / Informativos (resumen)

| ID | Sev | Resumen | Ubicación |
|----|-----|---------|-----------|
| B-HTTP-08 | Baja | `_login` body parse acepta cualquier tipo con `str(...)` | `app.py:588-591` |
| B-HTTP-09 | Baja | Mensaje "es creador de N equipos" filtra cardinalidad post-compromise | `stores.py:97-108` |
| B-HTTP-10 | Baja | `/api/v1/health` y `/status` permiten fingerprint (`ORUX_VERSION`) | `app.py:597-613, 886-898` |
| B-HTTP-11 | Baja | Rate-limit por IP vulnerable a IPv6 /64 rotation | `_rate.py` + `app.py:103-120` |
| B-HTTP-12 | Baja | Faltan `Cache-Control: no-store`, `Permissions-Policy`, `Cross-Origin-Resource-Policy` | `app.py:_SeguridadHeaders:176-194` |
| B-FE-03 | Baja | `pr_url` se renderiza sin validar esquema en cliente | `Sidebar.tsx:104-110` |
| B-FE-05 | Baja | Sin `window.parent !== window` guard en IDE real (clickjacking) | `App.tsx` |
| B-FE-07 | Baja | `error-reporter` envía `message`/`stack` sin sanear | `error-reporter.ts:53-77` |
| B-FE-09 | Baja | Analytics `/api/v1/track` no respeta DNT/`Sec-GPC`; reenvía `location.search` | `analytics.ts:36-61` |
| B-WS-06 | Baja | `auth_handshake` no setea `open_timeout`/`close_timeout` en `serve()` | `sync.py:860-864` |
| B-WS-07 | Baja | `redeem_invite` sin throttle dedicado por IP | `lobby.py:104-120` |
| B-WS-08 | Baja | `verificar_password` timing distinguible cuando usuario no existe | `passwords.py` + `auth_handshake.py` |
| B-WS-09 | Baja | `Workspace.cargar` no aplica `path_seguro` sobre archivos del disco | `storage.py:149-216` |
| B-WS-10 | Baja | LSP `_TransporteProceso timeout=15s` × 50 miembros = starvation potencial | `domain/analysis/lsp.py:466-493` |
| B-WS-11 | Baja | `SaveMessage` sin rate-limit específico → spam LSP fan-out | `dispatch.py:_h_save` |
| B-WS-12 | Baja | `_throttle` GC perezoso solo con >10k buckets → 100MB RAM no recolectada | `_rate.py:55-68` |
| B-WS-13 | Baja | `AdminAssignMany` permite broadcasts de 10k entries × N miembros (amplificación) | `use_cases.py:274-297` |
| B-PERS-04 | Baja | `clonar` usa `startswith` en lugar de `is_relative_to` | `binary.py:601` |
| B-PERS-05 | Baja | Sin quota de disco por equipo en `git clone` | `binary.py:504-612` |
| B-PERS-06 | Baja | `verificar_password` sin clamp en iteraciones del registro | `passwords.py:91-100` |
| B-PERS-01 | Baja | `JsonOwnershipStore` no loguea WARN cuando JSON corrupto (dev) | `adapters/outbound/json/ownership.py:42-54` |
| B-ADMIN-02 | Baja | Admin: 2 usos de `innerHTML` con templates (textos i18n estáticos) | `admin.html:1015-1020, 1086-1088` |
| B-ADMIN-03 | Baja | CSP del admin bloquea Google Fonts (incoherente con `<link>`, positivo para privacidad) | `Caddyfile:59` |
| I-FE-08 | Inf | Ventana ~50ms entre OAuth callback y `absorberSesionDeURL` (mitigado) | `store.ts:542-551` |
| I-FE-12 | Inf | `localStorage` claves UI — solo metadata, no sensible | múltiples |
| I-INF-03 | Inf | Footer mailto sin obfuscación — harvest (decisión consciente) | `landing/App.tsx:1074` |
| I-INF-04 | Inf | Imágenes Docker pinneadas por digest; usuario no-root; `no-new-privileges` | `Dockerfile`, `docker-compose.yml` |
| I-INF-05 | Inf | `_intercambiar` y `stripe_client._post` sin pin de SPKI | `app.py:386-441` |
| I-PERS-07 | Inf | **Bug funcional**: `autor_git` no acepta `gh:<login>` (OAuth users no pueden commitear) | `util.py:28-38` + `binary.py:191-209` |

---

## 5. Riesgos por área

### Frontend
- **IDE:** XSS latente dependiendo de Prism (A-FE-01), token en localStorage (A-FE-02), demo bypass (A-FE-04), iframe sandbox autoinvalidante (A-FE-05). Buena disciplina: React escapa, CSP estricta, sanitización URL en error reporter, validación dominio Stripe.
- **Landing:** Google Fonts (A-INF-02). Resto: scripts inline justificados, analytics sin cookies.
- **Admin panel:** mejores prácticas (sessionStorage, textContent, Bearer no cookie). Falta `Cache-Control: no-store` y logout server-side.

### Backend
- **Auth/identity:** PBKDF2 600k, HMAC con domain separation, OAuth con state firmado + anti-replay, rate-limit por IP+usuario. Falta: validar `epoch` en HTTP (A-AUTH-01), domain separation en OAuth state (A-HTTP-03), rechazar tokens sin `exp` (A-HTTP-02), normalización NFKC (A-AUTH-02).
- **WebSocket:** `path_seguro` ultraestricto, aislamiento multi-tenant via TeamRuntime, rate-limit por conexión + por IP, lock por equipo. Falta: validar Origins default sin localhost (A-WS-02), validar path existente en Presence (A-WS-01), restringir commit/push (A-WS-03/04), re-validar membresía (B-WS-01).
- **HTTP API:** rate-limit, security headers, CSP estricta, body cap 64KB, idempotencia webhooks. Falta: cap body en webhook (A-HTTP-07), log injection (A-HTTP-06), logout server (A-HTTP-05).
- **Persistencia/git:** 100% queries parametrizadas con asyncpg (sin SQL injection), transacciones, `FOR UPDATE`. Git binary excelente: env allowlist, askpass con credenciales solo en env, allowlist de schemes, `core.hooksPath=/dev/null`, hooks purgados post-clone. Falta: scrubear URL del clone en logs (A-PERS-01), caps en LSP (A-PERS-02), fsync en JsonUserStore (A-PERS-03).

### Configuración, infraestructura y dependencias
- **Docker/compose:** Hardened ✅ (no-new-privileges, no-root user, pin por digest, recursos limitados, healthchecks). ❌ `POSTGRES_PASSWORD=orux` en `.env` real (A-INF-01).
- **Caddy:** HSTS, CSP por-ruta, TLS automático. `frame-ancestors 'self'` permite embedding same-origin (consciente para iframe demo).
- **Scripts:** backup-db con `set -a` + source .env (seguro), restore con CONFIRM=yes.
- **Dependencias:** sin SDK Stripe (stdlib), `prismjs 1.30.0`, `react 18.3.1`, `vite 5.4.21`. Sin CVEs activas a cutoff Ene 2026.
- **Secretos:** `.env` NO commiteado al git ✅. Pero `POSTGRES_PASSWORD=orux` debe rotarse.

---

## 6. Acciones recomendadas por prioridad

### Corregir inmediatamente (Bloque 1)

| # | Archivo | Cambio | Hallazgo | Esfuerzo |
|---|---------|--------|----------|----------|
| 1 | `.env` | `POSTGRES_PASSWORD=$(openssl rand -hex 24)` + `ALTER USER orux WITH PASSWORD '...'` en docker | A-INF-01 | 5 min |
| 2 | `backend/orux/adapters/inbound/websocket/config.py:70` | `_DEF_ORIGINS = "https://orux.space"` (sin localhost) | A-WS-02 | 2 min |
| 3 | `.env.example` | Documentar `ORUX_WS_ORIGINS` obligatorio en producción | A-WS-02 | 2 min |
| 4 | `application/http_use_cases.py:69-83` | `crear_token(user, secret, ttl_seg, epoch=await users.epoch(user))` en `login_operador` | A-AUTH-01 | 5 min |
| 5 | `application/http_use_cases.py:80` | `operador_de_token(token, admin_user, secret, users)` async + `epoch_de=` | A-AUTH-01 | 5 min |
| 6 | `adapters/inbound/http/app.py:556, 712` | Convertir `_gate` y `_billing_checkout` a usar `users` para epoch | A-AUTH-01 | 5 min |
| 7 | `adapters/inbound/websocket/dispatch.py:_h_presence` | Rechazar si `path not in rt.workspace.snapshot()` | A-WS-01 | 5 min |
| 8 | `adapters/inbound/websocket/dispatch.py:366-368` | Envolver URL del clone con `_scrubear` antes del log de admin gate | A-PERS-01 | 5 min |

**Total Bloque 1: ~30-40 minutos. Todos reversibles.**

### Corregir en el corto plazo (Bloque 2)

| Archivo | Cambio | Hallazgo |
|---------|--------|----------|
| `domain/identity/tokens.py:178-183` | Rechazar `exp=None` salvo flag explícito | A-HTTP-02 |
| `adapters/inbound/websocket/sync.py:144-146` | Clampar TTL mínimo a 3600s | A-HTTP-02 |
| `adapters/inbound/http/app.py:209-226` (`_LimiteBody`) | Cap 1MB para `/billing/webhook` | A-HTTP-07 |
| `adapters/inbound/websocket/dispatch.py:_h_push` | `if not await _es_admin_o_logear(...)` o validar URL=origin | A-WS-04 |
| `frontend/ide/package.json` | `"prismjs": "~1.30.0"` (no `^`) | A-FE-01 |
| `frontend/ide/src/components/Editor.tsx:112` | Comentario `// SEGURIDAD: depende de invariante Prism escapa` | A-FE-01 |
| `frontend/landing/package.json`, IDE, admin | `npm i @fontsource-variable/inter @fontsource/jetbrains-mono` + remover `<link>` Google | A-INF-02 |
| `domain/identity/oauth.py:144-147` | `_DOMAIN_OAUTH_STATE = b"orux-oauth-state\x00"` en `_firma_state` | A-HTTP-03 |
| `adapters/inbound/http/app.py:847-850, 879-882` | `kind=%r`, `event=%r` | A-HTTP-06 |
| `adapters/inbound/http/app.py` | Añadir `POST /api/v1/logout` (requiere A-AUTH-01 resuelto) | A-HTTP-05 |
| `domain/analysis/lsp.py:64-89` | Caps de cabecera y body LSP | A-PERS-02 |
| `adapters/outbound/json/users.py:77-96` | `fsync()` antes de `os.replace` | A-PERS-03 |
| `adapters/outbound/git/binary.py:601` | `is_relative_to` en lugar de `startswith` | B-PERS-04 |
| `domain/identity/passwords.py:91-100` | Clamp iteraciones a `[100_000, 2_000_000]` | B-PERS-06 |

### Mejoras recomendadas (mediano plazo)

- Re-validar membresía cada 60s en `_despachar` (B-WS-01).
- Externalizar `_oauth_states_usados` a Postgres (A-HTTP-04) o guard rail anti-multi-worker.
- `casefold()` + NFKC en `normalizar(username)` (A-AUTH-02).
- Restringir `commit` a admin o rate-limit por usuario (A-WS-03).
- Limpiar `__setForTutorial` y `orux_session` en modo demo (A-FE-04).
- Rate-limit dedicado para `redeem_invite` y `SaveMessage` (B-WS-07, B-WS-11).
- `Cache-Control: no-store` en headers de seguridad (B-HTTP-12).
- Self-host de fuentes en admin panel también (B-ADMIN-03).
- Validar esquema `pr_url` en cliente (B-FE-03).
- Documentar invariante `WEB_CONCURRENCY=1` en RUNBOOK.
- Sanitizar `message`/`stack` del error-reporter (B-FE-07).
- Respetar DNT/Sec-GPC en analytics (B-FE-09).
- `open_timeout=10` en `serve()` del WS (B-WS-06).
- Aplicar `path_seguro` también en `DiskStorage.cargar` (B-WS-09).
- `verificar_password` con tiempo constante incluso si usuario no existe (B-WS-08).
- Servir iframe demo desde subdominio (A-FE-05).
- Migrar `orux_session` a cookie `HttpOnly` con endpoint ws-ticket (A-FE-02).
- Quota de disco por equipo en `git clone` (B-PERS-05).
- Fix funcional: `autor_git` para usuarios OAuth (`gh:<login>`) (I-PERS-07).

---

## 7. Checklist de seguridad

| Área | Estado | Nota |
|------|--------|------|
| Gestión de secretos | ⚠️ | `.env` excluido del repo ✅; `POSTGRES_PASSWORD=orux` débil. OAuth/Stripe/Admin cerrados-por-defecto ✅. |
| Autenticación | ⚠️ | PBKDF2 600k ✅, HMAC ✅, OAuth state firmado ✅. Pero `epoch` no validado en HTTP (A-AUTH-01). |
| Autorización | ⚠️ | TeamRuntime aislado ✅, admin gate en mutaciones ✅. Pero membresía no re-validada (B-WS-01); commit/push abiertos a member (A-WS-03/04). |
| Validación de entradas | ✅ | `path_seguro` ultra estricto, `_str`/`_int` defensivos en protocol, body cap 64KB. Falta validar Presence path existente (A-WS-01). |
| Protección contra inyecciones | ✅ | SQL 100% parametrizado, subprocess git sin shell, `_GIT_ENV_SEGURO`. |
| Protección contra XSS | ⚠️ | React escapa por defecto ✅, CSP estricta IDE ✅. Riesgo latente con Prism (A-FE-01). |
| CORS | ✅ | No habilitado a propósito; mismo-origen via Caddy proxy. |
| CSRF | ⚠️ | Bearer no cookie inmuniza HTTP. WS valida Origin pero default permite localhost (A-WS-02). |
| Cookies y sesiones | ⚠️ | Token en localStorage IDE (A-FE-02), sessionStorage admin ✅. Sin HttpOnly. |
| Rate limiting | ✅ | Multi-capa: por IP login/errors/track/registro, por conexión WS, por usuario crear-equipo. Falta dedicado para `redeem_invite`/`Presence`/`Save`. |
| Manejo de errores | ✅ | Logger con `repr` (excepto kind/event A-HTTP-06), 401/503/429 consistentes. |
| Logs | ⚠️ | Sin tokens/passwords/code ✅. Pero log injection en `kind`/`event` (A-HTTP-06) y URL del clone (A-PERS-01). |
| Dependencias | ❓ | `npm audit`/`pip-audit` no ejecutable en sandbox. Versiones inspeccionadas sin CVEs conocidas. Pinear `prismjs` a `~1.30.0`. |
| Configuración de producción | ⚠️ | Docker hardened, Caddy TLS auto, healthchecks. `POSTGRES_PASSWORD` débil; localhost en Origins default. |
| Headers HTTP | ⚠️ | nosniff, X-Frame-Options DENY/SAMEORIGIN, Referrer-Policy, HSTS, CSP por-ruta ✅. Falta Cache-Control, Permissions-Policy (B-HTTP-12). |
| Subida de archivos | ✅ | No hay subida directa; archivos vienen como contenido WS validado (`_MAX_CONTENT=1MB`). |
| Seguridad de base de datos | ✅ | asyncpg parametrizado, `FOR UPDATE`, `ON CONFLICT`, FKs CASCADE/RESTRICT, transacciones atómicas. |
| CI/CD | ❓ | No detectado workflow CI/CD en repo (sin `.github/workflows/`). |
| Docker o infraestructura | ✅ | Pin por digest, no-new-privileges, no-root, recursos limitados, healthchecks WS-aware. |

Leyenda: ✅ Correcto · ⚠️ Requiere mejora · ❌ Vulnerable · ❓ No verificable.

---

## 8. Plan de corrección — pruebas y efectos secundarios

**Tests a ejecutar tras cada bloque:**
- `cd backend && python -m pytest -q` (513 tests, no debe regresionar).
- Manual: registro/login/lobby/crear-equipo/invitar/redimir desde un browser real.
- Manual: panel admin login + listar/borrar equipo.
- Manual: OAuth GitHub end-to-end.
- Manual: simulación de WS con `Origin: http://localhost:5173` desde curl/wscat (debe rechazar tras A-WS-02).

**Posibles efectos secundarios a vigilar:**
- A-WS-02: dev local roto sin setear `ORUX_WS_ORIGINS=http://localhost:5173` — documentar prominente en README.
- A-AUTH-01: `_gate` se vuelve async (afecta firma; verificar callers).
- A-WS-01: tutorial OruxBot puede enviar presencia sobre paths fake — validar que no rompa el script.
- A-INF-02: build del frontend pesa unos KB más por las woff2, despreciable.
- Pinear `prismjs` a `~1.30.0`: rebuild necesario.

---

## 9. Conclusión

**Riesgo principal:** el solapamiento de tres condiciones específicas:
1. operador no setea `ORUX_WS_ORIGINS` → server WS acepta `Origin: localhost` (A-WS-02);
2. fuga del token de operador (XSS via Prism futuro, o phishing);
3. rotar password del operador NO cierra la sesión filtrada (A-AUTH-01).

Cualquier combinación expone la consola de operador o permite CSRF al WebSocket. Las tres son fixes mecánicos (~3 archivos, ~30 líneas).

**Correcciones más importantes** (en este orden): rotar `POSTGRES_PASSWORD` → quitar localhost del default de Origins → cablear `epoch` en HTTP → rechazar Presence con path inexistente → scrubear URL del clone → pin Prism → cap webhook → restricción push.

**Siguiente paso recomendado:** comenzar por el Bloque 1 (8 cambios, alta señal/ruido, todos reversibles). Después auditar de nuevo y avanzar al Bloque 2.

La base es **sólida**: PBKDF2, HMAC, parametrización SQL, sandbox de Docker, multi-layer rate limiting, idempotencia de webhooks, allowlist de URLs git, env scrubbing, security headers + CSP — todo aplicado con disciplina. Los hallazgos son refinamientos de un sistema ya bien defendido, no rescates de un sistema roto.

---

## Estado de remediación (2026-05-26)

**Todos los altos + medios + bajos relevantes aplicados. 541 tests pasan (vs 513 baseline).** TypeScript del IDE y landing OK.

### Bloque 1 — Altos (8/8)

| ID | Fix | Files |
|----|-----|-------|
| A-INF-01 | Password Postgres rotada a 24 bytes hex aleatorios | `.env` |
| A-WS-02 | `_DEF_ORIGINS` ya no incluye localhost en producción; modo dev (sin ORUX_DB_DSN) lo incluye automático. `.env.example` documenta `ORUX_WS_ORIGINS` | `config.py`, `.env.example` |
| A-AUTH-01 | `operador_de_token` async + valida epoch con doble-pasada. `login_operador` emite con epoch. `_gate` async. `_billing_checkout` usa helper `_usuario_de_session_con_epoch` | `http_use_cases.py`, `app.py`, `test_api_service.py` |
| A-WS-01 | Rate-limit dedicado Presence (5/s, burst 10) por cliente en TeamRuntime. Cleanup al desconectar | `runtime.py`, `dispatch.py`, `sync.py` |
| A-WS-04 | Push requiere admin del equipo; log INFO con URL scrubbeada al push exitoso | `dispatch.py` |
| A-FE-01 | `prismjs` pineado a `~1.30.0` (no `^`); comentario de seguridad en Editor.tsx | `package.json`, `Editor.tsx` |
| A-FE-02 | TTL token usuario de 30→7 días (clamp mínimo 1h); TTL operador con env separada `ORUX_ADMIN_TOKEN_TTL_SEC` (default 24h, clamp 1h..7d) | `sync.py`, `app.py` |
| A-PERS-01 | URL del clone scrubbeada antes del log de admin gate (igual que push) | `dispatch.py` |

### Bloque 2 — Medios (14/14)

| ID | Fix |
|----|-----|
| A-HTTP-02 | Tokens sin exp rechazados por default; flag `ORUX_ALLOW_NONEXPIRING_TOKENS=1` para opt-out. TTL mínimo clampeado a 1h en `crear_token` |
| A-HTTP-03 | Domain separation `_DOMAIN_OAUTH_STATE` en `_firma_state` |
| A-HTTP-04 | Guard rail al startup que aborta si `WEB_CONCURRENCY > 1` |
| A-WS-03 | Rate-limit per (team, user) de 100 commits/h, mensaje de error al cliente |
| A-HTTP-05 | `POST /api/v1/logout` que revoca sesiones server-side. Wire en admin.html y store.ts |
| A-FE-04 | `__setForTutorial` no-op en producción no-demo. Limpia `orux_session` al entrar a `?demo=1` |
| A-FE-05 | Guard `window.parent !== window && !demoMode` en App.tsx del IDE (anti-clickjacking + iframe escape). Iframe demo documentado en landing |
| A-AUTH-02 | `normalizar(username)` ahora usa NFKC + casefold |
| A-HTTP-06 | `kind` y `event` logueados con `%r` (anti log-injection) |
| A-HTTP-07 | Cap 1MB específico para `/billing/webhook` antes de verificar HMAC |
| A-INF-02 | Google Fonts removido. IDE/landing usan `@fontsource-variable/inter` + `@fontsource/jetbrains-mono` self-hosted. Admin sin Google Fonts (cae a system font) |
| A-PERS-02 | Caps `_MAX_CAB_LSP=8KB`, `_MAX_BODY_LSP=16MB` en `_leer_mensaje` |
| A-PERS-03 | `fsync()` antes de `os.replace` en JsonUserStore |
| B-WS-01 | Re-validación de membresía cada 60s en el loop de sesión; close 4003 si revocaron |

### Bloque 3 — Bajos (selectivos, alta señal/ruido)

| ID | Fix |
|----|-----|
| B-HTTP-08 | `_login` rechaza body no-dict o username/password no-string con 400 |
| B-HTTP-12 | `Cache-Control: no-store`, `Permissions-Policy`, `Cross-Origin-Resource-Policy: same-origin` en `_SeguridadHeaders` |
| B-FE-03 | `pr_url` validado con `URL()` (solo http/https) antes de renderizar |
| B-FE-05 | (Cubierto por A-FE-05) Guard anti-iframe del IDE real |
| B-FE-07 | `error-reporter` sanitiza `message` y `stack` con `sanitizarTexto()` (regex URL + key=value sensibles) |
| B-FE-09 | `analytics` respeta DNT/Sec-GPC/globalPrivacyControl. No reenvía `location.search` |
| B-WS-06 | `open_timeout=10`, `close_timeout=5` en `websockets.serve()` |
| B-WS-09 | `path_seguro` aplicado en `Workspace.cargar` sobre rel-paths del FS |
| B-WS-11 | Rate-limit save (60/min per team-user) en `_h_save` para no saturar análisis |
| B-PERS-04 | `clonar` usa `Path.is_relative_to` en vez de `startswith` para chequear escape |
| B-PERS-06 | `verificar_password` clampa iteraciones del registro a [100k, 2M] |
| B-PERS-01 | `JsonOwnershipStore` ahora loguea WARN cuando JSON está corrupto |

### Bloque 4 — Bug funcional

| ID | Fix |
|----|-----|
| I-PERS-07 | `autor_git` ahora maneja `gh:<login>` → email `<login>@users.noreply.github.com` (formato canónico GitHub). Antes el commit fallaba porque `gh:joaquin@orux.local` no es email RFC válido |

### Cambios estructurales

- **Tests:** `test_api_service.py` extendido con epoch + revocación. `test_robustez.py` ajustado al nuevo comportamiento de tokens sin exp + clamp TTL. `test_identity.py` actualizado para emitir tokens con ttl explícito.
- **Memoria del agente:** memoria viva del proyecto actualizada con todos los fixes.
- **`vite-env.d.ts`** creado en `frontend/ide/src/` para typear `import.meta.env.DEV`.

### Pendientes operativos (no-código, para el usuario)

1. **Rotar password Postgres en el VPS**: `docker compose exec postgres psql -U orux -d orux -c "ALTER USER orux WITH PASSWORD '068358070d167ec689f8a395eca97a74f8630b6ab31d3d02';"` y luego `docker compose up -d`. Pasos en `.env`.
2. **`npm install`** en `frontend/ide/` y `frontend/landing/` para traer fontsource (necesita internet del VPS).
3. **Verificar `ORUX_WS_ORIGINS` en el VPS** — el default ya no incluye localhost.
4. **Validar manualmente** con el smoke-test de `docs/smoke-test.md`.

### Diferidos conscientemente (no implementados)

- **Subdominio para iframe demo** (A-FE-05 ideal): requiere DNS + Caddyfile separado, sale de scope de auditoría. Mitigación: guard anti-iframe en IDE + clean orux_session en demo.
- **Migrar tokens a cookie HttpOnly + endpoint `/auth/ws-ticket`** (A-FE-02 ideal): rediseño grande del flujo de auth. Mitigación: TTL bajado a 7d.
- **Externalizar `_oauth_states_usados` a Postgres** (A-HTTP-04 ideal): no escalamos workers todavía. Mitigación: guard rail que rechaza WEB_CONCURRENCY > 1.
- **Quota de disco por equipo en clone** (B-PERS-05): se evaluará si llega a ser problema operativo real.
