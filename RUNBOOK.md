# Orux · runbook operacional

Guía de bolsillo para mantener Orux corriendo en el VPS. No reemplaza
`CLAUDE.md` (arquitectura) ni `README.md` (visión); es para los momentos
"algo se rompió a las 2 AM" o "necesito ajustar Y manual".

> **Fuente de verdad:** este documento envejece. El comportamiento real
> vive en el código y el `git log`. Si algo de acá no cuadra, confiá en
> el código primero y actualizá el runbook al volver.

---

## 1. Acceso al VPS

```bash
ssh <usuario>@orux.space        # o la IP, según cómo lo tengas
cd /ruta/al/repo                 # donde clonaste orux
```

Todos los comandos `make ...` y `docker compose ...` se corren desde esa
raíz del repo.

---

## 2. Estado y logs

```bash
make ps                          # estado de los 4 contenedores
make logs                        # logs combinados, en vivo
docker compose logs -f orux      # solo el server WS
docker compose logs -f api       # solo la API HTTP
docker compose logs --tail=200 postgres
```

**Healthchecks**: `make ps` muestra `(healthy)`/`(unhealthy)`/`(starting)`.
Si `orux` o `api` aparecen `unhealthy` por mucho tiempo, Docker los
reinicia solo (config en `Dockerfile` y `docker-compose.yml`). Antes de
debuggear lógica, mirá los logs.

---

## 3. Backup y restore

### 3.1 Backup manual

```bash
make db-backup
```

Eso:
1. Hace `pg_dump | gzip` → `./backups/orux-YYYY...sql.gz` (siempre).
2. Limpia backups locales con más de 7 días (configurable: `RETENTION_DIAS`).
3. Si `DO_SPACES_*` están seteadas en `.env`, sube la copia al bucket.

Sin `DO_SPACES_*` el backup local sigue funcionando — la subida es
opt-in. Mejor algo que nada.

### 3.2 Configurar el off-site (DigitalOcean Spaces, opcional)

Para sobrevivir a la muerte del VPS entero, los backups deben vivir fuera
del host. DO Spaces es S3-compatible y barato.

1. **Crear el Space**: DigitalOcean → Spaces Object Storage → Create.
   Elegí región cercana al VPS (latencia + costo). Anotá el nombre y la
   región (`nyc3`, `ams3`, `fra1`, `sfo3`, `sgp1`).
2. **Generar credenciales**: DigitalOcean → API → Spaces Keys → Generate
   New Key. Copiá **Access Key** y **Secret Key** (la secret la verás
   una sola vez).
3. **Llenar `.env`** en el VPS:
   ```env
   DO_SPACES_BUCKET=orux-backups-prod
   DO_SPACES_ENDPOINT=https://nyc3.digitaloceanspaces.com
   DO_SPACES_KEY=DO00XXXXXXXXXXXX
   DO_SPACES_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
   DO_SPACES_PREFIX=orux-db
   ```
4. **Instalar AWS CLI en el host**:
   ```bash
   sudo apt install awscli         # Debian/Ubuntu
   # o pipx install awscli         # con pipx
   ```
5. **Probar**:
   ```bash
   make db-backup
   # Deberías ver: [backup] ✓ local OK + [backup] subiendo a s3://...
   ```
6. **Listar lo que ya está en el bucket** (sanity check):
   ```bash
   AWS_ACCESS_KEY_ID=$DO_SPACES_KEY AWS_SECRET_ACCESS_KEY=$DO_SPACES_SECRET \
     aws s3 ls s3://$DO_SPACES_BUCKET/$DO_SPACES_PREFIX/ \
     --endpoint-url $DO_SPACES_ENDPOINT
   ```

### 3.3 Cron diario

Como root o el usuario que corre docker (el que tiene acceso a
`docker compose`), agregá a `crontab -e`:

```cron
# Backup diario a las 3 AM UTC.
0 3 * * * cd /ruta/al/repo && /usr/bin/make db-backup >> /var/log/orux-backup.log 2>&1
```

Verificá que esté: `crontab -l`. Mirá el log al día siguiente:
`tail /var/log/orux-backup.log`.

### 3.4 Restore (DESTRUCTIVO — sobrescribe la DB actual)

```bash
# 1) Si el archivo está en DO Spaces, traélo:
AWS_ACCESS_KEY_ID=$DO_SPACES_KEY AWS_SECRET_ACCESS_KEY=$DO_SPACES_SECRET \
  aws s3 cp s3://$DO_SPACES_BUCKET/orux-db/orux-20260523T030000Z.sql.gz \
    ./backups/ --endpoint-url $DO_SPACES_ENDPOINT

# 2) Restore (pide CONFIRM=yes explícito):
make db-restore FILE=./backups/orux-20260523T030000Z.sql.gz CONFIRM=yes
```

`pg_dump` fue invocado con `--clean --if-exists` así que el restore
empieza con `DROP`s — los datos actuales se pierden. Tomá un backup
fresco antes de restaurar uno viejo, por si el viejo está roto.

### 3.5 Los repos git de los equipos también son estado

`pg_dump` cubre **solo metadatos** (users, teams, ownership, invites).
El contenido de los archivos vive como repositorios git reales en el
volumen `orux-data` (`/data/ws/<team_id>/`). Para un backup completo:

```bash
docker run --rm -v orux_orux-data:/data -v $(pwd)/backups:/out \
  alpine tar czf /out/orux-ws-$(date -u +%Y%m%dT%H%M%SZ).tar.gz -C /data ws
```

Y subirlo al bucket con el mismo patrón de `aws s3 cp`. La mayoría de
recovery cases se resuelven con solo Postgres (los repos siguen estando
en el volumen del host); el tar del workspace es para "perdí el VPS
entero".

---

## 4. Operaciones de equipo manual (psql)

Si necesitás tocar la DB directamente (ej: marcar a un equipo como
Premium sin Stripe activo):

```bash
docker compose exec postgres psql -U orux -d orux
```

Comandos útiles dentro de psql:

```sql
-- Ver equipos y plan actual.
SELECT id, nombre, plan, stripe_subscription_id, miembros FROM teams;

-- Marcar un equipo como Premium MANUALMENTE (favor, prueba, etc.):
UPDATE teams SET plan = 'premium' WHERE id = '<team_id>';

-- Volver a Free:
UPDATE teams SET plan = 'free', stripe_subscription_id = NULL
  WHERE id = '<team_id>';

-- Ver miembros de un equipo:
SELECT u.username, m.rol
  FROM team_members m
  JOIN users u ON u.id = m.user_id
  WHERE m.team_id = '<team_id>';

-- Promover un usuario a admin de su equipo:
UPDATE team_members SET rol = 'admin'
  WHERE team_id = '<team_id>' AND user_id = '<user_id>';

-- Borrar invites usados o expirados (housekeeping):
DELETE FROM invites WHERE used_at IS NOT NULL OR expires_at < NOW();
```

Salir: `\q`.

---

## 5. Rotación de secretos

### 5.1 `ORUX_SESSION_SECRET` (firma de tokens de sesión)

Generar uno nuevo + actualizar `.env`. **Importante**: rotar este secreto
INVALIDA todas las sesiones abiertas — todos los usuarios tienen que
volver a loguearse. Hacelo en horario tranquilo.

```bash
NUEVO=$(openssl rand -hex 32)
# Editar .env: reemplazar ORUX_SESSION_SECRET=...
make restart        # los contenedores leen el .env nuevo
```

### 5.2 `ORUX_ADMIN_TOKEN` (firma de la consola de operador)

Mismo procedimiento. Rotación invalida tu propia sesión de operador (en
`/admin`); volvés a loguear con la misma cuenta + password.

### 5.3 Credenciales de Stripe (`STRIPE_SECRET_KEY`, `STRIPE_WEBHOOK_SECRET`)

Si rotás la API key, regenerala en el dashboard de Stripe, actualizá
`.env`, `make restart`. El webhook secret se rota desde el endpoint
correspondiente en el dashboard de Stripe.

### 5.4 OAuth GitHub (`ORUX_GITHUB_CLIENT_SECRET`)

GitHub → OAuth App → Generate a new client secret. El viejo sigue
funcionando hasta que lo borres en GitHub. Actualizá `.env` y reiniciá.

---

## 6. Troubleshooting común

### 6.1 "Aparecen archivos `undefined` en la UI / clientes ven cosas raras"

Casi siempre = **servidor zombi** en puerto 8765 corriendo una versión
vieja del protocolo. Antes de debuggear lógica:

```bash
ps aux | grep python | grep -v grep
lsof -i:8765
```

Matá el zombi (`kill <PID>`) o `make rebuild`.

### 6.2 "El análisis de impacto no se ve / sale aproximado"

El cliente muestra un chip discreto (`ast`, `tree-sitter`, `regex`) en el
Inspector cuando LSP NO se usó — eso es por diseño desde la capa
anti-degradación. Si el chip aparece SIEMPRE para Python, probablemente
pyright no levanta. Mirá:

```bash
docker compose logs orux | grep -i "pyright\|lsp"
```

Si pyright se queja de `libatomic.so.1`, el `Dockerfile` ya la instala —
forzá `make rebuild-orux`. Si el cache de pyright es read-only,
chequeá permisos de `/opt/pyright` en la imagen.

### 6.3 "El healthcheck del orux container falla"

El healthcheck abre un WebSocket real al puerto 8765 (no un connect TCP
crudo, ver `Dockerfile:105`). Si está fallando:

- Si los logs del server gritan `EOFError: stream ends after 0 bytes`
  cada 30s, ese ruido es **histórico** — el fix está en main hace
  tiempo. Si lo ves ahora, posiblemente tenés una imagen vieja sin
  rebuildear: `make rebuild-orux`.
- Si el server WS realmente está caído, los logs del container `orux`
  van a tener el traceback antes de la caída.

### 6.4 "Cae la conexión WS de un cliente"

El cliente ahora **reintenta solo** (backoff exponencial 500ms → 30s).
El usuario ve `desconectado → conectando → conectado` y sigue. Si NUNCA
reconecta, es que el server WS está realmente abajo: mirá `make ps`.

### 6.5 "Stripe webhook no llega"

```bash
docker compose logs api | grep -i "stripe\|webhook"
```

Verificá:
- El endpoint registrado en el dashboard de Stripe apunta a
  `https://<dominio>/api/v1/billing/webhook`.
- Los eventos suscritos son **exactamente** `checkout.session.completed`
  y `customer.subscription.deleted`.
- `STRIPE_WEBHOOK_SECRET` en `.env` coincide con el que muestra el
  dashboard del endpoint.
- Tras cambiar el `.env`: `make restart`.

---

## 7. Comandos útiles

```bash
make help                                # lista todos los make targets
make build                               # construye TODAS las imágenes (no levanta)
make up                                  # levanta TODO (sin buildear)
make rebuild                             # down + build + up (lo más usado tras cambios)
make down                                # baja todo (los datos quedan)
make restart                             # reload del .env y restart
make logs                                # logs combinados
make sh                                  # shell dentro del container orux
make ps                                  # estado de los 4 containers
make test                                # tests del backend en local
make db-backup                           # backup Postgres
make db-restore FILE=... CONFIRM=yes     # restore Postgres

# Por servicio (svc ∈ orux, api, postgres, caddy):
make build-<svc>                         # rebuild de UN servicio (postgres NO; usar `make pull`)
make up-<svc>                            # levantar UN servicio (sube sus deps)
make stop-<svc>                          # parar UN servicio (sin borrarlo)
make restart-<svc>                       # reiniciar UN servicio
make rebuild-<svc>                       # build + recreate de UN servicio (no toca los demás)
make logs-<svc>                          # logs en vivo de UN servicio
make sh-<svc>                            # shell del contenedor (sh-postgres = psql)

make pull                                # baja imágenes públicas nuevas (postgres)
make build-nocache                       # rebuild forzado ignorando cache (emergencia)
docker system df                         # cuánto espacio está usando docker
docker system prune -af                  # limpieza agresiva (ojo: borra
                                         # imágenes/cache; no toca volúmenes)
```

---

## 8. Durante el spike de promoción (monitoreo en vivo)

VPS actual: **4 vCPU · 8 GB RAM** (DigitalOcean Basic Regular, $48/mo, resize en caliente desde el panel).

Topes del `docker-compose.yml` configurados:
| Servicio | CPU tope | RAM tope |
|---|---|---|
| `orux` | 3.0 | 4 G |
| `api` | 0.5 | 768 M |
| `postgres` | 1.0 | 1.5 G |
| `caddy` | 0.5 | 256 M |
| **Total cap** | **5.0** (125% del físico, oversubscription OK) | **6.5 G** (82%, deja 1.4 G para OS) |

### Comandos para mirar en vivo

```bash
# 1) Top en el host: visión global (CPU, RAM, swap)
htop                                      # si no está: apt install htop

# 2) Uso real POR contenedor (en vivo, refresh cada 2s)
docker stats

# 3) Logs combinados con tail corto (no inunda terminal)
docker compose logs -f --tail=100

# 4) Errores reportados desde el cliente (capa 35)
docker compose logs api | grep client_error

# 5) Pageviews que están llegando (analytics propio)
docker compose logs api | grep client_track | tail -20

# 6) Salud de cada container
make ps                                    # busca "(healthy)" en los 4
```

### Criterios numéricos para resize (no opinión: número)

**Subir a 8 vCPU/16 GB ($96/mo)** si CUALQUIERA de estos se sostiene >10 minutos:
- CPU del host (en `htop`) > **75%** sostenido
- RAM del host > **85%** sostenida (o aparece **swap usage**)
- `docker stats` muestra que `orux` está al **>90% de su tope** (3.7+ CPU o 3.6+ G RAM)
- `make ps` reporta `(unhealthy)` recurrente

**Bajar a 2vCPU/4GB** si tras 7-14 días el uso sostenido del host está <30% CPU y <50% RAM en horas pico.

**Resize en caliente desde DO**: panel del droplet → Resize → elegí plan → "Resize Disk and CPU". Tarda ~5 min; volúmenes y red persisten; el container va a reiniciar (downtime ~30-60s; el reconnect WS del cliente lo absorbe). Tras el resize, NO hay que tocar nada del compose si subís — los límites son topes; si bajás a 2vCPU/4GB, revisar/reducir topes del `docker-compose.yml` antes del próximo `make restart`.

### Qué mirar en los primeros 30 minutos del anuncio

```bash
# Terminal A: monitor de recursos
watch -n 5 'docker stats --no-stream'

# Terminal B: errores del cliente (si algo se rompe en vivo, acá lo ves)
docker compose logs -f api | grep --line-buffered "client_error\|ERROR\|WARN"

# Terminal C: tráfico de la landing
docker compose logs -f api | grep --line-buffered client_track
```

Si algo se ve mal y no es obvio el por qué: `docker compose logs --tail=300 orux > /tmp/orux.log` (para revisar tranquilo). Los logs de api y orux NO se rotan automáticamente — si crecen mucho durante el spike, `docker compose logs api > /var/log/orux-api.log && docker compose restart api` (el archivo de log del container es transitorio).

---

## 9. Antes de anunciar / ir a producción real (checklist)

- [ ] `.env` completo con todos los secretos reales (no defaults).
- [ ] `ORUX_SITE_ADDRESS` apunta al dominio real (no `localhost`).
- [ ] Stripe en **live mode** (`sk_live_...`, `whsec_...`) si vas a cobrar.
- [ ] DO Spaces configurado y `make db-backup` sube sin error.
- [ ] Cron del backup agregado en el host.
- [ ] OAuth GitHub redirect apunta al dominio real (no localhost).
- [ ] `make up` arranca con los 4 containers `(healthy)` en `make ps`.
- [ ] Probar end-to-end: signup nuevo → crear team → invitar → editar
      colaborativo → ctrl+S → ver impacto.
