# Atajos de deploy y desarrollo. `make` o `make help` lista todo.
.DEFAULT_GOAL := help
.PHONY: help build up down restart logs ps sh test dev db-backup db-restore

help: ## Muestra esta ayuda
	@grep -E '^[a-zA-Z_-]+:.*## ' $(MAKEFILE_LIST) \
	  | awk -F':.*## ' '{printf "  \033[36m%-10s\033[0m %s\n", $$1, $$2}'

build: ## Construye la imagen del server
	docker compose build

up: ## Levanta todo (server + Caddy) en segundo plano
	docker compose up -d --build --remove-orphans --force-recreate

down: ## Apaga todo (contenedores y red; los DATOS quedan en el volumen)
	docker compose down --remove-orphans

restart: ## Reinicia los contenedores
	docker compose restart

logs: ## Sigue los logs
	docker compose logs -f

ps: ## Estado de los contenedores
	docker compose ps

sh: ## Abre una shell en el contenedor del server
	docker compose exec orux sh

test: ## Corre la suite de tests en local (no en docker)
	cd backend && python -m pytest -q

dev: ## Server en local para desarrollo (sin docker)
	cd backend && python -m orux.server

db-backup: ## Backup de Postgres (local en ./backups; off-site a DO Spaces si DO_SPACES_* está seteado)
	./scripts/backup-db.sh

db-restore: ## Restaurar DB desde backup. Uso: make db-restore FILE=./backups/orux-XXX.sql.gz CONFIRM=yes
	@if [ -z "$(FILE)" ]; then echo "uso: make db-restore FILE=./backups/orux-XXXX.sql.gz CONFIRM=yes"; exit 2; fi
	CONFIRM=$(CONFIRM) ./scripts/restore-db.sh "$(FILE)"
