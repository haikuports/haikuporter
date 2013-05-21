# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

from string import Template

# -----------------------------------------------------------------------------

# A list of all the commands/packages that are prerequired in the chroot, such
# that these scriptlets have all the commands available that they are using.
scriptletPrerequirements = r'''
	coreutils
	cmd:bash
	cmd:grep
	cmd:${targetMachinePrefix}readelf
	cmd:sed
'''

def getScriptletPrerequirements(targetMachineTripleAsName = None):
	"""Returns the list of prerequirements for executing scriptlets.
	   If targetMachineTriple is given, the prerequirements will be specialized
	   for cross-building for the given target machine."""
	
	targetMachinePrefix \
		= (targetMachineTripleAsName + '_') if targetMachineTripleAsName else ''
	
	prerequirements = Template(scriptletPrerequirements).substitute({
		'targetMachinePrefix': targetMachinePrefix,
	}).splitlines()

	return prerequirements

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

fixDevelopLibDirReferences()
{
	# Usage: fixDevelopLibDirReferences <file> ...
	# Replaces instances of $libDir in the given files with $developLibDir.
	for file in $*; do
		sed -i "s,$libDir,$developLibDir,g" $file
	done
}

prepareInstalledDevelLib()
{
	if [ $# -lt 1 ]; then
		echo >&2 "Usage: prepareInstalledDevelLib <libBaseName>" \
			"[ <soPattern> [ <pattern> ] ]"
		echo "Moves libraries from \$prefix/lib to \$prefix/develop/lib and" >&2
		echo >&2 "creates symlinks as required."
		echo >&2 "  <libBaseName>"
		echo >&2 "      The base name of the library, e.g. \"libfoo\"."
		echo >&2 "  <soPattern>"
		echo >&2 "      The glob pattern to be used to enumerate the shared"
		echo >&2 '      library entries. Is appended to $libDir/${libBaseName}'
		echo >&2 '      to form the complete pattern. Defaults to ".so*".'
		echo >&2 "  <pattern>"
		echo >&2 "      The glob pattern to be used to enumerate all library"
		echo >&2 '      entries. Is appended to $libDir/${libBaseName} to form'
		echo >&2 '      the complete pattern. Defaults to ".*".'
		
		exit 1
	fi

	mkdir -p $developLibDir

	libBaseName=$1
	soPattern=$2
	pattern=$3

	# find the shared library file and get its soname
	sharedLib=""
	sonameLib=""
	soname=""
	for lib in $libDir/${libBaseName}${soPattern:-.so*}; do
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
	for lib in $libDir/${libBaseName}${pattern:-.*}; do
		if [ "$lib" = "$sharedLib" ]; then
			ln -s ../../lib/$(basename $lib) $developLibDir/
		elif [ "$lib" = "$sonameLib" ]; then
			ln -s $(basename $sharedLib) $developLibDir/$soname
		else
			# patch .la files before moving
			if [[ "$lib" = *.la ]]; then
				fixDevelopLibDirReferences $lib
			fi

			mv $lib $developLibDir/
		fi
	done
}

prepareInstalledDevelLibs()
{
	while [ $# -ge 1 ]; do
		prepareInstalledDevelLib $1
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

packageEntries()
{
	# Usage: packageEntries <packageSuffix> <entry> ...
	# Moves the given entries to the packaging directory for the package
	# specified by package name suffix (e.g. "devel").
	# Entry paths can be absolute or relative to $prefix.

	if [ $# -lt 2 ]; then
		echo >&2 "Usage: packageEntries <packageSuffix> <entry> ..."
		exit 1
	fi

	packageSuffix="$1"
	shift 1

	packageLinksDir="$(dirname $portPackageLinksDir)"
	packageName="${portName}_$packageSuffix"
	packagePackageLinksDir="$packageLinksDir/$packageName-$portFullVersion"
	packagePrefix="$packagePackageLinksDir/.self"

	if [ ! -e "$packagePrefix" ]; then
		echo >&2 "packageEntries: error: \"$packageSuffix\" doesn't seem to be"
		echo >&2 "a valid package suffix."
		exit 1
	fi

	# move the entries
	for file in $*; do
		# If absolute, resolve to relative file name.
		if [[ "$file" = /* ]]; then
			if [[ "$file" =~ $prefix/(.*) ]]; then
				file=${BASH_REMATCH[1]}
			else
				echo >&2 "packageEntries: error: absolute entry \"$file\""
				echo >&2 "doesn't appear to be in \"$prefix\"."
			fi
		fi

		# make sure target containing directory exists and move there
		targetDir=$(dirname "$packagePrefix/$file")
		mkdir -p "$targetDir"
		mv "$prefix/$file" "$targetDir"
	done
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

# ignore sigint but stop on every error
trap '' SIGINT
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
if [ -e dev/console ]; then
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

# ignore sigint
trap '' SIGINT

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
