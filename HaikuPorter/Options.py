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

from HaikuPorter.__version__ import __version__

from optparse import OptionParser


# -- global options -----------------------------------------------------------

global __Options__


# -- getOption ===-------------------------------------------------------------

def getOption(string):
	"""Fetches an option by name"""
	
	return getattr(__Options__, string)


# -- parseOptions -------------------------------------------------------------

def parseOptions():
	"""Does command line argument parsing"""

	parser =  OptionParser(
						usage='usage: %prog [options] portname[-portversion]',
						version='%prog ' + __version__)

	parser.add_option('-l', '--list', 
					  action='store_true', dest='list', default=False, 
					  help='list available ports')
	parser.add_option('-a', '--about', 
					  action='store_true', dest='about', default=False, 
					  help='show description of the specified port')
	parser.add_option('-s', '--search', 
					  action='store_true', dest='search', default=False, 
					  help='search for a port (regex)')
	parser.add_option('-o','--location', 
					  action='store_true', dest='location', default=False, 
					  help="print out the location of a recipe (via search, "
						   "for scripted editing)")
	
	parser.add_option('-q', '--quiet', 
					  action='store_true', dest='quiet', default=False, 
					  help="suppress output from build actions")
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
	parser.add_option('--nosrcpackage', 
					  action='store_false', dest='sourcePackageByDefault', 
					  default=True, 
					  help="don't create a source package by default")
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
					  default='/etc/haikuports.conf',
					  help='specifies the location of the global config file; '
					  	   'the default is "/etc/haikuports.conf"')
	parser.add_option('--command-package',
					  action='store', type='string', dest='commandPackage',
					  default='package',
					  help='specifies the "package" command; '
					  	   'the default is "package"')

	global __Options__

	(__Options__, args) = parser.parse_args()

	# some normalization
	if (getOption('patchFilesOnly') or not getOption('patch') 
		or getOption('extractPatchset')):
		setattr(__Options__, 'build', False)
	if not getOption('build'):
		setattr(__Options__, 'package', False)
	if getOption('enterChroot'):
		setattr(__Options__, 'sourcePackageByDefault', False)

	return (__Options__, args)
