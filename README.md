# haikuporter

[![Release](https://img.shields.io/github/v/release/haikuports/haikuporter)](https://img.shields.io/github/v/release/haikuports/haikuporter)
[![Build status](https://img.shields.io/github/actions/workflow/status/haikuports/haikuporter/main.yml?branch=main)](https://github.com/haikuports/haikuporter/actions/workflows/main.yml?query=branch%3Amain)
[![codecov](https://codecov.io/gh/haikuports/haikuporter/branch/main/graph/badge.svg)](https://codecov.io/gh/haikuports/haikuporter)
[![Commit activity](https://img.shields.io/github/commit-activity/m/haikuports/haikuporter)](https://img.shields.io/github/commit-activity/m/haikuports/haikuporter)
[![License](https://img.shields.io/github/license/haikuports/haikuporter)](https://img.shields.io/github/license/haikuports/haikuporter)

- **Github repository**: <https://github.com/haikuports/haikuporter/>
- **Documentation** <https://haikuports.github.io/haikuporter/>

## Quick start

### Single Machine (Haiku)

A single machine installation is for building individual packages.

## Installation (Haiku)

HaikuPorts installation can be done via the following command sequence:

```shell
 $ git clone https://github.com/haikuports/haikuporter.git
 $ git clone https://github.com/haikuports/haikuports.git --depth=10
 $ cd haikuporter
 $ cp haikuports-sample.conf /boot/home/config/settings/haikuports.conf # Copy the config file
 $ lpe ~/config/settings/haikuports.conf # and edit it
```

### Build port
 - `./haikuporter mesa -j4`

### Build port and all outdated dependency ports
 - `./haikuporter mesa --all-dependencies -j4`

## Multi-node cluster (Linux + Haiku)

A multi-node cluster is for mass building large numbers of packages.

### Running buildmaster in a container with docker

 - `docker pull haikuporter/buildmaster`
 - `mkdir ~/buildmaster.x86`
 - `docker run -v ~/buildmaster.x86:/data -it -e ARCH=x86 haikuporter/buildmaster`
 - Provision builders
   - `createbuilder -n test01 -H 127.0.0.1`
   - copy generated public key to builder
   - `builderctl health`
 - exit
 - Copy the packages from a nightly to ports/packages on the buildmaster
 - `docker run -v ~/buildmaster.x86:/data -it -e ARCH=x86 haikuporter/buildmaster`
 - buildmaster everything

buildmaster.x86 will persist between build runs. Feel free to exit, update, or
erase the container without losing your work.

### Manually Deploy buildmaster (Linux)

 - Install requirements
   - `pip install paramiko` or `dnf install python-paramiko`
   - buildtools dependencies: autoconf, flex, bison, texinfo, zlib-devel
   - Haiku host tools dependencies: libstdc++-static, libcurl-devel
 - Bootstrap the buildmaster instance
   - `git clone https://github.com/haikuports/haikuporter.git`
   - `./haikuporter/buildmaster/bin/bootstrap_buildmaster.sh ...`
 - Configure your builders within instance ports tree with createbuilder
   - `cd buildmaster_<arch>/haikuports`
   - example: `../haikuporter/buildmaster/bin/createbuilder -n mybuilder01 -H 127.0.0.1`
 - Validate and provision your builders
   - `../haikuporter/buildmaster/bin/builderctl health`
   - `../haikuporter/buildmaster/bin/builderctl provision`
 - `../haikuporter/buildmaster/bin/buildmaster everything`

### Deploy buildslave (Haiku)

 - Checkout Haikuporter and Haikuports, matching the paths specified in createbuilder on buildmaster side
 - Add the public key from the buildmaster to authorized\_keys
 - useradd sshd ; ssh-keygen -A
 - Enable PermitRootLogin in /system/settings/ssh/sshd\_config and make sure the path to the sftp server is correct
 - install xz\_utils\_x86, lzip\_x86 (required for extracting packages), patch, dos2unix (required for PATCH() function in some packages)
