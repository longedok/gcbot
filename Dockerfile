FROM python:3.9.1-alpine

RUN apk add --update gcc musl-dev libffi-dev openssl-dev postgresql-libs postgresql-dev

ENV POETRY_VERSION=1.1.4 \
  PIP_DISABLE_PIP_VERSION_CHECK=on

RUN pip install "poetry==$POETRY_VERSION"

WORKDIR /app
COPY poetry.lock pyproject.toml /app/

RUN poetry config virtualenvs.create false \
  && poetry install --no-dev --no-interaction --no-ansi

COPY . /app

CMD ["python3", "main.py"]

