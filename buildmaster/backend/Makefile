#
# CAREFUL HERE! The build context is the top level directory of git!
#
REPO=ghcr.io/haikuports
VERSION=1.3.0-1
default:
	docker build --no-cache --tag ${REPO}/haikuporter/buildmaster:${VERSION} -f Dockerfile ../..
push:
	docker push ${REPO}/haikuporter/buildmaster:${VERSION}
enter:
	docker run -it ${REPO}/haikuporter/buildmaster:${VERSION} /bin/bash -l
