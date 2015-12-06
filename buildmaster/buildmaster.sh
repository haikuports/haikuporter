#!/bin/bash

BASE_DIR="$(pwd)/buildmaster"
CONFIG_FILE="$BASE_DIR/config"
source "$CONFIG_FILE"

if [ $? -ne 0 ]
then
	echo "configuration file $CONFIG_FILE couldn't be sourced"
	exit 1
fi

if [ -z "$HAIKUPORTER" ]
then
	echo "HAIKUPORTER environment variable not set"
	exit 1
fi

git pull --ff-only
if [ $? -ne 0 ]
then
	echo "git pull failed, manual fixing needed"
	exit 2
fi

REVISIONS_FILE="$BASE_DIR/processed_rev"
PREVIOUS_REVISION=$(cat "$REVISIONS_FILE")
HEAD_REVISION=$(git rev-parse HEAD)

if [ "$PREVIOUS_REVISION" == "$HEAD_REVISION" ]
then
	echo "no new revisions"
	exit 0
fi

echo "moving from $PREVIOUS_REVISION to $HEAD_REVISION"

ADDED_MODIFIED_PORTS=$(git diff-tree -r --name-only --diff-filter ACMTR \
		$PREVIOUS_REVISION..$HEAD_REVISION \
	| grep '\.recipe$' \
	| sed 's|.*/.*/\(.*\)-.*$|\1|' \
	| sort -u \
	| tr '\n' ' ')

if [ -z "$ADDED_MODIFIED_PORTS" ]
then
	echo "no ports changed"
	exit 0
fi

echo "added/modified ports: $ADDED_MODIFIED_PORTS"

# Expand possibly available secondary arch ports as well.
EXPANDED_PORTS=$("$HAIKUPORTER" --print-raw --literal-search-strings --search \
		$ADDED_MODIFIED_PORTS \
	| tr '\n' ' ')

echo "ports to be built: $EXPANDED_PORTS"

BUILDRUN_FILE="$BASE_DIR/last_buildrun"
BUILDRUN=$(expr $(cat "$BUILDRUN_FILE" 2> /dev/null) + 1)
BUILDRUN_OUTPUT_DIR="$BASE_DIR/buildruns/$BUILDRUN"
BUILDRUN_INDEX="$BASE_DIR/buildruns.txt"

echo "buildruns/$BUILDRUN" >> "$BUILDRUN_INDEX"
echo "$BUILDRUN" > "$BUILDRUN_FILE"

# Remove and relink the current output dir.
rm "$BASE_DIR/output"
ln -s "$BUILDRUN_OUTPUT_DIR/output" "$BASE_DIR"

"$HAIKUPORTER" --debug --build-master-output-dir="$BUILDRUN_OUTPUT_DIR" \
	--build-master $EXPANDED_PORTS

if [ $? -ne 0 ]
then
	echo "build master failed"
	exit 3
fi

echo "$HEAD_REVISION" > "$REVISIONS_FILE"
