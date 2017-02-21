#!/bin/bash

function extract_from_json {
	FIELD=$1
	EXTRACT=$(cat <<EOF
import json

with open('$BUILDER_CONFIG') as input:
	data = json.loads(input.read())

try:
	print data['ssh']['$FIELD']
except:
	pass
EOF
)
	python -c "$EXTRACT"
}


function print_usage_and_exit {
	echo "usage: $0 [--sftp] <builderConfig> [args]"
	exit 1
}


if [ -z "$1" ]
then
	print_usage_and_exit
fi

COMMAND="ssh"
case "$1" in
	--sftp)
		COMMAND="sftp"
		shift
	;;
esac

if [ -z "$1" -o ! -f "$1" ]
then
	print_usage_and_exit
fi


BUILDER_CONFIG="$1"
BASE_DIR="$(dirname "$BUILDER_CONFIG")"
HOST="$(extract_from_json host)"
USER="$(extract_from_json user)"
PORT="$(extract_from_json port)"
PORT=${PORT:-22}
PRIVATE_KEY_FILE="$(extract_from_json privateKeyFile)"
HOST_KEY_FILE="$(extract_from_json hostKeyFile)"

shift

"$COMMAND" -i "$BASE_DIR/$PRIVATE_KEY_FILE" \
	-o UserKnownHostsFile="$BASE_DIR/$HOST_KEY_FILE" \
	-o HashKnownHosts="no" \
	-o HostKeyAlgorithms="ssh-rsa" \
	-o Port="$PORT" "$USER@$HOST" $@
