#
# CAREFUL HERE! The build context is the top level directory of git!
#
REPO=ghcr.io/haikuports
VERSION=1.3.0-2
default:
	docker build --no-cache --tag ${REPO}/buildmaster:${VERSION} -f Dockerfile ../..
push:
	docker push ${REPO}/buildmaster:${VERSION}
enter:
	docker run -it ${REPO}/buildmaster:${VERSION} /bin/bash -l
