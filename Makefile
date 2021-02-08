build:
	docker build -t longedok/main .

push:
	docker push longedok/main

publish:
	docker build -t longedok/main .
	docker push longedok/main

run:
	docker-compose stop bot || true
	docker-compose -f docker-compose-dev.yml up -d --build --no-deps bot

up:
	docker-compose -f docker-compose-dev.yml up

test:
	pytest

psql:
	psql -h localhost -p 5432 -U postgres ${POSTGRES_DB}

deploy:
	docker pull longedok/main
	docker-compose stop bot || true
	docker-compose up -d --no-deps bot

check:
	mypy .

