# Operations: Runbook

Operaciones comunes en el VPS. El `RUNBOOK.md` en la raíz del repo es la fuente oficial (8 secciones operativas detalladas); este doc apunta y resume.

## Tareas frecuentes

### Re-deploy

```bash
cd /opt/orux
git pull origin main
make redeploy
docker compose logs -f orux api
```

### Backup manual de DB

```bash
make db-backup
# → /data/backups/orux-YYYY-MM-DD.sql.gz
```

Si configurado, sube también a DO Spaces. Ver [`backup.md`](backup.md).

### Restore de DB

```bash
make db-restore
# Pide confirmación. Restaura del último backup.
```

**Destructivo**: la DB actual se borra. Solo para recuperación de desastres.

### Ver logs en tiempo real

```bash
make logs                # los 4 contenedores
docker compose logs -f orux  # solo orux
docker compose logs orux --since 1h | grep -i error
```

### Reiniciar un servicio sin tocar volúmenes

```bash
docker compose restart orux
docker compose restart api
```

### Shell de Postgres

```bash
make db-shell
# psql -U orux orux
```

Útil para queries ad-hoc:

```sql
-- Cuántos equipos con plan premium?
SELECT plan, count(*) FROM teams GROUP BY plan;

-- Equipos con suscripción Stripe?
SELECT id, nombre, stripe_subscription_id FROM teams WHERE stripe_subscription_id != '';

-- Usuarios sin equipo (huérfanos)?
SELECT u.username FROM users u LEFT JOIN team_members m ON m.username=u.username WHERE m.username IS NULL;

-- Workspaces más grandes (count de ownership)?
SELECT team_id, count(*) AS n_owners FROM ownership GROUP BY team_id ORDER BY n_owners DESC LIMIT 10;
```

## Operaciones del operador (panel admin)

Endpoints en `/api/v1/admin/*`. Autenticación: login con `ORUX_ADMIN_USER` + password → Bearer token de 8h.

### Listar todos los usuarios

```bash
curl -H "Authorization: Bearer $TOKEN" https://orux.space/api/v1/users
```

### Listar todos los equipos (con plan + miembros)

```bash
curl -H "Authorization: Bearer $TOKEN" https://orux.space/api/v1/teams
```

### Detalle de un equipo

```bash
curl -H "Authorization: Bearer $TOKEN" https://orux.space/api/v1/teams/<team_id>
# → {id, nombre, plan, miembros: [{usuario, rol}, ...]}
```

### Cambiar plan manualmente

```bash
curl -X POST -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"plan": "premium"}' \
  https://orux.space/api/v1/teams/<team_id>/plan
```

NO crea suscripción Stripe; cambio manual. Útil para premiar / compensar / beta testers.

### Borrar un equipo

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  https://orux.space/api/v1/teams/<team_id>
```

CASCADE en FK barre miembros/invites/ownership/proposals. NO toca el workspace en disco (`/data/orux/ws/<team_id>/`) — corré `rm -rf` aparte si querés.

### Borrar un usuario

```bash
curl -X DELETE -H "Authorization: Bearer $TOKEN" \
  https://orux.space/api/v1/users/<username>
```

400 si es el operador (no te disparas en el pie) o tiene FK pendientes (creador de equipo / dueño de ownership).

## Diagnóstico rápido

### Status público

```bash
curl https://orux.space/api/v1/status
# → {ok: true, uptime_s: 12345, version: "dev"}
```

Sin auth. Apto para UptimeRobot.

### Healthcheck (con DB)

```bash
curl https://orux.space/health
# → {ok: true, db: true} o {ok: false, db: false} → 503
```

Cualquier 5xx tras 30s del boot es señal de problema.

### Quién está conectado al WS

```bash
# En el contenedor orux:
docker compose exec orux python -c "
import asyncio
# Hacky: no hay endpoint para esto.
# Mirar los logs: 'AuthOk para X'
"
```

NO hay endpoint para "quién está conectado" hoy. Se infiere de logs o queries SQL (presencia NO se persiste en DB; solo memoria).

### Eventos Stripe recientes

```bash
docker compose logs api --since 24h | grep -i "Stripe:"
# → "Stripe: equipo X → plan premium (event_id=evt_...)"
```

```sql
-- En la DB:
SELECT event_id, processed_at FROM processed_webhooks ORDER BY processed_at DESC LIMIT 20;
```

### Sesiones LSP arrancadas

```bash
docker compose logs orux | grep -iE "LSP (py|jsts|go|rust)"
```

`LSP X arrancado` (OK), `LSP X arranque #N falló` (cooldown), `LSP X murió (subprocess)` (auto-reintento).

## Operaciones de recuperación

### Postgres caído

```bash
docker compose logs postgres | tail -50
docker compose restart postgres
```

Si no levanta: revisar `/data/postgres` (disk full? permisos rotos?). Restaurar del último backup en última instancia.

### orux WS caído

```bash
docker compose ps    # ¿está en restart loop?
docker compose logs orux | tail -50
docker compose restart orux
```

Causas comunes:
- OOM (RAM agotada). Subir el límite o bajar el cap de runtimes activos.
- Path con permisos rotos. `chown -R orux:orux /data/orux`.

### api HTTP caído

Igual que orux. `docker compose restart api`. El panel admin queda inaccesible; la colaboración del WS sigue.

### Caddy caído

Todo se cae (es la única puerta a internet). `docker compose restart caddy`. Si no levanta: revisar `Caddyfile` syntax (`docker compose exec caddy caddy validate /etc/caddy/Caddyfile`).

### Disco lleno

```bash
df -h
du -sh /data/*
```

Causas más comunes:

- `/data/postgres` crece sin techo. Verificar tabla `processed_webhooks` (la purga corre cada 24h).
- `/data/orux/ws/` crece con workspaces grandes (devs guardan binarios o `node_modules` por accidente).
- Logs de Docker. `docker system prune -af --volumes` (CUIDADO: borra volúmenes sin uso).

### Rotar el secret HMAC

```bash
# Apaga el rotate
docker compose stop orux api

# Backup del secret viejo
cp /data/orux/secret /data/orux/secret.bak

# Genera nuevo
openssl rand -hex 32 > /data/orux/secret
chmod 600 /data/orux/secret

# Configurar env compartido (docker-compose.yml):
# ORUX_SESSION_SECRET: ${SECRET_HEX}

docker compose up -d orux api
```

**Efecto**: TODOS los tokens de sesión vivos dejan de valer. Los devs deben re-loguear. Solo en emergencia (sospecha de fuga del secret).

Para rotación con superposición (sin tirar sesiones), implementar `kid` en producción. Ver [`security/auth.md`](../security/auth.md).

## Operaciones del Sprint G (housekeeping pre-anuncio)

Ver [`housekeeping-pre-anuncio.md`](../housekeeping-pre-anuncio.md) raíz de docs. Checklist en 7 secciones:

1. Limpieza de testing data en Postgres (queries SQL).
2. Verificación de secretos rotados.
3. Backup limpio antes de mostrar.
4. Healthchecks verdes.
5. Cert HTTPS válido.
6. WS Origins whitelist correcta.
7. Smoke test ejecutado.

Hecho y verificado por el usuario el 2026-05-23 antes del anuncio.

## Smoke test

Ver [`smoke-test.md`](../smoke-test.md). Guion manual de 30-60 min en 8 fases:

1. Setup limpio.
2. Auth (register, login, OAuth).
3. Lobby (crear, invitar, redimir).
4. Editar workspace coordinado.
5. Save + impacto (con LSP, con rename).
6. Git (commit, push a rama del equipo).
7. Admin panel (operador).
8. Cross-browser (Safari, Firefox, Chrome Android).

Re-correr tras cambios grandes (refactor hex, capa nueva crítica).

## Troubleshooting

Ver [`troubleshooting.md`](troubleshooting.md) para problemas específicos con soluciones.
