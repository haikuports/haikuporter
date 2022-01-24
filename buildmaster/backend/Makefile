#
# CAREFUL HERE! The build context is the top level directory of git!
#
default:
	docker build --no-cache --tag docker.io/haikuporter/buildmaster:1.2.6-2 -f Dockerfile ../..
push:
	docker push docker.io/haikuporter/buildmaster:1.2.6-2
enter:
	docker run -it docker.io/haikuporter/buildmaster:1.2.6-2 /bin/bash -l
