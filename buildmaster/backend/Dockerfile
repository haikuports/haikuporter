FROM debian:bullseye-slim AS host-tools

RUN apt-get update \
	&& apt-get -y install git bc nasm texinfo flex bison gawk build-essential \
		unzip wget zip less zlib1g-dev libzstd-dev python3

# We can skip buildtools someday if we ever get a way to build jam without it
RUN git clone --depth 1 https://review.haiku-os.org/buildtools /tmp/buildtools \
	&& git clone --depth 1 https://review.haiku-os.org/haiku /tmp/haiku \
	&& cd /tmp/buildtools/jam && make && ./jam0 install \
	&& cd /tmp/haiku && ./configure --host-only \
	&& jam -j2 -q \<build\>package \<build\>package_repo

#############################################################
FROM debian:bullseye-slim

# hardlink for build-packages
ADD https://cgit.haiku-os.org/haiku/plain/src/tools/hardlink_packages.py /usr/local/bin/

# Pre-requirements
RUN apt-get update \
	&& apt-get -y install attr autoconf automake bison coreutils curl flex \
		gawk gcc gcc-multilib g++ git libcurl4-openssl-dev make nasm python3 \
		python3-paramiko python3-pip tar texinfo vim wget zlib1g-dev \
	&& apt-get clean

RUN echo 'export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib' >> /etc/bash.bashrc \
	&& wget https://github.com/jedisct1/minisign/releases/download/0.10/minisign-0.10-linux.tar.gz -O /tmp/minisign.tar.gz \
	&& cd /tmp && tar -xvz --strip=2 -f /tmp/minisign.tar.gz && mv minisign /usr/local/bin

# Haikuporter from local context root (this is where the weird context requirement comes from)
ADD . /tmp/haikuporter

RUN pip3 install /tmp/haikuporter \
	&& echo "Bug #277 Fix" && cp /tmp/haikuporter/haikuporter.py /usr/local/bin/haikuporter \
	&& cp /tmp/haikuporter/buildmaster/backend/assets/bin/* /usr/local/bin/ \
	&& cp /tmp/haikuporter/buildmaster/backend/assets/bootstrap /bin/ \
	&& cp /tmp/haikuporter/buildmaster/backend/assets/loop /bin/ \
	&& rm -rf /tmp/* \
	&& mkdir /var/licenses /var/buildmaster \
	&& chmod 755 /usr/local/bin/*

COPY --from=host-tools /tmp/haiku/generated/objects/linux/x86_64/release/tools/package/package /usr/local/bin/
COPY --from=host-tools /tmp/haiku/generated/objects/linux/x86_64/release/tools/package_repo/package_repo /usr/local/bin/
COPY --from=host-tools /tmp/haiku/generated/objects/linux/lib/* /usr/local/lib/
COPY --from=host-tools /tmp/haiku/data/system/data/licenses /var/licenses

VOLUME ["/var/buildmaster"]
WORKDIR /var/buildmaster
