# Housekeeping pre-anuncio · VPS

Lo último antes del anuncio público. Tiempo estimado: **15–25 min**, todo
desde el VPS (`ssh root@orux-prod` o como te conectes).

Si algo de acá no sale como dice "Esperado", parar el anuncio y avisarme.

---

## 1 · `.env` sin defaults inseguros

Desde el host, en la raíz del repo:

```bash
cd ~/laidea
# Listar las vars del .env sin imprimir secretos: solo nombre + si está vacío.
awk -F= '/^[A-Z]/ { if ($2 == "") print $1 ": VACÍO"; else print $1 ": OK"; }' .env
```

**Esperado** (todo "OK" salvo donde marco `puede vaciar`):

| Variable | Estado | Notas |
|---|---|---|
| `ORUX_SITE_ADDRESS` | OK | debe ser `orux.space` (NO `localhost`) |
| `ORUX_ADMIN_USER` | OK | tu cuenta de operador, ya registrada |
| `ORUX_ADMIN_TOKEN` | OK | `openssl rand -hex 32`, ≥ 64 chars |
| `ORUX_SESSION_SECRET` | OK | `openssl rand -hex 32`, ≥ 64 chars |
| `ORUX_GITHUB_CLIENT_ID` | OK *o vacío* | si está vacío, OAuth GitHub se desactiva (botón no aparece) |
| `ORUX_GITHUB_CLIENT_SECRET` | OK *o vacío* | idem |
| `ORUX_OAUTH_REDIRECT` | OK *o vacío* | debe terminar en `/oauth/github/callback` exacto |
| `STRIPE_SECRET_KEY` | OK *o vacío* | si vas a cobrar: `sk_live_...` (NO `sk_test_...`); si no, vacío y `/api/v1/billing/*` da 503 limpio |
| `STRIPE_WEBHOOK_SECRET` | OK *o vacío* | idem; debe coincidir con el endpoint registrado en Stripe |
| `ORUX_PUBLIC_URL` | OK *o vacío* | si Stripe está activo: `https://orux.space` |
| `STRIPE_PRICE_AMOUNT` | OK | el precio real por asiento (en centavos) |
| `DO_SPACES_BUCKET` | OK | el bucket de DigitalOcean para backups off-site |
| `DO_SPACES_*` | OK | las otras 3 credenciales |

**Verificar puntualmente**:

```bash
# Que las longitudes de los secretos sean serias (≥ 32 chars en HEX = 64)
awk -F= '/^ORUX_(ADMIN_TOKEN|SESSION_SECRET)=/{ print $1, length($2) }' .env
# Esperado: ambos ≥ 64.

# Que ORUX_SITE_ADDRESS no quedó en "localhost"
grep '^ORUX_SITE_ADDRESS=' .env
# Esperado: ORUX_SITE_ADDRESS=orux.space

# Que Stripe sea LIVE (no TEST) si vas a cobrar
grep '^STRIPE_SECRET_KEY=' .env | grep -oE 'sk_(test|live)_'
# Esperado: sk_live_  (si vacío, el output es vacío, OK también)
```

---

## 2 · Limpiar data de testing en Postgres

```bash
docker compose exec postgres psql -U orux -d orux
```

Adentro de psql, queries de **revisión** primero (cero destructivas):

```sql
-- Cuántos usuarios totales y de cuáles tipos
SELECT
  count(*) FILTER (WHERE username LIKE 'gh:%') AS oauth_github,
  count(*) FILTER (WHERE username NOT LIKE 'gh:%') AS locales,
  count(*) AS total
FROM users;

-- Usuarios "smoke-*" / "test-*" / similares (lo que sea que usaste vos para tests)
SELECT username, created_at
FROM users
WHERE username SIMILAR TO '(smoke|test|tmp|demo|prueba|abc|xyz|aaa|ana|bob)%'
ORDER BY created_at DESC;

-- Equipos creados (todos)
SELECT id, nombre, creador, plan, created_at FROM teams ORDER BY created_at DESC;

-- Invitaciones que ya expiraron o se usaron (candidatas a limpieza)
SELECT count(*) FROM invites
WHERE usado_at IS NOT NULL OR expires_at < NOW();
```

**Si querés borrar usuarios/teams de testing** (CUIDADO — IRREVERSIBLE):

```sql
-- Borrar TEAMS de testing primero (cascades a team_members + invites)
DELETE FROM teams WHERE nombre SIMILAR TO '(smoke|test|tmp|demo|prueba|abc)%';

-- Borrar USERS de testing (siempre y cuando no sean creadores de teams
-- vivos; la FK con ON DELETE RESTRICT va a bloquear si lo son)
DELETE FROM users WHERE username SIMILAR TO '(smoke|test|tmp|demo|prueba|abc)%';

-- Limpieza housekeeping siempre segura
DELETE FROM invites WHERE usado_at IS NOT NULL OR expires_at < NOW();

-- Si querés ver el estado final
SELECT count(*) FROM users;
SELECT count(*) FROM teams;
SELECT count(*) FROM invites;
```

> **NO** borrar tu cuenta operador (`ORUX_ADMIN_USER`) — si lo hacés, perdés el acceso a `/admin` hasta que la vuelvas a crear con el mismo username.

Salir con `\q`.

---

## 3 · Logs sin tracebacks ruidosos

```bash
# Ver últimos 200 lineas de orux (server WS). Buscamos tracebacks anómalos
# que un dev curioso vea con `docker logs` si se le ocurre snoopear.
docker compose logs --tail=200 orux | grep -iE "traceback|error|warn" | head -50

# Idem api
docker compose logs --tail=200 api | grep -iE "traceback|error|warn" | head -50
```

**Esperado**:
- `WARN` ocasionales son OK (rate limit alcanzado por tu propio smoke test, p. ej.).
- `Traceback` NO debería haber salvo si vos disparaste el bug a propósito.

**Si ves un traceback que no reconocés**, copiame las 10-20 líneas alrededor y lo analizamos.

Después de revisar, **rotar/limpiar logs** antes del anuncio para que el "minuto 1" arranque con disco vacío de ruido:

```bash
# Forzar rotación: reinicia los containers (~1 min downtime, el reconnect
# WS lo absorbe). No toca volúmenes.
make restart
```

---

## 4 · Backup pre-anuncio (sanity)

Antes de exponer al mundo, **un backup limpio**:

```bash
make db-backup
# Verificá la salida:
#   [backup] ✓ local OK (XXXX bytes)
#   [backup] ✓ off-site OK   (si DO_SPACES_* está configurado)

# Verificar que el archivo realmente se subió
AWS_ACCESS_KEY_ID=$DO_SPACES_KEY AWS_SECRET_ACCESS_KEY=$DO_SPACES_SECRET \
  aws s3 ls s3://$DO_SPACES_BUCKET/$DO_SPACES_PREFIX/ \
  --endpoint-url $DO_SPACES_ENDPOINT \
  | tail -5
# Esperado: ver el backup que acabás de hacer en lista
```

Si el cron del backup aún no está agregado:

```bash
crontab -e
# Pegá esto al final (ajustá la ruta del repo):
0 3 * * * cd /root/laidea && /usr/bin/make db-backup >> /var/log/orux-backup.log 2>&1
# Guardar y salir
crontab -l  # verificar
```

---

## 5 · Healthchecks de los 4 contenedores

```bash
make ps
```

**Esperado**: los 4 (`orux`, `api`, `postgres`, `caddy`) en estado **`(healthy)`** o equivalente. Si alguno está `(unhealthy)`:

```bash
docker compose logs --tail=50 <servicio>
```

Y reportame qué dice antes de promocionar.

---

## 6 · Probar que el dominio responde HTTPS válido

Desde tu **laptop** (no el VPS):

```bash
# Cert válido + HTTPS forzado
curl -I https://orux.space/
# Esperado: HTTP/2 200, sin warnings de cert
curl -I http://orux.space/
# Esperado: HTTP/1.1 301 o 308 → ubicación https://orux.space/  (HSTS)

# El cert sale del Let's Encrypt
openssl s_client -showcerts -connect orux.space:443 -servername orux.space </dev/null 2>/dev/null | grep -E "subject|issuer"
# Esperado: subject = orux.space, issuer = Let's Encrypt (R3 o E1)
```

---

## 7 · Volcado de tamaños (sanity numérica)

```bash
docker system df       # cuánto está ocupando docker
df -h /                # disco del host (los 160 GB del droplet)
free -h                # memoria del host
```

**Esperado**:
- `/` con uso < 50% (deja margen para backups, logs durante el spike, image rebuilds).
- `free -h`: con los 4 containers idle, el host debería tener ≥ 4 GB libres.

---

## Checklist final (todo OK = listo para promocionar)

- [ ] `.env` sin defaults inseguros (paso 1)
- [ ] Postgres limpio de cuentas/teams de testing (paso 2)
- [ ] Logs sin tracebacks anómalos + restart (paso 3)
- [ ] Backup limpio + cron configurado (paso 4)
- [ ] Los 4 containers `(healthy)` (paso 5)
- [ ] HTTPS válido + cert Let's Encrypt (paso 6)
- [ ] Disco < 50% y RAM con margen (paso 7)
- [ ] `docs/smoke-test.md` ejecutado sin 🔴 ni 🟡 críticos
