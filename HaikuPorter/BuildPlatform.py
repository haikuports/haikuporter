# -*- coding: utf-8 -*-
#
# Copyright 2013 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.GlobalConfig import globalConfiguration
from HaikuPorter.Options import getOption
from HaikuPorter.PackageInfo import PackageInfo
from HaikuPorter.RecipeTypes import MachineArchitecture
from HaikuPorter.RequiresUpdater import RequiresUpdater
from HaikuPorter.Utils import (check_output, printError, sysExit)

import os
import platform
from subprocess import check_call, CalledProcessError


buildPlatform = None


# -- BuildPlatform class ------------------------------------------------------

class BuildPlatform(object):
	def __init__(self):
		pass

	def init(self, treePath, machineTriple):
		self.machineTriple = machineTriple

		self.treePath = treePath

	def getName(self):
		return platform.system()

	def getMachineTriple(self):
		return self.machineTriple

	def getArchitecture(self):
		index = self.machineTriple.find('-')
		if index >= 0:
			return self.machineTriple[:index]
		return self.machineTriple

	def getLicensesDirectory(self):
		directory = getOption('licensesDirectory')
		if not directory:
			directory = (self.findDirectory('B_SYSTEM_DIRECTORY')
				+ '/data/licenses')
		return directory

	def getSystemMimeDbDirectory(self):
		directory = getOption('systemMimeDB')
		if not directory:
			directory = (self.findDirectory('B_SYSTEM_DIRECTORY')
				+ '/data/mime_db')
		return directory


# -- BuildPlatformHaiku class -------------------------------------------------

class BuildPlatformHaiku(BuildPlatform):
	def __init__(self):
		super(BuildPlatformHaiku, self).__init__()

	def init(self, treePath):
		# get system haiku package version and architecture
		haikuPackageInfo = PackageInfo('/system/packages/haiku.hpkg')
		self.haikuVersion = haikuPackageInfo.getVersion()
		machine = MachineArchitecture.getTripleFor(
			haikuPackageInfo.getArchitecture())
		if not machine:
			sysExit('Unsupported Haiku build platform architecture %s'
				% haikuPackageInfo.getArchitecture())

		super(BuildPlatformHaiku, self).init(treePath, machine)

		self.findDirectoryCache = {}

	def isHaiku(self):
		return True

	def getHaikuVersion(self):
		return self.haikuVersion

	def usesChroot(self):
		return getOption('chroot')

	def findDirectory(self, which):
		"""wraps invocation of 'finddir', uses caching"""
		if not which in self.findDirectoryCache:
			self.findDirectoryCache[which] \
				= check_output(['/bin/finddir', which]).rstrip()  # drop newline
		return self.findDirectoryCache[which]

	def resolveDependencies(self, packageInfoFiles, repositories,
			isPrerequired):
		# When resolving pre-requirements, also consider the build host's
		# common package directory. In either case add the system packages
		# directory.
		repositories = repositories.copy()
		if isPrerequired:
			repositories.append(
				buildPlatform.findDirectory('B_COMMON_PACKAGES_DIRECTORY'))
		repositories.append(
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))

		args = ([ '/bin/pkgman', 'resolve-dependencies' ]
				+ packageInfoFiles + repositories)
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(args, stderr=devnull)
			return output.splitlines()
		except CalledProcessError:
			# call again, so the error is shown
			try:
				check_call(args)
			except:
				pass

	def isSystemPackage(self, packagePath):
		return packagePath.startswith(
			findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))


# -- BuildPlatformUnix class --------------------------------------------------

class BuildPlatformUnix(BuildPlatform):
	def __init__(self):
		super(BuildPlatformUnix, self).__init__()

	def init(self, treePath):
		# get the machine triple from gcc
		machine = check_output('gcc -dumpmachine', shell=True).strip()

		super(BuildPlatformUnix, self).init(treePath, machine)

		if getOption('commandPackage') == 'package':
			sysExit('--command-package must be specified on this build '
				'platform!')
		if getOption('commandMimeset') == 'mimeset':
			sysExit('--command-mimeset must be specified on this build '
				'platform!')
		if not getOption('systemMimeDB'):
			sysExit('--system-mimedb must be specified on this build '
				'platform!')

		if not getOption('crossTools'):
			sysExit('--cross-tools must be specified on this build platform!')
		self.originalCrossToolsDir = getOption('crossTools')

		self.findDirectoryMap = {
			'B_PACKAGE_LINKS_DIRECTORY': '/packages',
			'B_SYSTEM_DIRECTORY': '/boot/system',
			'B_SYSTEM_PACKAGES_DIRECTORY': '/boot/system/packages',
			'B_COMMON_PACKAGES_DIRECTORY': '/boot/common/packages',
			}

		targetArchitecture = globalConfiguration['TARGET_ARCHITECTURE'].lower()
		self.targetMachineTriple \
			= MachineArchitecture.getTripleFor(targetArchitecture)
		targetMachineAsName = self.targetMachineTriple.replace('-', '_')

		self.implicitBuildProvides = set([
			'haiku',
			'haiku_devel',
			'binutils_cross_' + targetArchitecture,
			'gcc_cross_' + targetArchitecture,
			'coreutils',
			'cmd:aclocal',
			'cmd:autoconf',
			'cmd:automake',
			'cmd:autoreconf',
			'cmd:bash',
			'cmd:grep',
			'cmd:libtoolize',
			'cmd:make',
			'cmd:makeinfo',
			'cmd:perl',
			'cmd:sed',
			'cmd:' + targetMachineAsName + '_objcopy',
			'cmd:' + targetMachineAsName + '_readelf',
			'cmd:' + targetMachineAsName + '_strip',
			])

	def isHaiku(self):
		return False

	def usesChroot(self):
		return False

	def findDirectory(self, which):
		if not which in self.findDirectoryMap:
			sysExit('Unsupported findDirectory() constant "%s"' % which)
		return self.findDirectoryMap[which]

	def resolveDependencies(self, packageInfoFiles, repositories,
			isPrerequired):
		# We don't have any packages for build host dependencies. So when
		# resolving pre-requires, we just check that they are available
		# implicitly.
		if isPrerequired:
			for packageInfoFile in packageInfoFiles:
				packageInfo = PackageInfo(packageInfoFile)
				for requires in packageInfo.getRequires():
					if not requires.getName() in self.implicitBuildProvides:
						printError('requires "%s" of package "%s" could not be '
							'resolved' % (str(requires), packageInfoFile))
						raise LookupError()
			return []

		# Use the RequiresUpdater to resolve the dependencies.
		requiresUpdater = RequiresUpdater([], packageInfoFiles)
		for repository in repositories:
			requiresUpdater.addPackages(repository)

		for packageInfoFile in packageInfoFiles:
			requiresUpdater.addPackageFile(packageInfoFile)

		pendingPackages = list(packageInfoFiles)
		result = set(pendingPackages)

		while pendingPackages:
			package = pendingPackages.pop()
			packageInfo = PackageInfo(package)
			for requires in packageInfo.getRequires():
				# TODO: Once we have a strict separation of build host and
				# target requires, this check should be omitted.
				if requires.getName() in self.implicitBuildProvides:
					continue

				provides = requiresUpdater.getMatchingProvides(requires)
				if not provides:
					printError('requires "%s" of package "%s" could not be '
						'resolved' % (str(requires), package))
					raise LookupError()

				providingPackage = provides.getPackage()
				if not providingPackage in result:
					result.add(providingPackage)
					pendingPackages.append(providingPackage)

		return list(result - set(packageInfoFiles))

	def isSystemPackage(self, packagePath):
		return False


# init buildPlatform
if platform.system() == 'Haiku':
	buildPlatform = BuildPlatformHaiku()
else:
	buildPlatform = BuildPlatformUnix()
