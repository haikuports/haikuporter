build:
	docker build . -t docker.io/haikuporter/buildmaster
test:
	mkdir -p ~/x86-buildmaster
	docker run -v ~/x86-buildmaster:/data -it -e ARCH=x86 docker.io/haikuporter/buildmaster
push:
	docker push docker.io/haikuporter/buildmaster
