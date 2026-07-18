### Тесты в Docker

Шаблон: `cp .env.test.example .env.test` (Windows: `Copy-Item .env.test.example .env.test`).  
Тесты flow — `tests/flow/`, tasks — `tests/tasks/`; в команде всегда указывайте `-c pytest.flow.ini` или
`-c pytest.tasks.ini`.  
Покрытие задано в этих ini-файлах.

**Flow** (Postgres на хосте **5435**):

```
docker compose -f docker-compose.flow.test.yml --env-file .env.test up -d flow_db_test
docker compose -f docker-compose.flow.test.yml --env-file .env.test run --rm flow_tests pytest -c pytest.flow.ini tests/flow
docker compose -f docker-compose.flow.test.yml --env-file .env.test down
```

Для `tests/flow/unit` или `tests/flow/integration` замените путь в команде `run`. Том БД: `down -v`.

**Tasks** (Postgres на хосте **5436**):

```
docker compose -f docker-compose.tasks.test.yml --env-file .env.test up -d tasks_db_test
docker compose -f docker-compose.tasks.test.yml --env-file .env.test run --rm tasks_tests pytest -c pytest.tasks.ini tests/tasks
docker compose -f docker-compose.tasks.test.yml --env-file .env.test down
```

Аналогично: `tests/tasks/unit`, `tests/tasks/integration`, остановка с `down -v`.

Flow и tasks можно запускать параллельно в разных терминалах — отдельные compose-проекты и порты **5435** / **5436**.



[⬅ Назад на главную](../README.md)