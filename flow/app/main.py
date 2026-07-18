from fastapi import FastAPI

from routers.core import core_router

_FLOW_API_DESCRIPTION = """
## Сервис заметок

Сервис **flow** приложения TaskFlow: дневные заметки с датой, текстом
  и отметкой о выполнении. Есть список с фильтром по дате, пагинация и
  календарь по числу заметок на дату.

#### Авторизация
Эндпоинты защищены **Bearer JWT** (access-токен тех же пользователей,
 что и в разделе tasks). Префикс шлюза: `/api/flow`.
""".strip()

_OPENAPI_TAGS = [
    {
        'name': 'Заметки',
        'description': (
            'CRUD заметок, календарь и смена статуса «выполнено» для текущего '
            'пользователя.'
        ),
    },
]

app = FastAPI(
    title='TaskFlow Flow API',
    description=_FLOW_API_DESCRIPTION,
    version='0.1.0',
    openapi_tags=_OPENAPI_TAGS,
    root_path='/api/flow',
)
app.include_router(core_router)
