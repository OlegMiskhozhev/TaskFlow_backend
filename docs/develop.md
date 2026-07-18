## РАЗРАБОТКА

Backend проекта состоит из двух частей - основной (режим tasks) и микросервиса 
режима flow. Каждая часть запускается в своем контейнере со своей отдельной
базой данных, каждая из которых также запускается в отдельном контейнере.

### Локальный запуск backend

Для локального запуска необходимо клонировать репозиторий, установить 
виртуальное окружение через пакетный менеджер Poetry, запустить необходимые
сервисы через Docker.
Установити Poetry и Docker, используя официальную документацию.

Клонирование проекта:
```
git clone https://gitlab.pointpulse.ru/l1/taskflow/backend.git
```

Из корня репозитория выполнить:
```
poetry install                              # установить зависимости
poetry shell                                # активировать окружение
```

Миграции выполняются последовательно для каждого раздела.
```
cd tasks/app                                # раздел tasks
poetry run alembic upgrade head             # миграции tasks
cd ../..                                    # возврат в корневой каталог
cd flow/app                                 # раздел flow
poetry run alembic upgrade head             # миграции flow
```

Минимальные требования для запуска сервера раздела tasks - запуск базы данных 
PostgreSQL и Redis (для кеширования). Из корневого каталога выполниить:
```
docker compose up --build -d tasks_db redis
cd cd tasks/app
poetry run uvicorn main:app --reload
```
Для использования функционала фоновых задач необходимо подключить 
дополнительно Celery сервисов (добавьте к команде docker compose флаги 
celeryworker и celerybeat), а для загрузки файлов S3 храгилище (добавьте 
флаг minio)

Минимальные требования для запуска сервера раздела flow - запуск базы данных
```
docker compose up --build -d flow_db
cd cd flow/app
poetry run uvicorn main:app --reload
```

### Качество кода (ruff/mypy)

Для проверки и автоматического форматирования кода из корня проекта выполните:

```
poetry run ruff check .                     # линтер
poetry run ruff check . --fix               # автоисправление части замечаний ruff
poetry run ruff format .                    # форматирование (ruff)
poetry run mypy                             # типы только flow/app и tasks/app
poetry run mypy flow/app                    # типы только flow
poetry run mypy tasks/app                   # типы только tasks
```

Возможно запускать проверку и форматирование одновременно:
```
poetry run ruff format && poetry run ruff check --fix
```


[⬅ Назад на главную](../README.md)