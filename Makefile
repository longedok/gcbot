build:
	docker build -t longedok/main .

push:
	docker push longedok/main

upload:
	docker build -t longedok/main .
	docker push longedok/main

rund:
	docker build -t longedok/main .
	docker rm -f bot || true
	docker run -d -e TOKEN=${TOKEN} -e BOT_USERNAME=${BOT_USERNAME}\
		-e DATADIR=/data -v botdb:/data --name bot longedok/main

test:
	pytest
