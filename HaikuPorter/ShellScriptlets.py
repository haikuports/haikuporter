# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

# -----------------------------------------------------------------------------

# Shell scriptlet that is used to execute a config file and output all the 
# configuration values (in the form of environment variables) which have been
# set explicitly in the configuration file. The first placeholder is substituted 
# with the configuration file, the second with a '|'-separated list of 
# supported configuration keys.
# Note: this script requires bash, it won't work with any other shells
configFileEvaluatorScript = r'''# wrapper script for evaluating config/recipe

# stop on every error
set -e

# source the configuration file
. %s >/dev/null

# select all environment vars we are interested in, which are all vars that
# match the given keys plus the ones that extend a given key by '_<something>'
supportedKeys=$(set | grep -E -o '^(%s)(_[0-9a-zA-Z_]+)?=' | cut -d= -f1)

# output the supported environment vars which have been set, quoting any 
# newlines in their values
NL=$'\n'
for key in $supportedKeys
do
	if [[ -n ${!key+dummy} ]]
	then
		value=${!key}
		echo "$key=${value//$NL/\\n}"
	fi
done
'''


# -----------------------------------------------------------------------------

# Shell scriptlet that is used to trigger one of the actions defined in a build
# recipe.The first placeholder is substituted with the configuration file, the 
# second one with the action to be invoked.
recipeActionScript = r'''# wrapper scriptlet for running an action

# stop on every error
set -e

# provide defaults for every action
BUILD()
{
	true
}

INSTALL()
{
	true
}

TEST()
{
	true
}

# source the configuration file
. %s >/dev/null

# invoke the requested action
action='%s'
if [[ $quiet ]]; then
	$action >/dev/null
else
	$action
fi
'''


# -----------------------------------------------------------------------------

# Shell scriptlet that prepares a chroot environment for entering.
# Invoked with $packages filled with the list of packages that should
# be activated (via common/packages) and $recipeFilePath pointing to the
# recipe file.
setupChrootScript = r'''

# stop on every error
set -e

mkdir -p \
	dev \
	boot/system/packages \
	boot/common/cache/tmp \
	boot/common/packages \
	boot/common/settings/etc \

ln -sfn /boot/system system
ln -sfn /boot/system/bin bin
ln -sfn /boot/system/package-links packages
ln -sfn /boot/common/cache/tmp tmp
ln -sfn /boot/common/settings/etc etc
ln -sfn /boot/common/var var

# remove any packages that may be lying around
rm -f boot/common/packages/*.hpkg
rm -f boot/system/packages/*.hpkg

# link all system packages
ln -s /boot/system/packages/*.hpkg boot/system/packages/

# link the list of required common packages
for pkg in $packages; do 
	ln -sfn "$pkg" boot/common/packages/
done

# copy recipe file into the chroot
cp $recipeFile port.recipe

# silently unmount if needed, just to be one the safe side
if [ -e dev/null ]; then
	unmount dev
fi
if [ -e boot/system/bin ]; then
	unmount boot/system
fi
if [ -e boot/common/bin ]; then
	unmount boot/common
fi

# mount dev, system-packagefs and common-packagefs
mount -t bindfs -p "source /dev" dev
mount -t packagefs -p "type system" boot/system
mount -t packagefs -p "type common" boot/common
'''


# -----------------------------------------------------------------------------

# Shell scriptlet that cleans up a chroot environment after it has been exited.
# Invoked with $buildOk indicating if the build has worked and thus all paths 
# required for building only should be wiped.
cleanupChrootScript = r'''

# try to make sure we really are in a work directory
if ! echo $(basename $PWD) | grep -qE '^work-'; then 
	echo "cleanupChroot invoked in $PWD, which doesn't seem to be a work dir!"
	exit 1
fi

unmount dev
unmount boot/system
unmount boot/common

# wipe files and directories if it is ok to do so
if [[ $buildOk ]]; then
	echo "cleaning chroot folder"
	rmdir dev
	rm -rf \
		boot \
		build-packages \
		package-infos \
		packages \
		packaging \
		repository
	rm -f \
		.PackageInfo \
		bin \
		etc \
		port.recipe \
		system \
		tmp \
		var
else
	echo "keeping chroot folder $PWD intact for inspection"
fi
'''
