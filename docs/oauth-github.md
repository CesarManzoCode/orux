# GitHub OAuth — contrato e integración

Capa nueva sobre la identidad (capa 7). El login usuario+contraseña sigue
funcionando igual; GitHub OAuth es **aditivo y cerrado por defecto** (sin las
4 variables de entorno, `/oauth/github/*` responde 503 y nada cambia).

## La idea en una línea

OAuth NO inventa una sesión nueva: su único trabajo es producir el **mismo
token de sesión HMAC de la capa 7**. El navegador hace el viaje a GitHub por
HTTP; vuelve con un token; el front lo usa exactamente como el auto-login de
hoy. El protocolo WebSocket no cambia ni un byte.

## Backend (ya implementado)

- `orux/identity/oauth.py` — lógica pura (URL de autorización, identidad
  `gh:<login>`, `state` CSRF firmado con vencimiento). Testeada en sandbox
  (`tests/test_oauth.py`).
- `UserStore.asegurar_externo` / `PgUserStore.asegurar_externo` — crea la
  cuenta `gh:<login>` sin contraseña (no se puede entrar a ella por
  password; `existe()` sí, para que `SessionMessage` la acepte).
- `orux/api/app.py` — rutas HTTP (contenedor `api`, Starlette):
  - `GET /oauth/github/login` → 302 a GitHub con `state` firmado.
  - `GET /oauth/github/callback` → valida `state`, canjea `code`, deriva
    `gh:<login>`, asegura la cuenta, emite el token y **redirige al SPA**.
- Caddy proxya `/oauth/*` → `api:8800`. `docker-compose.yml` y
  `.env.example` ya tienen las variables.

### Identidad: `gh:<login>` (decisión de seguridad, no cosmética)

El registro con contraseña está abierto. Si la identidad OAuth fuese el
login pelado, un atacante podría pre-registrar con contraseña el nombre =
al handle de GitHub de una víctima y secuestrar su cuenta cuando entrara por
GitHub. El prefijo `gh:` hace **imposible** esa colisión. Que se vea en la
UI es deuda cosmética (se pule luego con un display-name), no se negocia.

## Lo que falta — FRONTEND (otra sesión; aquí está el contrato exacto)

1. **Botón "Entrar con GitHub"** en la pantalla de login: un enlace normal a
   `/oauth/github/login` (es un redirect del navegador, NO fetch/WS).
   Mostralo siempre; si OAuth no está configurado el server responde 503 y
   no se inicia nada — opcional: ocultarlo si un `GET /oauth/github/login`
   diera 503, pero no es necesario para un primer corte.

2. **Al volver al SPA** (`/app/`), leer la URL de retorno:
   - Éxito: el token viene en el **FRAGMENT** — `#session=<token>`, NO en el
     query. El fragmento no viaja al server ni aparece en Referer/logs de
     proxy (ver `_volver` en `api/app.py`, BACKEND-AUDIT-0019). Leerlo de
     `location.hash`, tratarlo **idéntico** a `orux_session` de localStorage:
     guardarlo y mandar `SessionMessage(token)`. Es el mismo token de la capa
     7 — el flujo auth→lobby→equipo no cambia. Limpiar el fragmento después
     (history.replaceState).
   - Error: `?oauth_error=<código>` — códigos: `cancelado` (el usuario
     canceló en GitHub), `state` (CSRF/link vencido), `github` (falló el
     intercambio). Mostrar un aviso y volver al login normal.

3. No hace falta tocar `store.ts`/protocolo: `SessionMessage` ya existe y el
   server ya lo acepta para identidades `gh:`.

## Activarlo en el VPS

Ver `.env.example` (sección GitHub OAuth): crear la OAuth App en GitHub con
callback `https://TU_DOMINIO/oauth/github/callback`, y setear
`ORUX_SESSION_SECRET` (mismo valor para los servicios `orux` y `api`),
`ORUX_GITHUB_CLIENT_ID`, `ORUX_GITHUB_CLIENT_SECRET`,
`ORUX_OAUTH_REDIRECT`.

## Follow-ups conscientes (NO hechos a propósito)

- Email real de commit: la identidad sigue siendo `gh:<login>` y
  `_autor_git` produce el email sintético `…@orux.local`. Traer el email
  verificado de GitHub requiere propagar un campo email por todo el stack
  (hoy la identidad es un solo string). Diferido.
- Display-name (mostrar `octocat` en vez de `gh:octocat` en presencia/
  commits/panel) — cosmético, diferido.
- `exp` en el token de sesión (hallazgo de la auditoría de robustez, ver
  memoria `orux_blindaje_pendiente`): ortogonal a OAuth, sigue pendiente.
- Scope `repo` para autocompletar clone/push: descartado por ahora
  (consentimiento mínimo, decisión del usuario).
