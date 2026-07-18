FROM python:3.12.0-slim as base

WORKDIR /code

FROM base as dep-poetry
ENV POETRY_HOME /opt/poetry
RUN python3 -m venv $POETRY_HOME
RUN $POETRY_HOME/bin/pip install poetry==2.3.1
ENV POETRY_BIN $POETRY_HOME/bin/poetry
 
COPY pyproject.toml poetry.lock ./
RUN $POETRY_BIN config --local virtualenvs.create false
RUN $POETRY_BIN install --no-root

COPY ./tasks/app /code

CMD ["uvicorn", "main:app", "--host", "0.0.0.0" ,"--port" ,"8000"]