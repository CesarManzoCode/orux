# Operations: Backup

## Qué se backupea

- **Postgres** (`/data/postgres`): metadatos críticos (users, teams, ownership, proposals, webhooks). Backup diario.
- **Secret HMAC** (`/data/orux/secret`): si se pierde, todas las sesiones vivas se invalidan (los devs vuelven a login). Backup manual cuando se rota.
- **Workspaces** (`/data/orux/ws/<team_id>/`): cada uno es un repo git. **NO se backupea sistemáticamente** — los devs son responsables de pushear a su remoto. Si el VPS se pierde, lo no-pusheado se pierde.

## Lo NO crítico (regenerable)

- **Caddy certs** (`/data/caddy`): re-emitibles. Si se pierden, Let's Encrypt los regenera al boot.
- **`processed_webhooks`** (parte de Postgres): la purga de 30 días los borra igual.
- **Logs de Docker**: ephemeral por design.

## Script `scripts/backup-db.sh`

```bash
#!/bin/bash
# scripts/backup-db.sh
# Backup atómico de Postgres con timestamp. Opcional sync a DO Spaces.

set -euo pipefail

# Carga env del host (.env del docker-compose)
source /opt/orux/.env

FECHA=$(date +%Y-%m-%d-%H%M%S)
DEST=/data/backups
mkdir -p "$DEST"

# pg_dump dentro del contenedor postgres
docker compose -f /opt/orux/docker-compose.yml exec -T postgres \
    pg_dump -U orux -d orux -F c -Z 9 \
    > "$DEST/orux-$FECHA.dump"

# Rotación local: mantener últimos 7 días
find "$DEST" -name "orux-*.dump" -mtime +7 -delete

# Opcional: sync a DO Spaces (si configurado)
if [[ -n "${BACKUP_S3_BUCKET:-}" ]]; then
    aws s3 cp "$DEST/orux-$FECHA.dump" \
        "s3://$BACKUP_S3_BUCKET/postgres/orux-$FECHA.dump" \
        --endpoint-url="${BACKUP_S3_ENDPOINT:-https://nyc3.digitaloceanspaces.com}"
fi

echo "✓ backup completo: orux-$FECHA.dump"
```

### Decisiones

- **Formato custom (`-F c`)**: comprimido, restorable con `pg_restore`, permite restore selectivo.
- **Nivel 9 compression (`-Z 9`)**: backup chico (~MB para 100 equipos), restore lento. Trade-off OK porque hacemos backup diario y restore raro.
- **Rotación local**: 7 días (ajustable). Mantiene `/data/backups/` chico.
- **DO Spaces opcional**: off-site backup. Sin él, un fallo de disco del VPS pierde los backups locales también.

## Schedule

Cron en el host:

```cron
# /etc/cron.d/orux-backup
0 4 * * * root /opt/orux/scripts/backup-db.sh >> /var/log/orux-backup.log 2>&1
```

4 AM UTC diario. Bajo tráfico esperado (público inicial es founders/dev, no usuarios masivos).

## Manual

```bash
make db-backup
# corre el script + muestra el resultado
```

Útil antes de:

- Aplicar una migración manual.
- Hacer pruebas destructivas en producción.
- Cambiar config crítica.

## Restore

```bash
make db-restore
```

Pide confirmación interactiva. Restaura del último archivo en `/data/backups/`. **Destructivo**: la DB actual se borra.

Para restaurar de un backup específico:

```bash
docker compose stop orux api
docker compose exec -T postgres dropdb -U orux orux
docker compose exec -T postgres createdb -U orux orux
gunzip -c /data/backups/orux-2026-05-20.dump.gz | \
    docker compose exec -T postgres pg_restore -U orux -d orux
docker compose start orux api
```

Tras restore: verificar healthcheck (`curl /health`) y smoke test rápido (login + entrar a un equipo).

## Backup del secret HMAC

`/data/orux/secret` se backupea **manualmente** cuando se rota (no diariamente, porque cambia raramente).

```bash
cp /data/orux/secret /data/backups/secret-$(date +%Y-%m-%d).bak
chmod 600 /data/backups/secret-*.bak
```

Si el secret se pierde y NO hay backup: los tokens vivos no valen → los devs deben re-loguear. No es catastrófico, pero rompe la experiencia.

Si el secret se filtra: rotarlo (ver [`runbook.md`](runbook.md) — Rotar el secret HMAC). Los tokens vivos quedan inválidos automáticamente.

## Backup del repo de cada equipo (`/data/orux/ws/<team_id>/`)

**No hacemos backup sistemático.** Cada workspace es un repo git real. La estrategia:

- **El dev pushea a su remoto** (GitHub, GitLab, etc.) regularmente. El producto promueve esto: el botón "Push" está en el IDE.
- **Si el VPS se pierde**, los devs hacen `git clone` de su remoto y arrancan.
- **Lo no-pusheado se pierde**. Mitigación social: pedir a los equipos que pusheen al final del día.

Por qué NO backupear:

- Volumen: 100 equipos × 100 MB promedio = 10 GB diarios. Backup masivo.
- Privacidad: el código del cliente es del cliente. Manejarlo + backupearlo nos hace responsables.
- Redundancia con git: el dev YA tiene mecanismo de backup (push a remoto). Duplicarlo no agrega seguridad real.

Si en el futuro hay equipos enterprise con SLA de respaldo: feature paga aparte (backup-as-a-service del workspace).

## Recovery time / point objectives

**RPO** (Recovery Point Objective — qué tan reciente debe ser la restauración):

- Postgres: ~24h en el peor caso (si se cae justo antes del backup nocturno). Aceptable para fase de prototipo.
- Workspaces: indefinido (responsabilidad del dev pushear).

**RTO** (Recovery Time Objective — tiempo para volver a estar operativo):

- Postgres restore: ~5 min (100 equipos × MBs cada uno).
- Rebuild de imágenes: ~2 min.
- Re-emisión de certs Caddy: ~30s.
- **Total**: ~10 min desde "VPS muerto" hasta "operativo de nuevo" si tenés el DNS y los backups a mano.

En la práctica, el cuello de botella es traer los backups del off-site (DO Spaces) — depende del ancho de banda.

## Disaster recovery completo

Suponiendo VPS catastróficamente perdido:

1. **Provisionar VPS nuevo** (~10 min en DigitalOcean).
2. **Restaurar `/data/postgres`** desde DO Spaces (~5 min).
3. **Restaurar `/data/orux/secret`** desde backup manual (~1 min).
4. **`git clone`** del repo del proyecto en `/opt/orux` (~30s).
5. **Copiar `.env`** con las credenciales (Stripe, OAuth, etc.) desde un password manager (~1 min).
6. **`make redeploy`** (~3 min).
7. **DNS update** si la IP cambió (~5 min propagación).
8. **Anunciar a los devs** que vuelvan a loguearse (sus tokens HMAC siguen siendo válidos si el secret se restauró bien).

Total: ~30 min de RTO si tenés disciplina con backups + credentials en password manager.

## Cosas a hacer (defer)

- **Backup automatizado del directorio `/data/orux`** (no solo Postgres): incluiría secret + workspaces. Pero workspaces masivos = caro. Probablemente solo secret + ws/.git (no working tree).
- **Backup verificado**: hoy el script genera backups pero NO valida que restauren bien. Mejora: un `make db-backup-verify` que hace restore a una DB scratch y compara.
- **Restore selectivo**: hoy solo "todo o nada". Mejora: `make db-restore --team <id>` que restaura solo las filas de ese equipo.

Estas mejoras son DIFERIDAS hasta que aparezca el caso real (cliente con SLA, incidente).
