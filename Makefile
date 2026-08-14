.PHONY: up-infra logs-infra run-tasks run-flow \
        run-full logs-full down-infra down-full \
        migrate-tasks migrate-flow
#==============================================================================
# 🛠️ РЕЖИМ РАЗРАБОТКИ (Backend на ПК, Инфраструктура в Docker)
# ==============================================================================

# 1. Запустить инфраструктуру в фоне (-d) и принудительно пересобрать воркеры (--build)
up-infra:
	docker compose \
		-f docker-compose.local.yaml \
		up -d --build

# 2. Посмотреть логи Celery, баз данных и MinIO
logs-infra:
	docker compose -f docker-compose.local.yaml logs -f

# 3. Локальный запуск бэкенда ПРОЕКТОВ через uv
run-tasks:
	PYTHONPATH=tasks/app \
	uv run \
		--env-file ./tasks/.env.tasks \
		uvicorn main:app --reload --port 8000

# 4. Локальный запуск бэкенда ФЛОУ через uv
run-flow:
	PYTHONPATH=flow/app \
	uv run \
		--env-file ./flow/.env.flow \
		uvicorn main:app --reload --port 8001

# 5. Миграции для базы данных ПРОЕКТОВ
migrate-tasks:
	PYTHONPATH=tasks/app \
	uv run \
		--env-file ./tasks/.env.tasks \
		alembic -c tasks/app/alembic.ini upgrade head

# 6. Миграции для базы данных ФЛОУ
migrate-flow:
	PYTHONPATH=flow/app \
	uv run \
		--env-file ./flow/.env.flow \
		alembic -c flow/app/alembic.ini upgrade head

# ==============================================================================
# 🚀 РЕЖИМ ПОЛНОЙ СБОРКИ (Всё внутри Docker)
# ==============================================================================

# 7. Сборка и запуск всего стека сервисов
run-full:
	docker compose up -d --build

# 8. Смотреть логи всей сборки в реальном времени
logs-full:
	docker compose logs -f

# ==============================================================================
# 🧹 ОЧИСТКА И ОСТАНОВКА
# ==============================================================================

# 9. Остановить контейнеры локальной инфраструктуры (данные в базах СОХРАНЯЮТСЯ)
down-infra:
	docker compose -f docker-compose.local.yaml down

# 10. Остановить полную сборку (данные в базах СОХРАНЯЮТСЯ)
down-full:
	docker compose down
