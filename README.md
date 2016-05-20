# Haikuporter

The HaikuPorter tool is provided to ease the fetching, patching and building of source code. It can be compared to a slim version of [Gentoo Portage](https://www.gentoo.org/main/en/about.xml). Each port contains the [Haiku](http://haiku-os.org) specific patches to the original source code. It fetches the original source code, applies the Haiku-specific patches, builds the software, and packages it.

Detailed information available on the [wiki](https://github.com/haikuports/haikuports/wiki/).

# Quick start

## Single Machine (Haiku)

A single machine installation is for building individual packages.

### Installation (Haiku)

HaikuPorts installation can be done via the following command sequence:
 - `git clone https://github.com/haikuports/haikuporter.git`
 - `git clone https://github.com/haikuports/haikuports.git`
 - `cd haikuporter`
 - `cp haikuports-sample.conf /boot/home/config/settings/haikuports.conf # Copy the config file`
 - `lpe ~/config/settings/haikuports.conf # and edit it`

### Build port
 - `./haikuporter mesa --no-dependencies -j4`

## Multi-node cluster (Linux + Haiku)

A multi-node cluster is for mass building large numbers of packages.

### Deploy buildmaster (Linux)

 - `git clone https://git.haiku-os.org/buildtools`
 - `make -j2 -C buildtools/jam && sudo cp buildtools/jam/bin.*/jam /usr/local/bin/`
 - `git clone https://git.haiku-os.org/haiku`
 - `mkdir haiku/generated.tools`
 - `cd haiku/generated.tools`
 - `../configure --build-cross-tools x86 ../../buildtools -j4`
 - `jam -q \<build\>package`
 - `sudo cp objects/linux/lib/* /usr/local/lib/`
 - `sudo cp objects/linux/x*/release/tools/package/package /usr/local/bin/`
 - `sudo ldconfig`
 - `cd ../..`
 - `git clone https://github.com/haikuports/haikuporter.git`
 - `git clone https://github.com/haikuports/haikuports.git`
 - `cd haikuporter`
 - `./buildmaster/createbuilder.sh`
   -  configure your first build slave with the prompts
 - `./haikuporter --build-master --command-package /usr/local/bin/package --licenses ../haiku/data/system/data/licenses/`

### Deploy buildslave (Haiku)

 - TODO
