# Atajos de deploy y desarrollo de Orux. `make` o `make help` lista todo.
#
# Filosofía: nunca tenés que escribir `docker compose ...` a mano. Todo lo
# rutinario (build, up, down, restart, rebuild, logs, sh, ps) tiene target
# global Y target por servicio.
#
# Operaciones globales      Por servicio (svc ∈ orux, api, postgres, caddy)
# ----------------------    ---------------------------------------------
#   make build                make build-orux   (postgres NO tiene build:
#   make up                   make up-orux        usa imagen pública, ver
#   make down                 make stop-orux      `make pull`)
#   make restart              make restart-orux
#   make rebuild              make rebuild-orux
#   make logs                 make logs-orux
#   make ps                   make sh-orux
#
# Diferencias clave con la versión vieja:
#   - `make up` YA NO buildea. Si nunca buildeaste, corré primero
#     `make build` o usá el atajo `make rebuild` (= down + build + up).
#   - Cuando cambies código y querés reflejarlo en runtime, lo normal es:
#       make rebuild           (todo)
#       make rebuild-orux      (sólo un servicio, sin tocar los demás)
#
# Flujo típico:
#   make build           # primera vez o tras cambios en deps/Dockerfile
#   make up              # levantar rápido (usa la imagen ya construida)
#   make rebuild         # cuando algo no agarra el cambio
#   make rebuild-caddy   # frontend nuevo, sin reiniciar el server WS

.DEFAULT_GOAL := help
.PHONY: help \
        build up down restart rebuild logs ps sh pull build-nocache \
        build-orux build-api build-caddy \
        up-orux up-api up-postgres up-caddy \
        stop-orux stop-api stop-postgres stop-caddy \
        restart-orux restart-api restart-postgres restart-caddy \
        rebuild-orux rebuild-api rebuild-caddy \
        logs-orux logs-api logs-postgres logs-caddy \
        sh-orux sh-api sh-postgres sh-caddy \
        test dev db-backup db-restore

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk -F':.*## ' '{printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

# ============================================================
# Operaciones globales (todos los servicios)
# ============================================================
build: ## Construye TODAS las imágenes (no levanta nada)
	docker compose build

up: ## Levanta TODO en segundo plano (usa imágenes existentes; NO buildea)
	docker compose up -d --remove-orphans

down: ## Apaga y elimina los contenedores (los DATOS quedan en los volúmenes)
	docker compose down --remove-orphans

restart: ## Reinicia TODOS los contenedores en caliente
	docker compose restart

rebuild: ## down + build + up (rebuild completo: el atajo más usado tras cambios)
	docker compose down --remove-orphans
	docker compose build
	docker compose up -d --remove-orphans

logs: ## Sigue los logs combinados de TODOS los servicios
	docker compose logs -f

ps: ## Estado de los 4 contenedores
	docker compose ps

sh: ## Shell en el contenedor del server WS (alias de sh-orux)
	docker compose exec orux sh

pull: ## Descarga imágenes públicas nuevas (postgres)
	docker compose pull postgres

build-nocache: ## Rebuild ignorando el cache de Docker (emergencia: cuando un cambio no se ve)
	docker compose build --no-cache

# ============================================================
# Build por servicio (postgres usa imagen pública: `make pull`)
# ============================================================
build-orux: ## Construye sólo la imagen del server WS
	docker compose build orux

build-api: ## Construye sólo la imagen de la API (operador/OAuth/billing)
	docker compose build api

build-caddy: ## Construye sólo la imagen de Caddy (incluye el frontend compilado)
	docker compose build caddy

# ============================================================
# Up por servicio (compose arranca también las deps si faltan)
# ============================================================
up-orux: ## Levanta el server WS (sube postgres si no estaba)
	docker compose up -d orux

up-api: ## Levanta la API (sube postgres si no estaba)
	docker compose up -d api

up-postgres: ## Levanta sólo Postgres
	docker compose up -d postgres

up-caddy: ## Levanta Caddy (sube orux + api si no estaban)
	docker compose up -d caddy

# ============================================================
# Stop por servicio (NO borra el contenedor; reanudable con up-<svc>)
# ============================================================
stop-orux: ## Detiene el server WS
	docker compose stop orux

stop-api: ## Detiene la API
	docker compose stop api

stop-postgres: ## Detiene Postgres (cuidado: orux y api dependen de él)
	docker compose stop postgres

stop-caddy: ## Detiene Caddy
	docker compose stop caddy

# ============================================================
# Restart por servicio
# ============================================================
restart-orux: ## Reinicia el server WS
	docker compose restart orux

restart-api: ## Reinicia la API
	docker compose restart api

restart-postgres: ## Reinicia Postgres
	docker compose restart postgres

restart-caddy: ## Reinicia Caddy
	docker compose restart caddy

# ============================================================
# Rebuild por servicio (build + recreate sólo ese servicio)
# ============================================================
rebuild-orux: ## Rebuild + recreate del server WS (no toca los demás)
	docker compose build orux
	docker compose up -d --no-deps --force-recreate orux

rebuild-api: ## Rebuild + recreate de la API (no toca los demás)
	docker compose build api
	docker compose up -d --no-deps --force-recreate api

rebuild-caddy: ## Rebuild + recreate de Caddy / frontend (no toca los demás)
	docker compose build caddy
	docker compose up -d --no-deps --force-recreate caddy

# ============================================================
# Logs por servicio
# ============================================================
logs-orux: ## Logs del server WS
	docker compose logs -f orux

logs-api: ## Logs de la API
	docker compose logs -f api

logs-postgres: ## Logs de Postgres
	docker compose logs -f postgres

logs-caddy: ## Logs de Caddy
	docker compose logs -f caddy

# ============================================================
# Shell por servicio
# ============================================================
sh-orux: ## Shell en el contenedor del server WS
	docker compose exec orux sh

sh-api: ## Shell en el contenedor de la API
	docker compose exec api sh

sh-postgres: ## psql en Postgres (DB orux, usuario orux)
	docker compose exec postgres psql -U orux -d orux

sh-caddy: ## Shell en el contenedor de Caddy
	docker compose exec caddy sh

# ============================================================
# Desarrollo local (sin docker)
# ============================================================
test: ## Corre la suite de tests del backend en local (no en docker)
	cd backend && python -m pytest -q

dev: ## Server WS local para desarrollo (sin docker)
	cd backend && python -m orux.server

# ============================================================
# Base de datos
# ============================================================
db-backup: ## Backup de Postgres (local en ./backups; off-site si DO_SPACES_* está seteado)
	./scripts/backup-db.sh

db-restore: ## Restaurar la DB. Uso: make db-restore FILE=./backups/orux-XXX.sql.gz CONFIRM=yes
	@if [ -z "$(FILE)" ]; then echo "uso: make db-restore FILE=./backups/orux-XXXX.sql.gz CONFIRM=yes"; exit 2; fi
	CONFIRM=$(CONFIRM) ./scripts/restore-db.sh "$(FILE)"
