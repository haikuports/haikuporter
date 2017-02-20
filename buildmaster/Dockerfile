#
# Haiku buildmaster within a docker container
#
# Try me!
#  - docker build . -t haikuporter
#  - docker run -it haikuporter:latest /bin/bash
#
# TODO: /data persistant volume

FROM fedora
MAINTAINER Haiku, Inc.

ENV TARGET_ARCH=x86_64

# Install requirements
RUN dnf update -y && dnf install -y git python2 python2-paramiko wget xz

RUN mkdir -p /app
WORKDIR /app
RUN git clone https://github.com/haikuports/haikuporter
RUN git clone https://github.com/haikuports/haikuports

# Install host-tools
RUN wget http://download.haiku-os.org/host-tools/haiku_host_tools-02202017-linux-x86_64.tar.xz -O /tmp/host-tools.tar.xz
WORKDIR /usr/local
RUN tar xvf /tmp/host-tools.tar.xz
RUN ldconfig

RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/local-lib.conf
RUN echo "alias haikuporter='/app/haikuporter/haikuporter'" > /etc/profile.d/haikuporter-shell.sh
RUN echo "alias builderctl='/app/haikuporter/buildmaster/builderctl -C /data'" >> /etc/profile.d/haikuporter-shell.sh
RUN echo "alias createbuilder='/app/haikuporter/buildmaster/createbuilder -C /data'" >> /etc/profile.d/haikuporter-shell.sh

WORKDIR /data

# Persistant data
RUN mkdir -p /data
VOLUME ['/data']
