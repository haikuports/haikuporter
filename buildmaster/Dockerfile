#
# Haiku buildmaster within a docker container
#

FROM fedora
MAINTAINER Haiku, Inc.

ENV TARGET_ARCH=x86_64

# Install requirements
RUN dnf update -y && dnf install -y git python-paramiko wget xz

RUN mkdir -p /app
RUN git clone https://github.com/haikuports/haikuporter
RUN git clone https://github.com/haikuports/haikuports

# Install host-tools
RUN wget http://download.haiku-os.org/host-tools/haiku_host_tools-02202017-linux-x86_64.tar.xz -O /tmp/host-tools.tar.xz
WORKDIR /usr/local
RUN tar xvf /tmp/host-tools.tar.xz
RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/local-lib.conf
RUN ldconfig

# Persistant data
RUN mkdir -p /data
VOLUME ['/data']
