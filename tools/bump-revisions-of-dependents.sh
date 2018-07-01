#!/bin/bash
#
# Copyright 2018, Haiku, Inc. All rights reserved.
# Distributed under the terms of the MIT license.
#

if [ "$#" -lt 1 ]; then
	echo "A tool to bump the revisions of all recipes that depend on another recipe."
	echo "Usage: $0 <path/to/dependee/recipe>"
	exit 1
fi

RECIPE=$1
if [ ! -e "$1" ]; then
	echo "$1 does not exist!"
	exit 1
fi

# some stub functions so we don't get errors/warnings
getPackagePrefix()
{
	:
}
defineDebugInfoPackage()
{
	:
}

# some utility functions
processProvides()
{
	ret=""
	for provide in $1; do
		if [ "$provide" = "compat" ]; then
			continue
		fi
		# grab only the provides that start with a letter (ignore >=, versions, etc.)
		if [[ "$provide" =~ ^[A-Za-z].*$ ]]; then
			ret="${ret} ${provide}"
		fi
	done
	echo $ret
}
providesToGrep()
{
	ret=""
	for provide in $1; do
		ret="${ret}${provide}|"
	done
	echo ${ret::-1}
}

source $RECIPE
GREP=$(providesToGrep "$(processProvides "$PROVIDES_devel")")
FILES=$(git grep --name-only -E $GREP \
	$(git rev-parse --show-toplevel))
BUMPED=0
for file in $FILES; do
	source $file
		# yes, this potentially overwrites global variables, but
		# for now at least it's probably not an issue
	echo $(processProvides "$BUILD_REQUIRES") | egrep $GREP >/dev/null
	if [ $? -eq 0 ]; then
		echo "bumping $file"
		REVISION=$((REVISION+1))
		sed -i "s/.*REVISION=.*/REVISION=\"$REVISION\"/" $file
		BUMPED=$((BUMPED+1))
	fi
done
echo ""
echo "done; $BUMPED recipes bumped."
