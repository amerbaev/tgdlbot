.PHONY: help build build-test up down restart logs test shell clean install dev test-docker

help: ## Показать эту справку
	@echo "Доступные команды:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-20s\033[0m %s\n", $$1, $$2}'

install: ## Установить зависимости локально
	uv sync --extra dev

dev: ## Запустить бота локально
	uv run python bot.py

test: ## Запустить тесты локально
	uv run pytest tests/ -v

build: ## Собрать production Docker образ
	docker-compose build tgdlbot

build-test: ## Собрать test Docker образ
	docker-compose build test

up: ## Запустить бота в Docker
	docker-compose up -d

down: ## Остановить все сервисы
	docker-compose down

restart: ## Перезапустить бота
	docker-compose restart

logs: ## Просмотр логов бота
	docker-compose logs -f tgdlbot

shell: ## Открыть shell в контейнере
	docker-compose exec tgdlbot /bin/bash

test-docker: ## Запустить тесты в Docker
	docker-compose --profile test run --rm test

clean: ## Очистить временные файлы
	rm -rf downloads/*.mp4 downloads/*.webm downloads/*.mkv
	rm -rf .pytest_cache
	find . -type d -name __pycache__ -exec rm -rf {} +

clean-docker: ## Очистить Docker образы и контейнеры
	docker-compose down -v
	docker system prune -f
	docker image prune -f
