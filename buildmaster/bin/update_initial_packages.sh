#!/bin/sh

if [ -z "$1" ]
then
	echo "usage: $0 [--jobs <n>]"
	echo "		--base-dir <baseDirWhereGeneratedAndHaikuportsAre>"
	echo ""
	echo "This tool builds new Haiku packages and updates the set of initial"
	echo "packages and package tools with these freshly built/downloaded ones."
	exit 1
fi

set -e

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

		--*)
			echo "Invalid option: \"$1\""
			exit 1
		;;
	esac

	shift
done

if [ -z "$BASE_DIR" ]
then
	echo "No base dir specified"
	exit 1
fi

echo "Using base directory $BASE_DIR"

if [ ! -e "$BASE_DIR" ]
then
	echo "Base directory \"$BASE_DIR\" does not exist"
	exit 1
fi

cd "$BASE_DIR"

GENERATED_DIR="$(realpath "generated")"
echo "Using build output directory $GENERATED_DIR"

if [ ! -e "$GENERATED_DIR" ]
then
	echo "Build output directory \"$GENERATED_DIR\" does not exist"
	exit 1
fi

cd "$GENERATED_DIR"

CLEAN_DIRS="objects/haiku/*/packaging/packages"
for DIR in $CLEAN_DIRS
do
	if [ -e "$DIR" ]
	then
		rm -r "$DIR"
	fi
done


# Build Haiku image to generate new initial packages.

echo "Building Haiku image"
./jam "-qj$JOBS" @nightly-raw


# Update package tools.

cd "$BASE_DIR"
TOOLS_DIR="$(realpath "package_tools")"
echo "Updating package tools in $TOOLS_DIR"

if [ ! -e "$TOOLS_DIR" ]
then
	mkdir "$TOOLS_DIR"
fi

cd "$TOOLS_DIR"

cp "$GENERATED_DIR"/objects/*/*/release/tools/package/package .
cp "$GENERATED_DIR"/objects/*/*/release/tools/package_repo/package_repo .
cp "$GENERATED_DIR"/objects/*/lib/lib*_build.so .


# Repopulate initial set of packages.

cd "$BASE_DIR"
INITIAL_PACKAGES_DIR="$(realpath "haikuports/buildmaster/initial-packages")"
echo "Repopulating initial packages to $INITIAL_PACKAGES_DIR"

if [ -e "$INITIAL_PACKAGES_DIR" ]
then
	rm -r "$INITIAL_PACKAGES_DIR"
fi

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
echo "Package tools updated in $TOOLS_DIR."
echo "Initial packages updated in $INITIAL_PACKAGES_DIR."
