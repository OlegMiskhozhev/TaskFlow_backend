## ЗАПУСК

### Как развернуть проект

* клонируйте проект

```
git clone https://gitlab.pointpulse.ru/l1/taskflow/backend.git
```

* перейдите в ветку develop

```
git checkout develop
```

* создайте файл `.env` в корне проекта и заполните его по примеру из `.env.example`

* установите и запустите Docker, используйте официальную документацию для установки.

* запустите проект в Docker и выполните миграции

```
docker compose up --build -d
docker exec -it tasks_backend alembic upgrade head
docker exec -it flow_backend alembic upgrade head
```

* при необходимости загрузите тестовые данные в базу данных:

```
docker exec -it tasks_backend python3 test_data/load_test_data.py
```

Проект будет доступен по адресам:

- http://localhost/api/tasks — раздел проектов
- http://localhost/api/tasks/redoc — документация раздела проектов
- http://localhost/api/flow — flow режим
- http://localhost/api/flow/redoc — документация flow режима

* остановка основного проекта (`docker-compose.yml` в корне)

```
docker compose down
```

[⬅ Назад на главную](../README.md)