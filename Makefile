.PHONY: help build build-test pull up up-local down restart logs test shell clean install dev test-docker clean-docker

COMPOSE_LOCAL = docker compose -f docker-compose.yml -f docker-compose.build.yml

help: ## Показать эту справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Установить зависимости локально
	uv sync --extra dev

dev: ## Запустить бота локально
	uv run python bot.py

test: ## Запустить тесты локально
	uv run pytest tests/ -v

build: ## Собрать локальный production Docker образ
	$(COMPOSE_LOCAL) build tgdlbot

build-test: ## Собрать локальный test Docker образ
	$(COMPOSE_LOCAL) --profile test build test

pull: ## Скачать production-образ из GHCR
	docker compose pull tgdlbot

up: ## Скачать образ из GHCR и запустить бота
	docker compose up -d

up-local: ## Собрать и запустить бота из локального кода
	$(COMPOSE_LOCAL) up -d --build tgdlbot

down: ## Остановить все сервисы
	docker compose down

restart: ## Перезапустить бота
	docker compose restart

logs: ## Просмотр логов бота
	docker compose logs -f tgdlbot

shell: ## Открыть shell в контейнере
	docker compose exec tgdlbot /bin/bash

test-docker: ## Собрать локальный образ и запустить тесты в Docker
	$(COMPOSE_LOCAL) --profile test run --build --rm test

clean: ## Очистить временные файлы
	rm -rf downloads/*.mp4 downloads/*.webm downloads/*.mkv
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

clean-docker: ## Удалить контейнеры проекта и образы без пользовательских тегов
	docker compose down --rmi local
