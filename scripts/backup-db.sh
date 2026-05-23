#!/usr/bin/env bash
# Backup de la base de metadatos de Orux (Postgres en docker compose).
#
# Estrategia: dos copias por backup.
#   1) Local en ./backups/ con retención corta (7 días) — rollback rápido.
#   2) Off-site en DO Spaces (compatible S3) si las credenciales están
#      seteadas — recovery cuando el VPS entero se va abajo (single point
#      of failure si solo guardás local).
#
# Sin las env vars de DO el script sigue funcionando con SOLO el local:
# tener algo siempre es mejor que tener nada porque faltó configurar S3.
#
# Uso:
#   ./scripts/backup-db.sh                  # backup local (+ S3 si está)
#   make db-backup                          # idem, vía Makefile
#
# Cron sugerido (en el host, no en el contenedor):
#   0 3 * * * cd /ruta/al/repo && ./scripts/backup-db.sh >> /var/log/orux-backup.log 2>&1
#
# Restore: ./scripts/restore-db.sh ./backups/orux-XXXX.sql.gz

set -euo pipefail

# Directorios y configuración base. BACKUPS_DIR override-able por env var
# por si querés guardarlos en otro disco / volumen en el VPS.
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# Cargar .env del repo si existe. Este script corre en el HOST, no en un
# container — docker compose lee el .env solo para inyectarlo a los
# servicios, así que sin esto las DO_SPACES_* del .env no llegan acá.
# `set -a` exporta automáticamente lo que el source asigne; lo apagamos al
# salir para no contaminar el resto. Variables del shell del usuario YA
# son visibles (heredadas del entorno) y NO se pisan si vienen en el .env
# después, porque source asigna en el orden del archivo.
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  # shellcheck disable=SC1090,SC1091
  . "$REPO_ROOT/.env"
  set +a
fi

BACKUPS_DIR="${BACKUPS_DIR:-$REPO_ROOT/backups}"
RETENTION_DIAS="${RETENTION_DIAS:-7}"

# Identidad del contenedor y la DB. Los defaults coinciden con
# docker-compose.yml (POSTGRES_USER=orux, POSTGRES_DB=orux). Si los cambias
# allá, override-eá acá.
PG_SERVICE="${PG_SERVICE:-postgres}"
PG_USER="${PG_USER:-orux}"
PG_DB="${PG_DB:-orux}"

mkdir -p "$BACKUPS_DIR"

TIMESTAMP="$(date -u +%Y%m%dT%H%M%SZ)"
FILENAME="orux-${TIMESTAMP}.sql.gz"
BACKUP_PATH="$BACKUPS_DIR/$FILENAME"

echo "[backup] $(date -u +%FT%TZ) → $BACKUP_PATH"

# --- 1) Backup local ----------------------------------------------------------
# `docker compose exec -T` evita pedir TTY (lo necesitamos para piping).
# pg_dump → gzip en el host: nunca se materializa el .sql sin comprimir, así
# si la DB es grande no llenamos el disco con el dump crudo.
if ! docker compose exec -T "$PG_SERVICE" \
       pg_dump -U "$PG_USER" -d "$PG_DB" --no-owner --clean --if-exists \
     | gzip -9 > "$BACKUP_PATH"; then
  echo "[backup] ERROR: pg_dump falló" >&2
  rm -f "$BACKUP_PATH"
  exit 1
fi

# El gzip puede salir 0 con archivo vacío si pg_dump produjo cero bytes.
# Detectamos eso antes de que el "backup vacío" se sienta seguro.
TAMANO_BYTES="$(stat -c%s "$BACKUP_PATH" 2>/dev/null || stat -f%z "$BACKUP_PATH")"
if [ "$TAMANO_BYTES" -lt 100 ]; then
  echo "[backup] ERROR: backup demasiado chico ($TAMANO_BYTES bytes) — algo salió mal" >&2
  rm -f "$BACKUP_PATH"
  exit 1
fi

echo "[backup] ✓ local OK ($TAMANO_BYTES bytes)"

# --- 2) Retención local -------------------------------------------------------
# Borra los backups locales más viejos que RETENTION_DIAS. NO toca los del
# bucket — DO Spaces tiene su propia retención (configurada del lado DO).
find "$BACKUPS_DIR" -name 'orux-*.sql.gz' -type f -mtime +"$RETENTION_DIAS" -print -delete \
  | sed 's/^/[backup] (limpieza) /' || true

# --- 3) Push opcional a DO Spaces --------------------------------------------
# Cerrado por defecto: si faltan credenciales o el bucket, NO sube y NO falla
# (el backup local ya está, no queremos romper el cron por config faltante).
# Activación: setear las 4 env vars y tener `aws` CLI en el host.
if [ -z "${DO_SPACES_BUCKET:-}" ] \
   || [ -z "${DO_SPACES_ENDPOINT:-}" ] \
   || [ -z "${DO_SPACES_KEY:-}" ] \
   || [ -z "${DO_SPACES_SECRET:-}" ]; then
  echo "[backup] (off-site desactivado: DO_SPACES_* sin configurar — ver RUNBOOK)"
  exit 0
fi

if ! command -v aws >/dev/null 2>&1; then
  echo "[backup] WARN: AWS CLI no está instalado; salto el push a DO Spaces" >&2
  exit 0
fi

DO_PREFIX="${DO_SPACES_PREFIX:-orux-db}"
S3_URI="s3://${DO_SPACES_BUCKET}/${DO_PREFIX}/${FILENAME}"
echo "[backup] subiendo a $S3_URI"

# Las credenciales se pasan por env vars de la subshell — no tocamos
# ~/.aws/credentials (el cron puede correr sin home propio). DO Spaces es
# S3-compatible: lo único distinto es el --endpoint-url.
if AWS_ACCESS_KEY_ID="$DO_SPACES_KEY" \
   AWS_SECRET_ACCESS_KEY="$DO_SPACES_SECRET" \
   aws s3 cp "$BACKUP_PATH" "$S3_URI" \
     --endpoint-url "$DO_SPACES_ENDPOINT" \
     --only-show-errors; then
  echo "[backup] ✓ off-site OK"
else
  # Off-site falló pero el local ya está: no es razón para salir con error
  # (el cron lo logueará y el operador puede investigar).
  echo "[backup] WARN: push a DO Spaces falló; el backup local SÍ está OK" >&2
  exit 0
fi
