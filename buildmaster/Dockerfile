#
# Haiku buildmaster within a docker container
#
# Try me!
#  - docker build . -t haikuporter
#  - docker run -it -e ARCH=x86 haikuporter:latest
#
# TODO: /data persistant volume

FROM fedora
MAINTAINER Haiku, Inc.

ENV ARCH=x86_64

# Install requirements
RUN dnf update -y && dnf install -y git python2 python2-paramiko wget xz

RUN mkdir -p /app
WORKDIR /app
RUN git clone https://github.com/haikuports/haikuporter

# Install host-tools
RUN wget http://download.haiku-os.org/host-tools/haiku_host_tools-02202017-linux-x86_64.tar.xz -O /tmp/host-tools.tar.xz
WORKDIR /usr/local
RUN tar xvf /tmp/host-tools.tar.xz
RUN echo "/usr/local/lib" > /etc/ld.so.conf.d/local-lib.conf
RUN ldconfig

RUN mkdir -p /data

# Prepare paths in persistant storage (if provided empty volume)
RUN echo "mkdir -p /data/buildmaster" > /etc/profile.d/haikuporter-prep.sh
RUN echo "/app/haikuporter/buildmaster/gitget https://github.com/haikuports/haikuports /data/haikuports" >> /etc/profile.d/haikuporter-prep.sh

# Alias our tools with correct data locations (/data)
RUN echo "alias haikuporter='/app/haikuporter/haikuporter '" > /etc/profile.d/haikuporter-shell.sh
RUN echo "alias builderctl='/app/haikuporter/buildmaster/builderctl -C /data/buildmaster/builders '" >> /etc/profile.d/haikuporter-shell.sh
RUN echo "alias createbuilder='/app/haikuporter/buildmaster/createbuilder -C /data/buildmaster/builders '" >> /etc/profile.d/haikuporter-shell.sh

# Fancy shell prompt
RUN echo 'export PS1="\e[1;33m[buildmaster@$ARCH \W]\$ \e[m "' > /etc/profile.d/haikuporter-prompt.sh
RUN echo 'grep -q -F "TARGET_ARCHITECTURE" /data/haikuports.conf || echo "TARGET_ARCHITECTURE=$ARCH" >> /data/haikuports.conf' >> /etc/profile.d/haikuporter-arch.sh

# Setup sane haikuports.conf
RUN echo 'TREE_PATH="/data/haikuports"' > /data/haikuports.conf
RUN echo 'PACKAGER="Haiku Buildmaster <buildmaster@haiku-os.org>"' >> /data/haikuports.conf

# Persistant data
WORKDIR /data
VOLUME ['/data']

CMD /bin/bash
