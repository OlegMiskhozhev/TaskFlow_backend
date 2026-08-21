# Базовый официальный образ Python
FROM python:3.12-slim AS base

WORKDIR /code

# Настройка переменных окружения для компиляции и байт-кода
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

ENV PATH="/code/.venv/bin:$PATH"

# Отдельный слой для установки uv и синхронизации зависимостей
FROM base AS dep-uv

# Устанавливаем uv через официальный автономный скрипт
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Копируем только файлы конфигурации пакетов для кэширования слоев
COPY pyproject.toml uv.lock ./

# Синхронизируем зависимости на основе uv.lock без создания нового venv
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Финальный слой сборки приложения
FROM dep-uv AS runner

# Копируем исходный код приложения в рабочую директорию
COPY ./flow/app /code

# Запуск ASGI-сервера uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
