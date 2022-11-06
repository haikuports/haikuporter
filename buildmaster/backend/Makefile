#
# CAREFUL HERE! The build context is the top level directory of git!
#
VERSION=1.2.7-6
default:
	docker build --no-cache --tag docker.io/haikuporter/buildmaster:${VERSION} -f Dockerfile ../..
push:
	docker push docker.io/haikuporter/buildmaster:${VERSION}
enter:
	docker run -it docker.io/haikuporter/buildmaster:${VERSION} /bin/bash -l
