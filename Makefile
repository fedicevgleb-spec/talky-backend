# Docker Compose shortcuts for talky (service: web)
COMPOSE := docker compose
SERVICE := web
DB_PATH := /data/payments.db

.DEFAULT_GOAL := help

.PHONY: help up up-d down down-v ps logs build rebuild restart start stop sh shell db clean prune

help:
	@echo "Usage: make [target]"
	@echo ""
	@echo "  up        docker compose up (foreground)"
	@echo "  up-d      docker compose up -d (detached)"
	@echo "  down      docker compose down"
	@echo "  down-v    docker compose down -v (remove volumes; deletes DB in volume)"
	@echo "  ps        docker compose ps"
	@echo "  logs      docker compose logs -f $(SERVICE)"
	@echo "  build     docker compose build"
	@echo "  rebuild   docker compose build --no-cache"
	@echo "  restart   docker compose restart $(SERVICE)"
	@echo "  start     docker compose start"
	@echo "  stop      docker compose stop"
	@echo "  sh        shell into $(SERVICE) container (sh)"
	@echo "  shell     same as sh"
	@echo "  db        sqlite3 CLI on $(DB_PATH) inside $(SERVICE)"
	@echo "  clean     docker compose down"
	@echo "  prune     docker system prune -f (unused data)"

up:
	$(COMPOSE) up

up-d:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

down-v:
	$(COMPOSE) down -v

ps:
	$(COMPOSE) ps

logs:
	$(COMPOSE) logs -f $(SERVICE)

build:
	$(COMPOSE) build

rebuild:
	$(COMPOSE) build --no-cache

restart:
	$(COMPOSE) restart $(SERVICE)

start:
	$(COMPOSE) start

stop:
	$(COMPOSE) stop

sh:
	$(COMPOSE) exec -it $(SERVICE) sh

shell: sh

db:
	$(COMPOSE) exec -it $(SERVICE) sqlite3 $(DB_PATH)

clean:
	$(COMPOSE) down

prune:
	docker system prune -f

env:
	docker compose exec $(SERVICE) env
