.PHONY: up-infra logs-infra run-tasks run-flow \
        run-full logs-full down-infra down-full \
        migrate-tasks migrate-flow
#===============================================================================
# 🛠️ 1. РЕЖИМ РАЗРАБОТКИ (Backend на ПК, Инфраструктура в Docker)
# ==============================================================================

# 1.1. Запустить инфраструктуру в фоне (-d) c пересборкой воркеров (--build)
up-infra:
	docker compose \
		-f docker-compose.local.yaml \
		up -d --build

# 1.2. Посмотреть логи Celery, баз данных и MinIO
logs-infra:
	docker compose -f docker-compose.local.yaml logs -f

# 1.3. Миграции для базы данных ПРОЕКТОВ
migrate-tasks:
	PYTHONPATH=tasks/app \
	uv run \
		--env-file ./tasks/.env.tasks \
		alembic -c tasks/app/alembic.ini upgrade head

# 1.4. Миграции для базы данных ФЛОУ
migrate-flow:
	PYTHONPATH=flow/app \
	uv run \
		--env-file ./flow/.env.flow \
		alembic -c flow/app/alembic.ini upgrade head

# 1.5. Локальный запуск бэкенда ПРОЕКТОВ через uv
run-tasks:
	PYTHONPATH=tasks/app \
	uv run \
		--env-file ./tasks/.env.tasks \
		uvicorn main:app --reload --port 8000

# 1.6. Локальный запуск бэкенда ФЛОУ через uv
run-flow:
	PYTHONPATH=flow/app \
	uv run \
		--env-file ./flow/.env.flow \
		uvicorn main:app --reload --port 8001

# ==============================================================================
# 🚀 2. РЕЖИМ ПОЛНОЙ СБОРКИ (Всё внутри Docker)
# ==============================================================================

# 2.2. Сборка и запуск всего стека сервисов
run-full:
	docker compose up -d --build

# 2.. Смотреть логи всей сборки в реальном времени
logs-full:
	docker compose logs -f

# ==============================================================================
# 🧹 3. ОЧИСТКА И ОСТАНОВКА
# ==============================================================================

# 3.1. Остановить контейнеры локальной инфраструктуры (данные в базах СОХРАНЯЮТСЯ)
down-infra:
	docker compose -f docker-compose.local.yaml down

# 3.2. Остановить полную сборку (данные в базах СОХРАНЯЮТСЯ)
down-full:
	docker compose down


# ==============================================================================
# 🔍 4. КАЧЕСТВО КОДА И СТАТИЧЕСКИЙ АНАЛИЗ (Ruff / Mypy)
# ==============================================================================

# 4.1. Отформатировать и исправить стиль кода
check-all:
	uv run ruff check . --fix

# ==============================================================================
# 🧪 5. ТЕСТИРОВАНИЕ И ПРОВЕРКА ПОКРЫТИЯ (QA)
# ==============================================================================

# 5.1. Запустить тесты раздела ПРОЕКТОВ
test-tasks:
	uv run --env-file ./tests/tasks/.env.tasks.test pytest tests/tasks

# 5.2. Запустить тесты раздела FLOW
test-flow:
	uv run --env-file ./tests/flow/.env.flow.test pytest tests/flow

# 5.3. Последовательно запустить тесты всех разделов
test-all: test-tasks test-flow
