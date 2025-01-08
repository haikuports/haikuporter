REPO=ghcr.io/haikuports
VERSION=1.3.0-2
default:
	docker build --no-cache --tag ${REPO}/frontend:${VERSION} .
push:
	docker push ${REPO}/frontend:${VERSION}
enter:
	docker run -it ${REPO}/frontend:${VERSION} /bin/sh -l
