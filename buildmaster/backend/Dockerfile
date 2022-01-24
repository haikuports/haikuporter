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

# Pre-requirements
RUN apt-get update \
	&& apt-get -y install attr autoconf automake bison coreutils curl flex \
		gawk gcc gcc-multilib g++ git libcurl4-openssl-dev make nasm python3 \
		python3-paramiko python3-pip tar texinfo wget zlib1g-dev \
	&& apt-get clean \
	&& echo 'export LD_LIBRARY_PATH=$LD_LIBRARY_PATH:/usr/local/lib' >> /etc/bash.bashrc

# Minisign for repo signatures
RUN wget https://github.com/jedisct1/minisign/releases/download/0.10/minisign-0.10-linux.tar.gz -O /tmp/minisign.tar.gz \
	&& cd /tmp && tar -xvz --strip=2 -f /tmp/minisign.tar.gz && mv minisign /usr/local/bin \
	&& chmod 755 /usr/local/bin/minisign

# Haikuporter from local context root (this is where the weird context requirement comes from)
ADD . /tmp/haikuporter
RUN pip3 install /tmp/haikuporter \
	&& cp /tmp/haikuporter/buildmaster/backend/assets/bin/* /usr/local/bin/ \
	&& rm -rf /tmp/*

# Haikuporter release (another option, but weird from within haikuporter repo)
#ENV HAIKUPORTER_VERSION="1.2.6"
#RUN pip3 install https://github.com/haikuports/haikuporter/archive/refs/tags/$HAIKUPORTER_VERSION.tar.gz

COPY --from=host-tools /tmp/haiku/generated/objects/linux/x86_64/release/tools/package/package /usr/local/bin/
COPY --from=host-tools /tmp/haiku/generated/objects/linux/x86_64/release/tools/package_repo/package_repo /usr/local/bin/
COPY --from=host-tools /tmp/haiku/generated/objects/linux/lib/* /usr/local/lib/

RUN mkdir /var/sources /var/packages /var/buildmaster

VOLUME ["/var/sources", "/var/packages", "/var/buildmaster"]
WORKDIR /var/buildmaster

COPY buildmaster/backend/assets/bootstrap buildmaster/backend/assets/loop /bin/
