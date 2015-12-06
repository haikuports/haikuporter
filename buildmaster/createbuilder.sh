#!/bin/bash

set -e

function ask_parameter {
	local PROMPT="$1"
	local DEFAULT="$2"
	local PARAMETER="$3"
	local REQUIRED="$4"
	local CHOICES="$5"

	while true
	do
		read -ep "$PROMPT: " -i "$DEFAULT" "$PARAMETER"
		if [ "$REQUIRED" != "yes" ]
		then
			return
		fi

		if [ -z "$CHOICES" -a ! -z "${!PARAMETER}" ]
		then
			return
		fi

		local CHOICE
		for CHOICE in $CHOICES
		do
			if [ "${!PARAMETER}" == "$CHOICE" ]
			then
				return
			fi
		done

		if [ -z "$CHOICES" ]
		then
			echo "$PROMPT is required"
		else
			echo "type one of: $CHOICES"
		fi
	done
}

function confirm {
	local PROMPT="$1"
	local ABORT_REASON="$2"
	local CONFIRMED

	ask_parameter "$PROMPT (y/n)" "" CONFIRMED yes "y n"
	if [ "$CONFIRMED" != "y" ]
	then
		echo "aborting due to: $ABORT_REASON"
		exit 1
	fi
}

ask_parameter "configuration base dir" "buildmaster/builders" BASE_DIR no
ask_parameter "key dir (relative to $BASE_DIR)" "keydir" KEY_DIR no
ask_parameter "builder name" "" BUILDER_NAME yes
ask_parameter "config file" "$BASE_DIR/$BUILDER_NAME.json" CONFIG_FILE yes

if [ -f "$CONFIG_FILE" ]
then
	confirm "overwrite existing config file $CONFIG_FILE?" "existing config"
fi

ask_parameter "SSH host" "" SSH_HOST yes
ask_parameter "SSH port" "22" SSH_PORT yes
ask_parameter "SSH user" "" SSH_USER yes

ask_parameter "private key file (will be generated)" \
	"$KEY_DIR/$BUILDER_NAME.key" PRIVATE_KEY_FILE yes
ABSOLUTE_PRIVATE_KEY_FILE="$BASE_DIR/$PRIVATE_KEY_FILE"
if [ -f "$ABSOLUTE_PRIVATE_KEY_FILE" ]
then
	confirm "overwrite existing private key $ABSOLUTE_PRIVATE_KEY_FILE?" \
		"existing private key"
	rm "$ABSOLUTE_PRIVATE_KEY_FILE"
fi

ask_parameter "host key file (will be filled from query)" \
	"$KEY_DIR/$BUILDER_NAME.hostkey" HOST_KEY_FILE yes
ABSOLUTE_HOST_KEY_FILE="$BASE_DIR/$HOST_KEY_FILE"
if [ -f "$ABSOLUTE_HOST_KEY_FILE" ]
then
	confirm "overwrite existing host key file $ABSOLUTE_HOST_KEY_FILE?" \
		"existing host key"
fi

ask_parameter "remote portstree path" "" PORTSTREE_PATH yes
ask_parameter "remote packages path" "$PORTSTREE_PATH/packages" \
	PORTSTREE_PACKAGES_PATH yes
ask_parameter "remote packages cache path" "$PORTSTREE_PACKAGES_PATH/.cache" \
	PORTSTREE_PACKAGES_CACHE_PATH yes
ask_parameter "remote haikuporter command" "" HAIKUPORTER_PATH yes
ask_parameter "haikuporter arguments" "" HAIKUPORTER_ARGS no

echo "writing config file to $CONFIG_FILE"
cat > "$CONFIG_FILE" <<JSON
{
	"name": "$BUILDER_NAME",
	"ssh": {
		"host": "$SSH_HOST",
		"port": "$SSH_PORT",
		"user": "$SSH_USER",
		"privateKeyFile": "$PRIVATE_KEY_FILE",
		"hostKeyFile": "$HOST_KEY_FILE"
	},
	"portstree": {
		"path": "$PORTSTREE_PATH",
		"packagesPath": "$PORTSTREE_PACKAGES_PATH",
		"packagesCachePath": "$PORTSTREE_PACKAGES_CACHE_PATH"
	},
	"haikuporter": {
		"path": "$HAIKUPORTER_PATH",
		"args": "$HAIKUPORTER_ARGS"
	}
}
JSON

echo "generating keypair"
ssh-keygen -t rsa -b 4096 -f "$ABSOLUTE_PRIVATE_KEY_FILE" -P "" \
	-C "$BUILDER_NAME"

echo "using ssh-keyscan to retrieve hostkey"
HOST_KEY=$(ssh-keyscan -t rsa -p "$SSH_PORT" "$SSH_HOST")

echo "please verify the retrieved host key (using the following remote command)"
echo "	ssh-keygen -E md5 -lf /system/settings/ssh/ssh_host_rsa_key"
ssh-keygen -lf /dev/stdin <<HOST_KEY
$HOST_KEY
HOST_KEY

confirm "is host key correct" "host key mismatch"

echo "storing host key to $ABSOLUTE_HOST_KEY_FILE"
echo "$HOST_KEY" > "$ABSOLUTE_HOST_KEY_FILE"

echo "configuration complete, please authorize the following public key"
ssh-keygen -yf "$ABSOLUTE_PRIVATE_KEY_FILE"
