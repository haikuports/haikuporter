#!/bin/bash
#
# This is to be used on a local system trusted for generating a set of initial_packages
# for a single architecture to be transfered to the haikuporter buildmaster.
#
# You'll use this when updating the set of Haiku packages all haikuports are compiled
# against. You would generally do this when a new major version of Haiku is being tested
# for release.
#
# You may want to consider compiling a new set of package tools (package, package_repo, etc)
# on a "haikuporter buildmaster" compatible system as well when doing this.
#
# If you're building this on haiku's server within the buildmaster container, use
# update_initial_packages.sh instead

if [ $# -ne 3 ]; then	
	echo "generates an archive of initial_packages for haikuporter buildmaster"
	echo "reminder: ensure haiku and buildtools directories are on the branches you want"
	echo "usage: $0 <haiku dir> <buildtools dir> <arch>"
	exit 1
fi

HAIKU_SRC=$(realpath $1)
HAIKU_BRANCH=$(git -C "${HAIKU_SRC}" branch --show-current)
BUILDTOOLS_SRC=$(realpath $2)
BUILDTOOLS_BRANCH=$(git -C "${BUILDTOOLS_SRC}" branch --show-current)
ARCH=$3
WORK=~/.tmp/generated.$ARCH

rm -rf ${WORK}
mkdir -p ${WORK}

if [ "${HAIKU_BRANCH}" == "master" ]; then
	echo "Warning: haiku is the master branch, you likely don't want this!"
fi
if [ "${BUILDTOOLS_BRANCH}" == "master" ]; then
	echo "Warning: buildtools is the master branch, you likely don't want this!"
fi

CPUS=$(nproc)
if [ $CPUS -gt 8 ]; then
	# a little cautious for parallel job bugs in our jam
	CPUS=8
fi

CONFIGURE="$HAIKU_SRC/configure -j$CPUS --distro-compatibility official --cross-tools-source $BUILDTOOLS_SRC"

if [ "${ARCH}" == "x86_gcc2h" ]; then
	CONFIGURE="$CONFIGURE --build-cross-tools x86_gcc2 --build-cross-tools x86"
else
	CONFIGURE="$CONFIGURE --build-cross-tools $ARCH"
fi

## Build jam
cd "$BUILDTOOLS_SRC"/jam
make
cp bin.*/jam $WORK

cd $WORK

# Configure
$CONFIGURE

# nightly-raw == goldilocks of packages
./jam -q -j$CPUS @nightly-raw

export LD_LIBRARY_PATH="$LD_LIBRARY_PATH:$WORK/objects/linux/lib"
TOOLS="$WORK/objects/linux/$(uname -m)/release/tools/"

rm -rf ~/.tmp/"haiku-${HAIKU_BRANCH}-$ARCH"
mkdir -p ~/.tmp/"haiku-${HAIKU_BRANCH}-$ARCH";
cd ~/.tmp/"haiku-${HAIKU_BRANCH}-$ARCH"

for PACKAGE in "${WORK}"/objects/haiku/*/packaging/packages/*.hpkg
do
	cp "$PACKAGE" $("$TOOLS/package/package" info -f "%fileName%" "$PACKAGE")
done
cp "$WORK"/download/*.hpkg .

cd ~/.tmp
tar cvzf ~/.tmp/haiku-${HAIKU_BRANCH}-$ARCH.tar.gz haiku-${HAIKU_BRANCH}-$ARCH

echo "Done!  ~/.tmp/haiku-${HAIKU_BRANCH}-$ARCH.tar.gz is ready for the Haiku buildmaster"
