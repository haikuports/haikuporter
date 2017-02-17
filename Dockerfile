#
# Haiku buildmaster within a docker container
#

FROM fedora
MAINTAINER Haiku, Inc.

ARG TARGET_ARCH=x86

# Install requirements
RUN dnf update -y
RUN dnf install -y git nasm autoconf automake texinfo flex bison gcc gcc-c++ make glibc-devel zlib-devel genisoimage curl-devel libfdt byacc mtools libstdc++-static

RUN mkdir -p /app

WORKDIR /app
RUN git clone https://git.haiku-os.org/buildtools
RUN git clone https://git.haiku-os.org/haiku

# Install jam
RUN make -C buildtools/jam && cp buildtools/jam/bin.*/jam /usr/local/bin/

# Make tools
RUN mkdir -p /app/haiku/generated.tools
WORKDIR /app/haiku/generated.tools
RUN ../configure --host-only
RUN jam -q \<build\>package
RUN cp objects/linux/lib/* /usr/local/lib
RUN cp objects/linux/x*/release/tools/package/package /usr/local/bin
RUN ldconfig

# Prep environment
ADD . /app/haikuporter
