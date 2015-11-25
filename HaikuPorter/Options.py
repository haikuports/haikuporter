# -*- coding: utf-8 -*-
#
# Copyright 2007-2011 Brecht Machiels
# Copyright 2009-2010 Chris Roberts
# Copyright 2009-2011 Scott McCreary
# Copyright 2009 Alexander Deynichenko
# Copyright 2009 HaikuBot (aka RISC)
# Copyright 2010-2011 Jack Laxson (Jrabbit)
# Copyright 2011 Ingo Weinhold
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .__version__ import __version__
from .Utils import isCommandAvailable, warn

from optparse import OptionParser


# -- global options -----------------------------------------------------------

global __Options__


# -- getOption ===-------------------------------------------------------------

def getOption(string):
	"""Fetches an option by name"""

	return getattr(__Options__, string)


# -- splitCommaSeparatedList --------------------------------------------------

def setCommaSeparatedList(option, opt, value, parser):
	setattr(parser.values, option.dest, value.split(','))


# -- parseOptions -------------------------------------------------------------

def parseOptions():
	"""Does command line argument parsing"""

	parser =  OptionParser(
						usage='usage: %prog [options] portname[-portversion]',
						version='%prog ' + __version__)

	parser.add_option('-l', '--list',
					  action='store_true', dest='list', default=False,
					  help='list available ports')
	parser.add_option('--list-packages',
					  action='store_true', dest='listPackages', default=False,
					  help='list available packages')
	parser.add_option('-a', '--about',
					  action='store_true', dest='about', default=False,
					  help='show description of the specified port')
	parser.add_option('-s', '--search',
					  action='store_true', dest='search', default=False,
					  help='search for a port (regex)')
	parser.add_option('--search-packages',
					  action='store_true', dest='searchPackages', default=False,
					  help='search for a package (regex)')
	parser.add_option('-o','--location',
					  action='store_true', dest='location', default=False,
					  help="print out the location of a recipe (via search, "
						   "for scripted editing)")

	parser.add_option('-q', '--quiet',
					  action='store_true', dest='quiet', default=False,
					  help="suppress output from build actions")
	parser.add_option('-v', '--verbose',
					  action='store_true', dest='verbose', default=False,
					  help="show why the recipe is broken")
	parser.add_option('-y', '--yes',
					  action='store_true', dest='yes', default=False,
					  help="answer yes to all questions")
	parser.add_option('-j', '--jobs',
					  action='store', type="int", dest='jobs', default=1,
					  help="the number of concurrent jobs to build with")
	parser.add_option('-S', '--strict-policy',
					  action='store_true', dest='strictPolicy', default=False,
					  help="require strict packaging policy adherence; "
						"packaging will fail on any policy violation")
	parser.add_option('--debug',
					  action='store_true', dest='debug', default=False,
					  help="show Python stack traces for fatal errors")

	parser.add_option('-n', '--nopatch',
					  action='store_false', dest='patch', default=True,
					  help="don't patch the sources, just download and unpack")
	parser.add_option('-e', '--extract-patchset',
					  action='store_true', dest='extractPatchset', default=False,
					  help='extract current patchset(s) from port source(s)')
	parser.add_option('-G', '--init-git',
					  action='store_true', dest='initGitRepo', default=False,
					  help='create git-repo(s) for port source(s)')
	parser.add_option('-B', '--patch-files-only',
					  action='store_true', dest='patchFilesOnly',
					  default=False,
					  help="don't build the port, just download, unpack and "
						   "apply patch files; don't call PATCH() though")
	parser.add_option('-b', '--nobuild',
					  action='store_false', dest='build', default=True,
					  help="don't build the port, just download, unpack and "
						   "patch")
	parser.add_option('-p', '--nopackage',
					  action='store_false', dest='package', default=True,
					  help="don't create package, stop after build")
	parser.add_option('--no-dependencies',
					  action='store_true', dest='noDependencies', default=False,
					  help="ignore any dependencies, just build the given port")
	parser.add_option('--get-dependencies',
					  action='store_true', dest='getDependencies', default=False,
					  help="install all needed dependencies, then build the port")
	parser.add_option('--no-source-packages',
					  action='store_true', dest='noSourcePackages',
					  default=False,
					  help="don't create any source packages")
	parser.add_option('--test',
					  action='store_true', dest='test', default=False,
					  help="run tests on resulting binaries")
	parser.add_option('-C', '--nochroot',
					  action='store_false', dest='chroot', default=True,
					  help="build without a chroot()-environment - meant "
						   "for debugging the build/install process")
	parser.add_option('-E', '--enter-chroot',
					  action='store_true', dest='enterChroot', default=False,
					  help="just enter the chroot()-environment, do not build")
	parser.add_option('-f', '--force',
					  action='store_true', dest='force', default=False,
					  help="force to perform the steps (unpack, patch, build)")
	parser.add_option('-F', '--preserve-flags',
					  action='store_true', dest='preserveFlags', default=False,
					  help="don't clear any flags when a changed recipe file "
						   "is detected")

	parser.add_option('-P', '--portsfile',
					  action='store', type='string', dest='portsfile',
					  default='',
					  help="handle all ports in the given file")
	parser.add_option('--create-source-packages',
					  action='store_true',
					  dest='createSourcePackages',
					  default=False,
					  help="build only the (regular) source packages")
	parser.add_option('--create-source-packages-for-bootstrap',
					  action='store_true',
					  dest='createSourcePackagesForBootstrap',
					  default=False,
					  help="build only source packages as required by the"
						   "bootstrap image")
	parser.add_option('--do-bootstrap',
					  action='store_true', dest='doBootstrap', default=False,
					  help="build all packages with cyclic dependencies")

	parser.add_option('-w', '--why',
					  action='store', type='string', dest='why',
					  default='',
					  help='determine why the given port is pulled in as a '
						   'dependency of the port to be built')
	parser.add_option('-D', '--analyze-dependencies',
					  action='store_true', dest='analyzeDependencies',
					  default=False,
					  help="analyze dependencies between ports and print "
						"information; no port parameter required")

	parser.add_option('-c', '--clean',
					  action='store_true', dest='clean', default=False,
					  help="clean the working directory of the specified port")

	parser.add_option('-g', '--get',
					  action='store_true', dest='get', default=False,
					  help="get/update the ports tree")
	parser.add_option('-t', '--tree',
					  action='store_true', dest='tree', default=False,
					  help="print out the location of the haikuports source "
						   "tree")
	parser.add_option('--lint',
					  action='store_true', dest='lint', default=False,
					  help="scan the ports tree for problems")

	parser.add_option('--config',
					  action='store', type='string', dest='configFile',
					  default=None,
					  help='specifies the location of the global config file; '
						   'the default is "~/config/settings/haikuports.conf"')
	parser.add_option('--cross-devel-package',
					  action='store', type='string', dest='crossDevelPackage',
					  default=None,
					  help='path to the cross development package (the actual '
						   '"sysroot" package); the default (when '
						   'cross-building at all) is the one to be found in '
						   '"/boot/system/develop/cross" matching the target '
						   'architecture')
	parser.add_option('--secondary-cross-devel-packages',
					  action='callback', callback=setCommaSeparatedList,
					  type='string', dest='secondaryCrossDevelPackages',
					  default=[],
					  help='comma-separated list of paths to a secondary cross '
							'development package (the actual "sysroot" '
							'package); one path must be specified for each '
							'configured secondary target architecture '
							'(specified in the same order)')
	parser.add_option('--licenses',
					  action='store', type='string', dest='licensesDirectory',
					  default=None,
					  help='path to the directory containing the well-known '
						   'licenses; the default is '
						   '"<systemDir>/data/licenses"')
	parser.add_option('--system-mimedb',
					  action='store', type='string', dest='systemMimeDB',
					  default=None,
					  help='path to the directory containing the system '
						   'MIME DB; the default is "<systemDir>/data/mime_db"')
	parser.add_option('--command-mimeset',
					  action='store', type='string', dest='commandMimeset',
					  default=None,
					  help='specifies the "mimeset" command; '
						   'the default is "mimeset"')
	parser.add_option('--command-package',
					  action='store', type='string', dest='commandPackage',
					  default=None,
					  help='specifies the "package" command; '
						   'the default is "package"')
	parser.add_option('--cross-tools',
					  action='store', type='string', dest='crossTools',
					  default=None,
					  help='specifies the path to the cross-tools directory '
						   'created by the Haiku build system\'s configure '
						   'script')

	parser.add_option('--no-system-packages', action='store_true',
		dest='noSystemPackages', default=False,
		help='do not use system packages to resolve dependencies')

	parser.add_option('--list-build-dependencies', action='store_true',
		dest='listBuildDependencies', default=False,
		help='list build dependencies of a port')

	parser.add_option('--build-master', action='store_true', dest='buildMaster',
		default=False,
		help='run as build master and delegate builds to builders')

	parser.add_option('--print-raw', action='store_true', dest='printRaw',
		default=False, help='print machine readable output for use by scripts')

	global __Options__

	(__Options__, args) = parser.parse_args()

	# some normalization
	if (getOption('patchFilesOnly') or not getOption('patch')
		or getOption('extractPatchset')):
		setattr(__Options__, 'build', False)
	if not getOption('build'):
		setattr(__Options__, 'package', False)
	if getOption('enterChroot'):
		setattr(__Options__, 'noSourcePackages', True)
		setattr(__Options__, 'noDependencies', True)
	elif not isCommandAvailable('git'):
		if not getOption('doBootstrap'):
			warn("deactivating creation of source packages as 'git' is not "
				 "available")
		setattr(__Options__, 'noSourcePackages', True)

	return (__Options__, args)
