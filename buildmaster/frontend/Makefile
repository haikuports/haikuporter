#
# CAREFUL HERE! The build context is the top level directory of git!
#
default:
	docker build --no-cache --tag docker.io/haikuporter/buildmaster-frontend:1.2.6-1 .
push:
	docker push docker.io/haikuporter/buildmaster-frontend:1.2.6-1
enter:
	docker run -it docker.io/haikuporter/buildmaster-frontend:1.2.6-1 /bin/sh -l
