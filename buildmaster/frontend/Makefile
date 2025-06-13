REPO=ghcr.io/haikuports
VERSION=1.3.0-5
default:
	podman build --no-cache --tag ${REPO}/haikuporter/frontend:${VERSION} .
push:
	podman push ${REPO}/haikuporter/frontend:${VERSION}
enter:
	podman run -it ${REPO}/haikuporter/frontend:${VERSION} /bin/sh -l
