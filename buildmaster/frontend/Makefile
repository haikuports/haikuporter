REPO=ghcr.io/haikuports
VERSION=1.2.8-4
default:
	docker build --no-cache --tag ${REPO}/haikuporter/frontend:${VERSION} .
push:
	docker push ${REPO}/haikuporter/frontend:${VERSION}
enter:
	docker run -it ${REPO}/haikuporter/frontend:${VERSION} /bin/sh -l
