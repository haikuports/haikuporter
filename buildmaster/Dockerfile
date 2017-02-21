#
# Haiku buildmaster within a docker container
#
# Local development:
#  - mkdir ~/x86-buildmaster
#  - docker build . -t buildmaster:next
#  - docker run -v ~/x86-buildmaster:/data -it -e ARCH=x86 buildmaster:next
#
# Pushing new version to docker.io:
#  - docker login
#  - docker build . -t docker.io/haikuporter/buildmaster
#  - docker push
#
# Running container on any workstation:
#  - mkdir ~/x86-buildmaster
#  - docker pull haikuporter/buildmaster
#  - docker run -v ~/x86-buildmaster:/data -it -e ARCH=x86 haikuporter/buildmaster
#

FROM fedora
MAINTAINER Haiku, Inc.

ENV ARCH=x86_64

# Install requirements
RUN dnf update -y && dnf install -y git python2 python2-paramiko wget xz vim gcc

RUN mkdir -p /app
WORKDIR /app
RUN git clone https://github.com/haikuports/haikuporter
RUN git clone https://github.com/haiku/haiku --depth 1
RUN git -C /app/haiku checkout HEAD data/system/data/licenses

# Install host-tools
RUN wget http://download.haiku-os.org/host-tools/haiku_host_tools-02202017-linux-x86_64.tar.xz -O /tmp/host-tools.tar.xz
WORKDIR /usr/local
RUN tar xvf /tmp/host-tools.tar.xz
RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/local-lib.conf
RUN ldconfig

RUN mkdir -p /data

# This does most of the environmental prep
ADD .buildmaster.env /etc/profile.d/buildmaster.sh
ADD .motd /etc/motd

# Persistant data
WORKDIR /data
VOLUME ['/data']

CMD /bin/bash
