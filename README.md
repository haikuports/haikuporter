# HaikuPorter

The HaikuPorter tool is provided to ease the fetching, patching and building of source code. It can be compared to a slim version of [Gentoo Portage](https://www.gentoo.org/main/en/about.xml). Each port contains the [Haiku](http://haiku-os.org) specific patches to the original source code. It fetches the original source code, applies the Haiku-specific patches, builds the software, and packages it.

Detailed information available on the [wiki](https://github.com/haikuports/haikuports/wiki/).

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

 - `docker pull ghcr.io/haikuports/haikuporter/buildmaster`
 - `mkdir ~/buildmaster.x86`
 - `docker run -v ~/buildmaster.x86:/data -it -e ARCH=x86 ghcr.io/haikuports/haikuporter/buildmaster`
 - Provision builders
   - `createbuilder -n test01 -H 127.0.0.1`
   - copy generated public key to builder
   - `builderctl health`
 - exit
 - Copy the packages from a nightly to ports/packages on the buildmaster
 - `docker run -v ~/buildmaster.x86:/data -it -e ARCH=x86 ghcr.io/haikuports/haikuporter/buildmaster`
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

### Making a release of haikuporter

 - Be sure __version__.py , pyproject.toml is set to the next version of haikuporter and changes are pushed
 - Draft a new release version matching what's in __version__.py, pyproject.toml
 - Once a new release is made in github, bump the versions in __version__.py , pyproject.toml to the *NEXT* version
 - The buildmaster containers are generally updated out-of-band as they receive updates less often
   - Version numbers in buildmaster/*/Makefile *should* follow the same process as above ideally
   - Ideally, we would rebuild the buildmaster containers every release, but not a requirement
