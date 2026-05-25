# Operations: Troubleshooting

Problemas comunes y cómo diagnosticarlos. Cada uno: síntoma → causa probable → comando para verificar → fix.

## "El sistema está caído"

```bash
# Verificación general
curl -I https://orux.space/api/v1/status     # → 200 si OK, 5xx si caído
docker compose ps                              # ¿qué contenedor está down?
docker compose logs --since 5m | tail -100    # los 4 logs recientes
```

Si Caddy está down: nadie ve nada (es la única puerta).

```bash
docker compose logs caddy --since 5m
docker compose restart caddy
```

Causas comunes de Caddy down:

- Syntax error en `Caddyfile` tras editar y deploy: `docker compose exec caddy caddy validate /etc/caddy/Caddyfile`.
- Cert renewal failing: Let's Encrypt rate-limit (si reintentas mucho). Esperar 1h.

## "Los devs no se pueden conectar al WS"

### Síntoma A: handshake 403

```bash
docker compose logs orux --since 5m | grep -i "origen no permitido"
```

**Causa**: cliente nuevo (dominio distinto) no está en `ORUX_WS_ORIGINS`.

**Fix**: agregar al docker-compose.yml:

```yaml
environment:
  ORUX_WS_ORIGINS: "https://orux.space,https://nuevo-dominio.com"
```

Después: `docker compose up -d --force-recreate orux`.

### Síntoma B: 401 (token inválido)

```bash
docker compose logs orux --since 5m | grep -iE "auth|token"
```

**Causas posibles**:

- Token expiró (TTL 30 días por default). El cliente debería re-loguear automáticamente.
- Secret HMAC cambió (rotación). `docker compose logs orux | grep "ORUX_SESSION_SECRET"`.
- Epoch revocado (`UserStore.revocar_sesiones` se llamó). Verificar `users.epoch` en DB.

**Fix**: pedir a los devs que cierren sesión y vuelvan a loguear.

### Síntoma C: el WS server no responde (timeout en handshake)

```bash
docker compose ps orux   # ¿está running?
docker compose logs orux --since 5m | tail -50
```

**Causas posibles**:

- OOM (memoria agotada). `docker stats orux` para ver uso.
- Loop bloqueado (un análisis pesado / un git que se cuelga). Verificar logs de LSP o git.

**Fix**: `docker compose restart orux`. Si recurre, ver memory limits del compose o investigar el comando que bloquea.

## "El panel admin no me deja entrar"

```bash
curl -X POST https://orux.space/api/v1/login \
  -H "Content-Type: application/json" \
  -d '{"username": "admin", "password": "..."}'
```

### Síntoma: 503 "API no configurada"

**Causa**: `ORUX_ADMIN_USER` o `ORUX_ADMIN_TOKEN` no seteados en el contenedor `api`.

**Fix**: setear en docker-compose + restart.

### Síntoma: 401 "no autorizado"

**Causa**:

- Username no es el `ORUX_ADMIN_USER` (case-sensitive tras normalizar).
- Password incorrecta.
- Cuenta no existe (registrar primero vía WS).
- Rate-limit (3 logins/min/IP).

**Fix**: verificar password; si olvidada, regenerar:

```bash
# Cambiar password manualmente:
docker compose exec orux python -c "
from orux.adapters.outbound.postgres.pool import Database
from orux.adapters.outbound.postgres.stores import PgUserStore
import asyncio, os

async def main():
    db = await Database.conectar(os.environ['ORUX_DB_DSN'])
    s = PgUserStore(db)
    # Hack: borrar y re-registrar (NO recomendado en producción real)
    pass
asyncio.run(main())
"
```

Mejor: ir al panel admin desde otro browser con session activa, o restaurar de backup.

## "OAuth GitHub falla"

```bash
docker compose logs api --since 10m | grep -iE "oauth|github"
```

### Síntoma: `/oauth/github/login` → 503

**Causa**: `ORUX_GH_CLIENT_ID`, `ORUX_GH_CLIENT_SECRET`, o `ORUX_GH_REDIRECT` no configurados.

**Fix**: setear en `api` (no en `orux`). Ver [`oauth-github.md`](../oauth-github.md) para el setup.

### Síntoma: callback → `?oauth=error&reason=state`

**Causa**: state CSRF inválido. Posibles razones:

- Tomó >120s entre `/login` y callback (state vencido).
- Replay: alguien (extensión browser, etc.) consumió el state.
- Reloj del server desfasado (raro).

**Fix**: el usuario reintenta el flujo desde el botón "Entrar con GitHub". Si recurre: verificar `date` en el VPS (sync con NTP).

### Síntoma: callback → `?oauth=error&reason=github`

**Causa**:

- El intercambio `code → access_token` falló. GitHub rechazó (code vencido, app deshabilitada, client_secret mal).
- Rate-limit de GitHub (raro a menos de >5000 req/h).

```bash
docker compose logs api --since 5m | grep -i "OAuth GitHub falló"
```

**Fix**: verificar `client_secret` no rotado en el dashboard de GitHub. Re-emitir si necesario.

### Síntoma: usuario logueado pero al entrar al WS dice "token inválido"

**Causa**: `ORUX_SESSION_SECRET` distinto entre `api` (que emitió el token) y `orux` (que verifica).

**Fix**: verificar que el env compartido es el mismo:

```bash
docker compose exec api env | grep ORUX_SESSION_SECRET
docker compose exec orux env | grep ORUX_SESSION_SECRET
# Deben ser idénticos.
```

Si difieren: corregir en docker-compose.yml y restart de ambos.

## "Stripe webhook no funciona"

```bash
docker compose logs api --since 1h | grep -i "billing/webhook\|stripe"
```

### Síntoma: webhook → 400 "firma inválida"

**Causa**: `STRIPE_WEBHOOK_SECRET` distinto del configurado en el dashboard de Stripe.

**Fix**: copiar el `whsec_...` del dashboard de Stripe → settings → webhooks → tu endpoint → "Signing secret". Setear en docker-compose, restart `api`.

### Síntoma: webhook llega, evento no aplica

```bash
docker compose logs api --since 1h | grep -E "Stripe:"
```

Si el log dice "evento X ya procesado (replay)": el `event_id` ya está en `processed_webhooks`. Es idempotencia funcionando.

Si dice "equipo Y inexistente": el `metadata[team_id]` en la sesión de Checkout no matchea ningún equipo en tu DB. Verificar que estás usando la misma DB para Checkout y Webhook (no Test Mode vs Live Mode mezclados).

### Síntoma: alta procesada, plan no cambia

```sql
-- En la DB:
SELECT id, nombre, plan, stripe_subscription_id FROM teams WHERE id = '<team_id>';
```

Si el plan sigue siendo `free`: el webhook handler falló silencioso. Logs:

```bash
docker compose logs api --since 1h | grep -i error
```

### Síntoma: ajuste de asientos no funciona

```bash
docker compose logs orux --since 1h | grep -iE "seats|asientos"
```

Posibles:

- `STRIPE_SECRET_KEY` no seteado en `orux` (solo en `api`). Debe estar en AMBOS.
- Lock contendido (raro a menos de muchos miembros entrando juntos).
- Stripe rechazó (subscription cancelada, etc.). Log debería decir.

## "El análisis LSP no anda"

```bash
docker compose logs orux | grep -E "LSP (py|jsts|go|rust)" | tail -20
```

### Síntoma: chip dice `"ast"` o `"treesitter"` siempre, nunca `"lsp"`

**Causa**: LSP en cooldown o no arranca.

```bash
docker compose logs orux | grep "LSP .* arranque #"
# → "LSP py arranque #4 falló; próximo reintento en 480s"
```

**Razón concreta del fallo** (debería estar en el log inmediatamente antes):

```bash
docker compose logs orux | grep "LSP .* NO disponible"
# → "LSP py NO disponible -> el análisis degrada... Razón: pyright-python-langserver: ..."
```

Casos típicos:

- **`libatomic.so.1` falta**: `apt install libatomic1` en Dockerfile.
- **Permisos de cache**: `chown -R orux:orux $PYRIGHT_PYTHON_CACHE_DIR`.
- **Binario no encontrado**: `which pyright-python-langserver` en el contenedor. Reinstalar.

**Fix**: tras corregir, esperar al cooldown O reciclar el LSP:

```bash
docker compose restart orux  # fuerza re-arranque de TODO
```

### Síntoma: el cap de lenguajes free saturado

**Causa**: equipo free con 3+ lenguajes en uso. Solo 2 pueden tener LSP activo simultáneo.

**Fix**: no es bug. Degrada a tree-sitter/AST. Upgrade a premium remueve el cap.

## "Git falla en commit/clone/push"

```bash
docker compose logs orux --since 5m | grep -iE "git|commit|clone|push"
```

### Síntoma: `(False, "URL de repo no válida")`

**Causa**: URL no pasa `_url_segura`. Probablemente scheme raro (`ext::`, etc.) o caracteres prohibidos.

**Fix**: el dev debe usar HTTPS/SSH normal. No hay forma de aflojar la validación (es seguridad).

### Síntoma: clone funciona pero el workspace queda vacío

**Causa**: el repo clonado tenía solo `.git/` o todos los archivos fueron filtrados por anti-traversal.

```bash
docker compose logs orux --since 5m | grep "clone: entry .* escapaba"
```

**Fix**: el dev verifica que el repo tiene archivos normales (no symlinks raros).

### Síntoma: push rechazado "el remoto cambió"

**Causa**: alguien commiteó en `main` (o la rama destino) y ahora el push local es non-fast-forward.

**Fix**: el dev hace `git pull` en su terminal local (orux NO hace pull, por tesis). Reintenta el push.

### Síntoma: push a `orux/<team_id>` falla con "alguien commiteó a mano"

**Causa**: el `--force-with-lease` rechazó porque la rama de publicación tiene commits manuales (alguien NO siguió la convención).

**Fix**: el dev hace `git pull origin orux/<team_id>` en su terminal, decide qué hacer (merge o rebase o force), commitea, y reintenta push desde el IDE.

## "Postgres lento / queries colgándose"

```bash
docker compose exec postgres psql -U orux -d orux -c "
  SELECT pid, query, state, waiting, age(clock_timestamp(), query_start) AS duration
  FROM pg_stat_activity
  WHERE state != 'idle'
  ORDER BY duration DESC
  LIMIT 10;
"
```

Causas comunes:

- **Tabla `processed_webhooks` enorme**: la purga de 30 días no corrió. Manual:

```sql
DELETE FROM processed_webhooks WHERE processed_at < now() - interval '30 days';
```

- **Tabla `proposals` enorme**: propuestas antiguas no resueltas. Manual: borrar las de equipos eliminados o muy viejas:

```sql
DELETE FROM proposals
WHERE team_id NOT IN (SELECT id FROM teams)
  OR created_at < now() - interval '180 days';
```

- **Sin índices** en una query nueva: ver con `EXPLAIN ANALYZE` y agregar índices al schema.

## Logs útiles por categoría

```bash
# Auth (login, registro, OAuth)
docker compose logs --since 1h orux api | grep -iE "auth|login|register|oauth"

# Git
docker compose logs --since 1h orux | grep -iE "commit|clone|push|git"

# LSP
docker compose logs --since 1h orux | grep -iE "LSP"

# Stripe
docker compose logs --since 24h api | grep -iE "stripe|billing|webhook"

# Errores y warnings
docker compose logs --since 1h | grep -iE "error|warn|warning|exception"

# Rate limits
docker compose logs --since 1h | grep -i "rate-limit"

# Auditoría (BACKEND-AUDIT-XXXX)
docker compose logs --since 7d | grep "BACKEND-AUDIT"
```

## Si nada de esto sirve

1. **Capturar el estado**:
   ```bash
   docker compose ps > /tmp/state.txt
   docker compose logs --since 1h > /tmp/logs.txt
   df -h >> /tmp/state.txt
   docker stats --no-stream >> /tmp/state.txt
   free -h >> /tmp/state.txt
   ```

2. **Backup preventivo** antes de tocar nada:
   ```bash
   make db-backup
   ```

3. **Reiniciar limpio** (último recurso):
   ```bash
   docker compose down  # NO toca volúmenes
   docker compose up -d --build
   ```

4. **Reportar** el incidente con logs + estado a `cesarmanzocode@gmail.com` o issue en el repo.

## Lecciones operativas aprendidas

(De CLAUDE.md, "Trampas operativas ya vistas")

- **Servidor zombi en puerto 8765** al cambiar protocolo: `ps aux | grep python | grep -v grep && lsof -i:8765`.
- **Healthcheck con TCP connect crudo spamea tracebacks**: el healthcheck del WS debe hacer handshake real, no socket pelado.
- **pyright en `python:3.12-slim` necesita `libatomic1`** + cache dir writable + sabe que `documentSymbol` NO trae firma.
- **Auto-reload del frontend dev borraba ownership**: histórico pre-React, ya no aplica. Pero la lección queda: persistir estado dentro de un dir watched-by-something explota.
