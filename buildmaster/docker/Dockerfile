FROM ubuntu:bionic

RUN apt-get update \
	&& apt-get -y install autoconf automake bison coreutils curl flex gawk gcc \
		g++ git libcurl4-openssl-dev make nasm python3 python3-paramiko tar \
		texinfo wget zlib1g-dev

RUN mkdir /var/sources /var/buildmaster

VOLUME ["/var/sources", "/var/buildmaster"]

WORKDIR /var/buildmaster

COPY bootstrap loop /bin/
