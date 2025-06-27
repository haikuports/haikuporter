REPO=ghcr.io/haikuports
VERSION=$(shell git describe --dirty --tags --abbrev=1)
default:
	podman build --no-cache --tag ${REPO}/haikuporter/frontend:${VERSION} .
push:
	podman push ${REPO}/haikuporter/frontend:${VERSION}
enter:
	podman run -it ${REPO}/haikuporter/frontend:${VERSION} /bin/sh -l
