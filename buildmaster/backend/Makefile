#
# CAREFUL HERE! The build context is the top level directory of git!
#
REPO=ghcr.io/haikuports
VERSION=1.3.0-4
default:
	podman build --no-cache --tag ${REPO}/haikuporter/buildmaster:${VERSION} -f Dockerfile ../..
push:
	podman push ${REPO}/haikuporter/buildmaster:${VERSION}
enter:
	podman run -it ${REPO}/haikuporter/buildmaster:${VERSION} /bin/bash -l
