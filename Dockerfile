FROM python:3.9.1-alpine AS base

ENV POETRY_VERSION=1.1.4 \
  PIP_DISABLE_PIP_VERSION_CHECK=on

WORKDIR /app

FROM base as builder

RUN apk --no-cache add gcc musl-dev libffi-dev openssl-dev \
	postgresql-dev
RUN apk --no-cache add curl \
	&& curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y
ENV PATH=/root/.cargo/bin:$PATH

RUN pip install "poetry==$POETRY_VERSION"
RUN python -m venv /venv

COPY poetry.lock pyproject.toml /app/
RUN . /venv/bin/activate && poetry install --no-dev --no-root

COPY . /app
RUN . /venv/bin/activate && poetry build

FROM base as final

RUN apk add --no-cache postgresql-libs
COPY --from=builder /venv /venv
COPY . /app
COPY docker-entrypoint.sh ./
ENTRYPOINT ["sh", "./docker-entrypoint.sh"]

