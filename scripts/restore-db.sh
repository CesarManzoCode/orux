#!/usr/bin/env bash
# Restaurar la DB de Orux desde un backup hecho por backup-db.sh.
#
# DESTRUCTIVO: sobrescribe el contenido actual. pg_dump fue invocado con
# --clean --if-exists, así que el dump empieza con DROPs — restaurar sobre
# una DB con datos los borra. Por eso pedimos CONFIRM=yes explícito.
#
# Uso:
#   CONFIRM=yes ./scripts/restore-db.sh ./backups/orux-XXXX.sql.gz
#
# Para descargar un backup de DO Spaces:
#   AWS_ACCESS_KEY_ID=$DO_SPACES_KEY AWS_SECRET_ACCESS_KEY=$DO_SPACES_SECRET \
#     aws s3 cp s3://$DO_SPACES_BUCKET/orux-db/orux-XXXX.sql.gz ./backups/ \
#     --endpoint-url $DO_SPACES_ENDPOINT

set -euo pipefail

if [ $# -lt 1 ]; then
  echo "uso: CONFIRM=yes $0 <ruta-al-backup.sql.gz>" >&2
  exit 2
fi

BACKUP_FILE="$1"
PG_SERVICE="${PG_SERVICE:-postgres}"
PG_USER="${PG_USER:-orux}"
PG_DB="${PG_DB:-orux}"

if [ ! -f "$BACKUP_FILE" ]; then
  echo "[restore] ERROR: no existe $BACKUP_FILE" >&2
  exit 1
fi

if [ "${CONFIRM:-}" != "yes" ]; then
  echo "[restore] ABORT: esto SOBREESCRIBE la DB actual. Re-corré con CONFIRM=yes:" >&2
  echo "  CONFIRM=yes $0 $BACKUP_FILE" >&2
  exit 1
fi

echo "[restore] $(date -u +%FT%TZ) ← $BACKUP_FILE"

# El dump fue gzipeado al backupear: lo descomprimimos en pipe directo
# a psql dentro del contenedor. `exec -T` desactiva el TTY que rompería
# el pipe.
if gunzip -c "$BACKUP_FILE" | docker compose exec -T "$PG_SERVICE" \
       psql -U "$PG_USER" -d "$PG_DB" -v ON_ERROR_STOP=1 -q >/dev/null; then
  echo "[restore] ✓ OK"
else
  echo "[restore] ERROR: psql falló" >&2
  exit 1
fi
