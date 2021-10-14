FROM ubuntu:bionic

RUN apt-get update \
	&& apt-get -y install attr autoconf automake bison coreutils curl flex \
		gawk gcc gcc-multilib g++ git libcurl4-openssl-dev make nasm python3 \
		python3-paramiko tar texinfo wget zlib1g-dev \
	&& apt-get clean

RUN mkdir /var/sources /var/buildmaster
RUN echo 'export PATH=$PATH:/var/sources/haikuporter/buildmaster/bin/' >> /etc/bash.bashrc

VOLUME ["/var/sources", "/var/buildmaster"]

WORKDIR /var/buildmaster

COPY bootstrap loop /bin/
