FROM ubuntu:bionic

RUN apt-get update \
	&& apt-get -y install attr autoconf automake bison coreutils curl flex \
		gawk gcc gcc-multilib g++ git libcurl4-openssl-dev make nasm python3 \
		python3-paramiko tar texinfo wget zlib1g-dev \
	&& apt-get clean

RUN wget https://github.com/jedisct1/minisign/releases/download/0.10/minisign-0.10-linux.tar.gz -O /tmp/minisign.tar.gz \
	&& cd /tmp && tar -xvz --strip=2 -f /tmp/minisign.tar.gz && mv minisign /usr/local/bin \
	&& chmod 755 /usr/local/bin/minisign && rm /tmp/*

RUN mkdir /var/sources /var/buildmaster
RUN echo 'export PATH=$PATH:/var/sources/haikuporter/buildmaster/bin/' >> /etc/bash.bashrc

VOLUME ["/var/sources", "/var/buildmaster"]

WORKDIR /var/buildmaster

COPY bootstrap loop /bin/
