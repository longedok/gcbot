build:
	docker build -t longedok/main .

push:
	docker push longedok/main

upload:
	docker build -t longedok/main .
	docker push longedok/main

run:
	docker-compose stop bot || true
	docker-compose up -d --build --no-deps bot

up:
	docker-compose up

test:
	pytest

psql:
	psql -h localhost -p 5432 -U postgres ${POSTGRES_DB}
