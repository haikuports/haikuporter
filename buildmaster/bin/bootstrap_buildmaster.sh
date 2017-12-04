#!/bin/sh

if [ -z "$1" ]
then
	echo "usage: $0 [--jobs <n>]"
	echo "		[--buildtoos-dir <existingBuildtoolsRepo>]"
	echo "		[--haiku-dir <existingHaikuRepo>]"
	echo "		[--haikuporter-dir <existingHaikuPorterRepo>]"
	echo "		[--base-dir <baseDirToCreateAndFillWithRepos>]"
	echo "		<arch> [<secondaryArch1> [<secondaryArch2> ...]]"
	echo ""
	echo "This tool bootstraps a HaikuPorter buildmaster instance for the"
	echo "specified architecture(s). It builds the needed tools and gets the"
	echo "set of initial packages by building a Haiku image for the target"
	echo "architecture. It then clones a HaikuPorts repository and configures"
	echo "the ports tree and buildmaster."
	exit 1
fi

set -e

unset ARCH
unset SECONDARY_ARCHS

while [ $# -ne 0 ]
do
	case "$1" in
		--jobs)
			JOBS=$2
			shift
		;;

		--base-dir)
			BASE_DIR="$(realpath "$2")"
			shift
		;;

		--buildtools-dir)
			BUILDTOOLS_DIR="$(realpath "$2")"
			shift
		;;

		--haiku-dir)
			HAIKU_DIR="$(realpath "$2")"
			shift
		;;

		--haikuporter-dir)
			HAIKUPORTER_DIR="$(realpath "$2")"
			shift
		;;

		--*)
			echo "Invalid option: \"$1\""
			exit 1
		;;

		*)
			if [ -z "$ARCH" ]
			then
				ARCH=$1
			else
				SECONDARY_ARCHS="$SECONDARY_ARCHS $1"
			fi
		;;
	esac

	shift
done

if [ -z "$ARCH" ]
then
	echo "No architecture specified"
	exit 1
fi

if [ -z "$BASE_DIR" ]
then
	BASE_DIR=$(realpath "buildmaster_$ARCH")
	echo "Using default base directory $BASE_DIR"
else
	echo "Using base directory $BASE_DIR"
fi

if [ -e "$BASE_DIR" ]
then
	echo "Base directory \"$BASE_DIR\" already exists"
	exit 1
fi

mkdir -p "$BASE_DIR"
cd "$BASE_DIR"

if [ -z "$BUILDTOOLS_DIR" ]
then
	BUILDTOOLS_DIR="$(realpath "buildtools")"
	echo "Cloning buildtools repository to $BUILDTOOLS_DIR"
	git clone --depth=1 https://git.haiku-os.org/buildtools "$BUILDTOOLS_DIR"
else
	echo "Using existing buildtools repository in $BUILDTOOLS_DIR"
fi

if [ -z "$HAIKU_DIR" ]
then
	HAIKU_DIR="$(realpath "haiku")"
	echo "Cloning Haiku repository to $HAIKU_DIR"
	git clone --depth=1 https://git.haiku-os.org/haiku "$HAIKU_DIR"
else
	echo "Using existing Haiku repository in $HAIKU_DIR"
fi

GENERATED_DIR="$(realpath "generated")"
echo "Creating build output directory $GENERATED_DIR"
mkdir "$GENERATED_DIR"
cd "$GENERATED_DIR"

ARCH_ARGS=
for SECONDARY_ARCH in $SECONDARY_ARCHS
do
	ARCH_ARGS="$ARCH_ARGS --build-cross-tools $SECONDARY_ARCH"
done


# Configure and build cross tools.

echo "Configuring and building cross tools"
"$HAIKU_DIR/configure" "-j$JOBS" \
	--build-cross-tools "$ARCH" "$BUILDTOOLS_DIR" $ARCH_ARGS


# Build and extract jam.

echo "Building jam"
make -C "$BUILDTOOLS_DIR/jam"
cp "$BUILDTOOLS_DIR"/jam/bin.*/jam .


# Build Haiku image to generate package tools and initial packages.

echo "Building Haiku image"
./jam "-qj$JOBS" @nightly-raw


# Extract built package tools.

cd "$BASE_DIR"
TOOLS_DIR="$(realpath "package_tools")"
echo "Extracting built package tools to $TOOLS_DIR"
mkdir "$TOOLS_DIR"
cd "$TOOLS_DIR"

cp "$GENERATED_DIR"/objects/*/*/release/tools/package/package .
cp "$GENERATED_DIR"/objects/*/*/release/tools/package_repo/package_repo .
cp "$GENERATED_DIR"/objects/*/lib/lib*_build.so .

# Get HaikuPorter and HaikuPorts

cd "$BASE_DIR"
if [ -z "$HAIKUPORTER_DIR" ]
then
	HAIKUPORTER_DIR="$(realpath "haikuporter")"
	echo "Cloning HaikuPorter repository to $HAIKUPORTER_DIR"
	git clone --depth=1 https://github.com/haikuports/haikuporter \
		"$HAIKUPORTER_DIR"
else
	echo "Using existing HaikuPorter repository in $HAIKUPORTER_DIR"
fi

PORTS_DIR="$(realpath "haikuports")"
echo "Cloning HaikuPorts repository to $PORTS_DIR"
git clone --depth=1 https://github.com/haikuports/haikuports "$PORTS_DIR"


# Configure the ports tree.

cd "$PORTS_DIR"
echo "Configuring ports tree"

echo "TREE_PATH=\"$PORTS_DIR\"" > haikuports.conf
echo "LICENSES_DIRECTORY=\"$HAIKU_DIR/data/system/data/licenses\"" \
	>> haikuports.conf
echo "PACKAGE_COMMAND=\"$TOOLS_DIR/package\"" >> haikuports.conf
echo "PACKAGE_REPO_COMMAND=\"$TOOLS_DIR/package_repo\"" >> haikuports.conf
echo "PACKAGER=\"buildmaster $ARCH$SECONDARY_ARCHS" \
		"<buildmaster@haiku-os.org>\"" >> haikuports.conf
echo "TARGET_ARCHITECTURE=\"$ARCH\"" >> haikuports.conf
if [ ! -z "$SECONDARY_ARCHS" ]
then
	echo "SECONDARY_TARGET_ARCHITECTURES=\"$SECONDARY_ARCHS\"" \
		>> haikuports.conf
fi


# Configure the buildmaster instance.

cd "$PORTS_DIR"
echo "Configuring buildmaster environment"
mkdir buildmaster
cd buildmaster

echo "export HAIKUPORTER=\"$HAIKUPORTER_DIR/haikuporter\"" > config
echo "export LD_LIBRARY_PATH=\"$TOOLS_DIR\"" >> config
echo "export REPO_DIR=\"buildmaster/package_repository\"" >> config


# Populate initial set of packages.

INITIAL_PACKAGES_DIR="$(realpath "initial-packages")"
echo "Populating initial packages to $INITIAL_PACKAGES_DIR"
mkdir "$INITIAL_PACKAGES_DIR"
cd "$INITIAL_PACKAGES_DIR"

export LD_LIBRARY_PATH="$TOOLS_DIR"
for PACKAGE in "$GENERATED_DIR"/objects/haiku/*/packaging/packages/*.hpkg
do
	cp "$PACKAGE" $("$TOOLS_DIR/package" info -f "%fileName%" "$PACKAGE")
done

cp "$GENERATED_DIR"/download/*.hpkg .


# Cleanup.
rm "$GENERATED_DIR"/*.image


# Done.

echo ""
echo "Buildmaster instance bootstrapped in $PORTS_DIR."
echo ""
echo "Use createbuilder to create builder configurations."
echo "Then use buildmaster to build packages."
echo "Then use create_repo.sh to build repositories."
