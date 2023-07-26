#!/bin/sh

if [ -z "$1" ]
then
	echo "usage: $0 <existingPackageListPathOrURL>"
	echo ""
	echo "This tool finds ports that have missing packages."
	exit 1
fi

set -e

HAIKUPORTER=${HAIKUPORTER:-haikuporter}
VALID_PACKAGE_LIST=$(mktemp)
PRESENT_PACKAGE_LIST=$(mktemp)

case "$1" in
	http://*|https://*)
		curl -qs "$1" | sort > $PRESENT_PACKAGE_LIST
	;;
	*)
		sort "$1" > $PRESENT_PACKAGE_LIST
	;;
esac

$HAIKUPORTER --list-packages --print-filenames --active-versions-only \
	| sort > $VALID_PACKAGE_LIST

comm -23 $VALID_PACKAGE_LIST $PRESENT_PACKAGE_LIST \
	| xargs "$HAIKUPORTER" --ports-for-packages | sort -u

rm $VALID_PACKAGE_LIST $PRESENT_PACKAGE_LIST
