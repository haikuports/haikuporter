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

for phase in ${recipePhases}; do
	if [ -n "$(type -t $phase)" ]; then
		echo "${phase}_DEFINED=1"
	fi
done
'''


# -----------------------------------------------------------------------------

# Shell scriptlet that is used to trigger one of the actions defined in a build
# recipe. The first placeholder is substituted with the configuration file, the 
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

# helper function to invoke a configure script with the correct directory
# arguments
runConfigure()
{
	# parse arguments
	varsToOmit=""

	while [ $# -ge 1 ]; do
		case $1 in
			--omit-dirs)
				shift 1
				if [ $# -lt 1 ]; then
					echo "runConfigure: \"--omit-dirs\" needs an argument!" >&2
				fi
				varsToOmit="$1"
				shift 1
				;;
			*)
				break
				;;
		esac
	done

	if [ $# -lt 1 ]; then
		echo "Usage: runConfigure [ --omit-dirs <dirsToOmit> ] <configure>" \
			"<argsToConfigure> ..." >&2
		echo "  <configure>" >&2
		echo "      The configure program to be called." >&2
		echo "  <dirsToOmit>" >&2
		echo "      Space-separated list of directory arguments not to be" >&2
		echo "      passed to configure, e.g. \"docDir manDir\" (single" >&2
		echo "      argument!)." >&2
		echo "  <argsToConfigure>" >&2
		echo "      The additional arguments passed to configure." >&2
		exit 1
	fi

	configure=$1
	shift 1

	# build the directory arguments string
	dirArgs=""
	for dir in $configureDirVariables; do
		if ! [[ "$varsToOmit" =~ (^|\ )${dir}($|\ ) ]]; then
			dirArgs="$dirArgs --${dir,,}=${!dir}"
		fi
	done

	$configure $dirArgs $@
}

prepareInstalledDevelLibsHelper()
{
	if [ $# -ne 1 ]; then
		echo "Usage: prepareInstalledDevelLibs <libBaseName>" >&2
		echo "Moves libraries from \$prefix/lib to \$prefix/develop/lib and" >&2
		echo "creates symlinks as required." >&2
		echo "  <libBaseName>" >&2
		echo "      The base name of the library, e.g. \"libfoo\"." >&2
		exit 1
	fi

	mkdir -p $developLibDir

	libBaseName=$1

	# find the shared library file and get its soname
	sharedLib=""
	sonameLib=""
	soname=""
	for lib in $libDir/${libBaseName}.so*; do
		if [ -f $lib -a ! -h $lib ]; then
			sharedLib=$lib
			sonameLine=$(readelf --dynamic $lib | grep SONAME)
			if [ -n "$sonameLine" ]; then
				soname=$(echo "$sonameLine" | sed 's,.*\[\(.*\)\].*,\1,')
				if [ "$soname" != "$sonameLine" ]; then
					sonameLib=$libDir/$soname
				else
					soname=""
				fi
			fi

			break;
		fi
	done

	# Move things/create symlinks: The shared library file and the symlink for
	# the soname remain where they are, but we create respective symlinks in the
	# development directory. Everything else is moved there.
	for lib in $libDir/${libBaseName}.*; do
		if [ "$lib" = "$sharedLib" ]; then
			ln -s ../../lib/$(basename $lib) $developLibDir/
		elif [ "$lib" = "$sonameLib" ]; then
			ln -s $(basename $sharedLib) $developLibDir/$soname
		else
			mv $lib $developLibDir/
		fi
	done
}

prepareInstalledDevelLibs()
{
	while [ $# -ge 1 ]; do
		prepareInstalledDevelLibsHelper $1
		shift 1
	done
}

fixPkgconfig()
{
	sourcePkgconfigDir=$libDir/pkgconfig
	targetPkgconfigDir=$developLibDir/pkgconfig

	if [ ! -d $sourcePkgconfigDir ]; then
		return
	fi


	mkdir -p $targetPkgconfigDir

	for file in $sourcePkgconfigDir/*; do
		name=$(basename $file)
		sed -e 's,^libdir=\(.*\),libdir=${prefix}/develop/lib,' \
			-e 's,^includedir=\(.*\),includedir=${prefix}/develop/headers,' \
			$file > $targetPkgconfigDir/$name
	done

	rm -r $sourcePkgconfigDir
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
	port \

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
if [ -e port/work* ]; then
	unmount port
fi

# mount dev, system-packagefs and common-packagefs
mount -t bindfs -p "source /dev" dev
mount -t packagefs -p "type system" boot/system
mount -t packagefs -p "type common" boot/common

# bind-mount the port directory to port/
portDir=$(dirname $recipeFile)
mount -t bindfs -p "source $portDir" port
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
unmount port

# wipe files and directories if it is ok to do so
if [[ $buildOk ]]; then
	echo "cleaning chroot folder"
	rmdir dev port
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
