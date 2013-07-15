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
import shutil
from subprocess import check_call, CalledProcessError


buildPlatform = None


# -- BuildPlatform class ------------------------------------------------------

class BuildPlatform(object):
	def __init__(self):
		pass

	def init(self, treePath, architecture, machineTriple):
		self.architecture = architecture
		self.machineTriple = machineTriple
		self.treePath = treePath

	def getName(self):
		return platform.system()

	def getMachineTriple(self):
		return self.machineTriple

	def getArchitecture(self):
		return self.architecture

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

		super(BuildPlatformHaiku, self).init(treePath,
			haikuPackageInfo.getArchitecture(), machine)

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
		repositories = list(repositories)
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
			raise

	def isSystemPackage(self, packagePath):
		return packagePath.startswith(
			self.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))

	def activateBuildPackage(self, workDir, packagePath):
		# activate the build package
		packagesDir = buildPlatform.findDirectory('B_COMMON_PACKAGES_DIRECTORY')
		activeBuildPackage = packagesDir + '/' + os.path.basename(packagePath)
		if os.path.exists(activeBuildPackage):
			os.remove(activeBuildPackage)

		if not buildPlatform.usesChroot():
			# may have to cross devices, so better use a symlink
			os.symlink(packagePath, activeBuildPackage)
		else:
			# symlinking a package won't work in chroot, but in this
			# case we are sure that the move won't cross devices
			os.rename(packagePath, activeBuildPackage)
		return activeBuildPackage

	def getCrossToolsBinPath(self, workDir):
		return '/boot/common/develop/tools/bin'

	def getInstallDestDir(self, workDir):
		return None

	def setupNonChrootBuildEnvironment(self, workDir, requiredPackages):
		sysExit('setupNonChrootBuildEnvironment() not supported on Haiku')

	def cleanNonChrootBuildEnvironment(self, workDir, buildOK):
		sysExit('cleanNonChrootBuildEnvironment() not supported on Haiku')


# -- BuildPlatformUnix class --------------------------------------------------

class BuildPlatformUnix(BuildPlatform):
	def __init__(self):
		super(BuildPlatformUnix, self).__init__()

	def init(self, treePath):
		# get the machine triple from gcc
		machine = check_output('gcc -dumpmachine', shell=True).strip()

		# compute/guess architecture from the machine
		index = machine.find('-')
		if index >= 0:
			return machine[:index]
		architecture = machine[:index] if index >= 0 else machine

		super(BuildPlatformUnix, self).init(treePath, architecture, machine)

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

		self.crossDevelPackage = getOption('crossDevelPackage')
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

	def activateBuildPackage(self, workDir, packagePath):
		# get the package info
		packageInfo = PackageInfo(packagePath)
		installPath = packageInfo.getInstallPath()
		if not installPath:
			sysExit('Build package "%s" doesn\'t have an install path'
				% packagePath)

		# create the package links directory for the package and the .self
		# symlink
		packageLinksDir = (self.getInstallDestDir(workDir) + '/packages/'
			+ packageInfo.getName() + '-' + packageInfo.getVersion())
		os.mkdir(packageLinksDir)
		os.symlink(installPath, packageLinksDir + '/.self')

		return packageLinksDir

	def getCrossToolsBinPath(self, workDir):
		return self._getCrossToolsPath(workDir) + '/bin'

	def getInstallDestDir(self, workDir):
		return workDir + '/cross-sysroot'

	def setupNonChrootBuildEnvironment(self, workDir, requiredPackages):
		# re-init the global work dir
		sysrootDir = self.getInstallDestDir(workDir)
		if os.path.exists(sysrootDir):
			shutil.rmtree(sysrootDir)
		os.mkdir(sysrootDir)

		os.mkdir(sysrootDir + '/packages')
		os.mkdir(sysrootDir + '/boot')
		os.mkdir(sysrootDir + '/boot/system')
		os.mkdir(sysrootDir + '/boot/common')

		crossToolsDir = self._getCrossToolsPath(workDir)
		os.mkdir(crossToolsDir)

		toolsMachineTriple = self._getCrossToolsMachineTriple()

		# prepare the system include and library directories
		toolsMachineDir = self.originalCrossToolsDir + '/' + toolsMachineTriple
		machineDir = crossToolsDir + '/' + self.targetMachineTriple
		os.mkdir(machineDir)

		toolsIncludeDir = toolsMachineDir + '/sys-include'
		includeDir = machineDir + '/sys-include'
		os.symlink(sysrootDir + '/boot/system/develop/headers', includeDir)

		toolsLibDir = toolsMachineDir + '/lib'
		libDir = machineDir + '/lib'
		os.symlink(sysrootDir + '/boot/system/develop/lib', libDir)

		# Prepare the bin dir -- it will be added to PATH and must contain the
		# tools with the expected machine triple prefix.
		toolsBinDir = self.originalCrossToolsDir + '/bin'
		binDir = crossToolsDir + '/bin'
		if toolsMachineTriple != self.targetMachineTriple:
			os.mkdir(binDir)
			for tool in os.listdir(toolsBinDir):
				toolLink = tool
				if tool.startswith(toolsMachineTriple):
					toolLink = tool.replace(toolsMachineTriple,
						self.targetMachineTriple, 1)
				os.symlink(toolsBinDir + '/' + tool, binDir + '/' + toolLink)
		else:
			os.symlink(toolsBinDir, binDir)

		# Symlink the include and lib dirs back to the cross-tools machine
		# directory. These are the path that are built into the tools.
		if os.path.lexists(toolsIncludeDir):
			os.remove(toolsIncludeDir)
		os.symlink(includeDir, toolsIncludeDir)

		if os.path.lexists(toolsLibDir):
			if os.path.isdir(toolsLibDir):
				# That's the original lib dir -- rename it.
				os.rename(toolsLibDir, toolsLibDir + '.orig')
			else:
				os.remove(toolsLibDir)
		os.symlink(libDir, toolsLibDir)

		# extract the haiku_cross_devel_sysroot package
		args = [ getOption('commandPackage'), 'extract', '-C',
			sysrootDir + '/boot/system', self.crossDevelPackage ]
		check_call(args)

		# extract the required packages
		for package in requiredPackages:
			args = [ getOption('commandPackage'), 'extract', '-C',
				sysrootDir + '/boot/common', package ]
			check_call(args)

	def cleanNonChrootBuildEnvironment(self, workDir, buildOK):
		# remove the symlinks we created in the cross tools tree
		sysrootDir = self.getInstallDestDir(workDir)
		toolsMachineTriple = self._getCrossToolsMachineTriple()
		toolsMachineDir = self.originalCrossToolsDir + '/' + toolsMachineTriple

		toolsIncludeDir = toolsMachineDir + '/sys-include'
		if os.path.lexists(toolsIncludeDir):
			os.remove(toolsIncludeDir)

		toolsLibDir = toolsMachineDir + '/lib'
		if os.path.lexists(toolsLibDir):
			os.remove(toolsLibDir)
			# rename back the original lib dir
			originalToolsLibDir = toolsLibDir + '.orig'
			if os.path.lexists(originalToolsLibDir):
				os.rename(originalToolsLibDir, toolsLibDir)

		# remove the global work dir, if the build went fine
		if buildOK and os.path.exists(sysrootDir):
			shutil.rmtree(sysrootDir)

	def _getCrossToolsMachineTriple(self):
		# In case of gcc2 our machine triple doesn't agree with that of the
		# cross tools.
		if self.targetMachineTriple == 'i586-pc-haiku_gcc2':
			return 'i586-pc-haiku'
		return self.targetMachineTriple

	def _getCrossToolsPath(self, workDir):
		return self.getInstallDestDir(workDir) + '/cross-tools'


# -----------------------------------------------------------------------------

# init buildPlatform
if platform.system() == 'Haiku':
	buildPlatform = BuildPlatformHaiku()
else:
	buildPlatform = BuildPlatformUnix()
