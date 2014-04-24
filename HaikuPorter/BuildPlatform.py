# -*- coding: utf-8 -*-
#
# Copyright 2013 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Configuration import Configuration
from HaikuPorter.Options import getOption
from HaikuPorter.PackageInfo import PackageInfo
from HaikuPorter.RecipeTypes import Architectures, MachineArchitecture
from HaikuPorter.RequiresUpdater import RequiresUpdater
from HaikuPorter.Utils import (check_output, printError, sysExit)

import os
import platform
import shutil
import time
from subprocess import check_call, CalledProcessError


buildPlatform = None


# -- BuildPlatform class ------------------------------------------------------

class BuildPlatform(object):
	def __init__(self):
		pass

	def init(self, treePath, outputDirectory, architecture, machineTriple):
		self.architecture = architecture
		self.machineTriple = machineTriple
		self.treePath = treePath
		self.outputDirectory = outputDirectory

		self.targetArchitecture = Configuration.getTargetArchitecture()
		if not self.targetArchitecture:
			self.targetArchitecture = self.architecture

		self.crossSysrootDir = '/boot/cross-sysroot/' + self.targetArchitecture

	def getName(self):
		return platform.system()

	def getMachineTriple(self):
		return self.machineTriple

	def getArchitecture(self):
		return self.architecture

	def getTargetArchitecture(self):
		return self.targetArchitecture

	def getLicensesDirectory(self):
		directory = Configuration.getLicensesDirectory()
		if not directory:
			directory = (self.findDirectory('B_SYSTEM_DIRECTORY')
				+ '/data/licenses')
		return directory

	def getSystemMimeDbDirectory(self):
		directory = Configuration.getSystemMimeDbDirectory()
		if not directory:
			directory = (self.findDirectory('B_SYSTEM_DIRECTORY')
				+ '/data/mime_db')
		return directory

	def getCrossSysrootDirectory(self, workDir):
		if not workDir:
			return self.crossSysrootDir
		return workDir + self.crossSysrootDir


# -- BuildPlatformHaiku class -------------------------------------------------

class BuildPlatformHaiku(BuildPlatform):
	def __init__(self):
		super(BuildPlatformHaiku, self).__init__()

	def init(self, treePath, outputDirectory, shallowInitIsEnough = False):
		# get system haiku package version and architecture
		systemPackageName = None
		for file in os.listdir('/system/packages'):
			if (file == 'haiku.hpkg'
				or (file.startswith('haiku-') and file.endswith('.hpkg'))):
				systemPackageName = file
				break
		if systemPackageName == None:
			sysExit('Failed to find Haiku system package')

		haikuPackageInfo = PackageInfo('/system/packages/' + systemPackageName)
		self.haikuVersion = haikuPackageInfo.getVersion()
		machine = MachineArchitecture.getTripleFor(
			haikuPackageInfo.getArchitecture())
		if not machine:
			sysExit('Unsupported Haiku build platform architecture %s'
				% haikuPackageInfo.getArchitecture())

		super(BuildPlatformHaiku, self).init(treePath, outputDirectory,
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
			considerBuildhostPackages, fallbackRepositories = []):
		# Always add the system packages.
		repositories = list(repositories)
		repositories.append(
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))
		repositories += fallbackRepositories

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

	def activateBuildPackage(self, workDir, packagePath, revisionedName):
		# activate the build package
		packagesDir = buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY')
		activeBuildPackage = packagesDir + '/' + os.path.basename(packagePath)
		self.deactivateBuildPackage(workDir, activeBuildPackage, 
									revisionedName)

		if not buildPlatform.usesChroot():
			# may have to cross devices, so better use a symlink
			os.symlink(packagePath, activeBuildPackage)
		else:
			# symlinking a package won't work in chroot, but in this
			# case we are sure that the move won't cross devices
			os.rename(packagePath, activeBuildPackage)
		self._waitForPackageSelfLink(revisionedName, True)
		return activeBuildPackage

	def deactivateBuildPackage(self, workDir, activeBuildPackage,
							   revisionedName):
		if os.path.exists(activeBuildPackage):
			os.remove(activeBuildPackage)
		self._waitForPackageSelfLink(revisionedName, False)

	def getCrossToolsBasePrefix(self, workDir):
		return ''

	def getCrossToolsBinPaths(self, workDir):
		return [ '/boot/system/develop/tools/bin' ]

	def getInstallDestDir(self, workDir):
		return None

	def setupNonChrootBuildEnvironment(self, workDir, secondaryArchitecture,
			requiredPackages):
		sysExit('setupNonChrootBuildEnvironment() not supported on Haiku')

	def cleanNonChrootBuildEnvironment(self, workDir, secondaryArchitecture,
			buildOK):
		sysExit('cleanNonChrootBuildEnvironment() not supported on Haiku')

	def _waitForPackageSelfLink(self, revisionedName, activated):
		while True:
			try:
				linkTarget = os.readlink('/packages/%s/.self'
										 % revisionedName)
				packagingFolder = revisionedName.split('-')[0]
				linkTargetIsPackagingFolder \
					= os.path.basename(linkTarget) == packagingFolder
				if linkTargetIsPackagingFolder == activated:
					return
			except OSError:
				if not activated:
					return
			print ('waiting for build package %s to be %s'
				   % (revisionedName,
				      'activated' if activated else 'deactivated'))
			time.sleep(1)

# -- BuildPlatformUnix class --------------------------------------------------

class BuildPlatformUnix(BuildPlatform):
	def __init__(self):
		super(BuildPlatformUnix, self).__init__()

	def init(self, treePath, outputDirectory, shallowInitIsEnough = False):
		# get the machine triple from gcc
		machine = check_output('gcc -dumpmachine', shell=True).strip()

		# When building in a linux32 environment gcc still says "x86_64", so we
		# replace the architecture part of the machine triple with what uname()
		# says.
		machineArchitecture = os.uname()[4].lower()
		machine = machineArchitecture + '-' + machine[machine.find('-') + 1:]

		# compute/guess architecture from the machine
		architecture = MachineArchitecture.findMatch(machineArchitecture)
		if not architecture:
			architecture = Architectures.ANY

		super(BuildPlatformUnix, self).init(treePath, outputDirectory,
			architecture, machine)

		self.secondaryTargetArchitectures \
			= Configuration.getSecondaryTargetArchitectures()
			
		if Configuration.getLicensesDirectory() == None:
			sysExit('LICENSES_DIRECTORY must be set in configuration on this '
				'build platform!')
			
		if not shallowInitIsEnough:
			if Configuration.getPackageCommand() == 'package':
				sysExit('--command-package must be specified on this build '
					'platform!')
			if Configuration.getMimesetCommand() == 'mimeset':
				sysExit('--command-mimeset must be specified on this build '
					'platform!')
			if not Configuration.getSystemMimeDbDirectory():
				sysExit('--system-mimedb must be specified on this build '
					'platform!')
	
			if not Configuration.getCrossToolsDirectory():
				sysExit('--cross-tools must be specified on this build '
					'platform!')
			self.originalCrossToolsDir = Configuration.getCrossToolsDirectory()

			self.secondaryTargetMachineTriples = {}
			if self.secondaryTargetArchitectures:
				if not Configuration.getSecondaryCrossToolsDirectory(
						self.secondaryTargetArchitectures[0]):
					sysExit('The cross-tools directories for all secondary '
						'architectures must be specified on this build '
						'platform!')
	
				for secondaryArchitecture in self.secondaryTargetArchitectures:
					self.secondaryTargetMachineTriples[secondaryArchitecture] \
						= MachineArchitecture.getTripleFor(
							secondaryArchitecture)
	
				if not Configuration.getSecondaryCrossDevelPackage(
						self.secondaryTargetArchitectures[0]):
					sysExit('The Haiku cross devel package for all secondary '
						'architectures must be specified on this build ' 
						'platform!')

		self.findDirectoryMap = {
			'B_PACKAGE_LINKS_DIRECTORY': '/packages',
			'B_SYSTEM_DIRECTORY': '/boot/system',
			'B_SYSTEM_PACKAGES_DIRECTORY': '/boot/system/packages',
			}

		self.crossDevelPackage = Configuration.getCrossDevelPackage()
		targetArchitecture = Configuration.getTargetArchitecture()
		self.targetMachineTriple \
			= MachineArchitecture.getTripleFor(targetArchitecture)
		targetMachineAsName = self.targetMachineTriple.replace('-', '_')

		self.implicitBuildHostProvides = set([
			'haiku',
			'haiku_devel',
			'binutils_cross_' + targetArchitecture,
			'gcc_cross_' + targetArchitecture,
			'coreutils',
			'cmd:aclocal',
			'cmd:autoconf',
			'cmd:autoheader',
			'cmd:automake',
			'cmd:autoreconf',
			'cmd:bash',
			'cmd:cmake',
			'cmd:find',
			'cmd:flex',
			'cmd:gcc',
			'cmd:grep',
			'cmd:gunzip',
			'cmd:ld',
			'cmd:libtool',
			'cmd:libtoolize',
			'cmd:login',
			'cmd:m4',
			'cmd:make',
			'cmd:makeinfo',
			'cmd:nm',
			'cmd:objcopy',
			'cmd:passwd',
			'cmd:perl',
			'cmd:ranlib',
			'cmd:readelf',
			'cmd:sed',
			'cmd:strip',
			'cmd:tar',
			'cmd:zcat',
			'cmd:' + targetMachineAsName + '_objcopy',
			'cmd:' + targetMachineAsName + '_readelf',
			'cmd:' + targetMachineAsName + '_strip',
			])

		# TODO: We might instead want to support passing the package infos for
		# the system packages to haikuporter, so we could get the actual
		# provides.
		self.implicitBuildTargetProvides = set([
			'haiku',
			'haiku_devel',
			'coreutils',
			'diffutils',
			'cmd:awk',
			'cmd:cat',
			'cmd:cmp',
			'cmd:gunzip',
			'cmd:less',
			'cmd:login',
			'cmd:passwd',
			'cmd:sh',
			'cmd:zcat'
		])

		for secondaryArchitecture in self.secondaryTargetArchitectures:
			self.implicitBuildTargetProvides |= set([
				'haiku_' + secondaryArchitecture,
				'haiku_' + secondaryArchitecture + '_devel',
				])
			self.implicitBuildHostProvides |= set([
				'haiku_' + secondaryArchitecture,
				'haiku_' + secondaryArchitecture + '_devel',
				'binutils_cross_' + secondaryArchitecture,
				'gcc_cross_' + secondaryArchitecture,
				])

	def isHaiku(self):
		return False

	def getHaikuVersion(self):
		targetHaikuPackage = Configuration.getCrossDevelPackage()
		targetHaikuPackageInfo = PackageInfo(targetHaikuPackage)
		return targetHaikuPackageInfo.getVersion()

	def usesChroot(self):
		return False

	def findDirectory(self, which):
		if not which in self.findDirectoryMap:
			sysExit('Unsupported findDirectory() constant "%s"' % which)
		return self.findDirectoryMap[which]

	def resolveDependencies(self, packageInfoFiles, repositories,
			considerBuildhostPackages, fallbackRepositories = []):
		# Use the RequiresUpdater to resolve the dependencies.
		requiresUpdater = RequiresUpdater([], packageInfoFiles)
		repositories += fallbackRepositories
		for repository in repositories:
			for package in os.listdir(repository):
				if not (package.endswith('.hpkg')
						or package.endswith('.PackageInfo')):
					continue
				# Only cross packages are build-host packages, everything
				# else are target packages
				isCrossPackage = '_cross_' in package
				if considerBuildhostPackages == isCrossPackage:
					requiresUpdater.addPackageFile(repository + '/' + package)

		for packageInfoFile in packageInfoFiles:
			requiresUpdater.addPackageFile(packageInfoFile)

		pendingPackages = list(packageInfoFiles)
		result = set(pendingPackages)

		while pendingPackages:
			package = pendingPackages.pop()
			packageInfo = PackageInfo(package)
			for requires in packageInfo.getRequires():
				if considerBuildhostPackages:
					if requires.getName() in self.implicitBuildHostProvides:
						continue
				else:
					if requires.getName() in self.implicitBuildTargetProvides:
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

	def activateBuildPackage(self, workDir, packagePath, revisionedName):
		return self._activatePackage(packagePath,
			self._getPackageInstallRoot(workDir, packagePath), None, True)

	def deactivateBuildPackage(self, workDir, activeBuildPackage,
							   revisionedName):
		if os.path.exists(activeBuildPackage):
			shutil.rmtree(activeBuildPackage)

	def getCrossToolsBasePrefix(self, workDir):
		return self.outputDirectory + '/cross_tools'

	def getCrossToolsBinPaths(self, workDir):
		return [
			self._getCrossToolsPath(workDir) + '/bin',
			self.getCrossToolsBasePrefix(workDir) + '/boot/system/bin'
			]

	def getInstallDestDir(self, workDir):
		return self.getCrossSysrootDirectory(workDir)

	def setupNonChrootBuildEnvironment(self, workDir, secondaryArchitecture,
			requiredPackages):
		# init the build platform tree
		crossToolsInstallPrefix = self.getCrossToolsBasePrefix(workDir)
		if os.path.exists(crossToolsInstallPrefix):
			shutil.rmtree(crossToolsInstallPrefix)
		os.makedirs(crossToolsInstallPrefix + '/boot/system')

		# init the sysroot dir
		sysrootDir = self.getCrossSysrootDirectory(workDir)
		if os.path.exists(sysrootDir):
			shutil.rmtree(sysrootDir)
		os.makedirs(sysrootDir)

		os.mkdir(sysrootDir + '/packages')
		os.mkdir(sysrootDir + '/boot')
		os.mkdir(sysrootDir + '/boot/system')

		self._activateCrossTools(workDir, sysrootDir, secondaryArchitecture)

		# extract the haiku_cross_devel_sysroot package
		self._activatePackage(self._getCrossDevelPackage(secondaryArchitecture),
			sysrootDir, '/boot/system')

		# extract the required packages
		for package in requiredPackages:
			self._activatePackage(package,
				self._getPackageInstallRoot(workDir, package), '/boot/system')

	def cleanNonChrootBuildEnvironment(self, workDir, secondaryArchitecture,
			buildOK):
		# remove the symlinks we created in the cross tools tree
		sysrootDir = self.getCrossSysrootDirectory(workDir)
		targetArchitecture = secondaryArchitecture \
			if secondaryArchitecture else self.targetArchitecture
		targetMachineTriple \
			= self._getTargetMachineTriple(secondaryArchitecture)
		toolsMachineTriple = self._getTargetMachineTriple(
			secondaryArchitecture)

		if targetArchitecture == 'x86_gcc2':
			# gcc 2: uses 'sys-include' and 'lib' in the target machine dir
			toolsMachineDir = (
				self._getOriginalCrossToolsDir(secondaryArchitecture) + '/'
				+ toolsMachineTriple)

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
		else:
			# gcc 4: has a separate sysroot dir -- remove it completely
			toolsSysrootDir = (
				self._getOriginalCrossToolsDir(secondaryArchitecture)
				+ '/sysroot')
			if os.path.exists(toolsSysrootDir):
				shutil.rmtree(toolsSysrootDir)

		# If the the build went fine, clean up.
		if buildOK:
			crossToolsDir = self._getCrossToolsPath(workDir)
			if os.path.exists(crossToolsDir):
				shutil.rmtree(crossToolsDir)
			if os.path.exists(sysrootDir):
				shutil.rmtree(sysrootDir)

	def _activateCrossTools(self, workDir, sysrootDir, secondaryArchitecture):
		crossToolsDir = self._getCrossToolsPath(workDir)
		os.mkdir(crossToolsDir)

		targetArchitecture = secondaryArchitecture \
			if secondaryArchitecture else self.targetArchitecture
		targetMachineTriple \
			= self._getTargetMachineTriple(secondaryArchitecture)
		toolsMachineTriple = self._getTargetMachineTriple(
			secondaryArchitecture)

		# prepare the system include and library directories
		includeDir = crossToolsDir + '/include'
		os.symlink(sysrootDir + '/boot/system/develop/headers', includeDir)

		libDir = crossToolsDir + '/lib'
		os.symlink(sysrootDir + '/boot/system/develop/lib', libDir)

		# Prepare the bin dir -- it will be added to PATH and must contain the
		# tools with the expected machine triple prefix.
		toolsBinDir = (self._getOriginalCrossToolsDir(secondaryArchitecture)
			+ '/bin')
		binDir = crossToolsDir + '/bin'
		os.symlink(toolsBinDir, binDir)

		# Symlink the include and lib dirs back to the cross-tools tree such
		# they match the paths that are built into the tools.
		if targetArchitecture == 'x86_gcc2':
			# gcc 2: uses 'sys-include' and 'lib' in the target machine dir
			toolsMachineDir = (
				self._getOriginalCrossToolsDir(secondaryArchitecture) + '/'
				+ toolsMachineTriple)
			toolsIncludeDir = toolsMachineDir + '/sys-include'
			toolsLibDir = toolsMachineDir + '/lib'
			# The cross-compiler doesn't have the subdirectory in the search
			# path, so refer to that directly.
			if secondaryArchitecture:
				libDir += '/' + secondaryArchitecture
		else:
			# gcc 4: has a separate sysroot dir
			toolsDevelopDir = (
				self._getOriginalCrossToolsDir(secondaryArchitecture)
				+ '/sysroot/boot/system/develop')
			if os.path.exists(toolsDevelopDir):
				shutil.rmtree(toolsDevelopDir)
			os.makedirs(toolsDevelopDir)
			toolsIncludeDir = toolsDevelopDir + '/headers'
			toolsLibDir = toolsDevelopDir + '/lib'

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

	def _getTargetMachineTriple(self, secondaryArchitecture):
		return (self.secondaryTargetMachineTriples[secondaryArchitecture]
			if secondaryArchitecture
			else self.targetMachineTriple)

	def _getOriginalCrossToolsDir(self, secondaryArchitecture):
		if not secondaryArchitecture:
			return self.originalCrossToolsDir
		return Configuration.getSecondaryCrossToolsDirectory(
			secondaryArchitecture)

	def _getCrossDevelPackage(self, secondaryArchitecture):
		if not secondaryArchitecture:
			return self.crossDevelPackage
		return Configuration.getSecondaryCrossDevelPackage(
			secondaryArchitecture)

	def _getCrossToolsPath(self, workDir):
		return self.getCrossToolsBasePrefix(workDir) + '/boot/cross-tools'

	def _getPackageInstallRoot(self, workDir, package):
		package = os.path.basename(package)
		if '_cross_' in package:
			return self.getCrossToolsBasePrefix(workDir)
		return self.getCrossSysrootDirectory(workDir)

	def _activatePackage(self, package, installRoot, installationLocation,
			isBuildPackage = False):
		# get the package info
		packageInfo = PackageInfo(package)

		# extract the package, unless it is a build package
		if not isBuildPackage:
			installPath = installRoot + '/' + installationLocation
			args = [ Configuration.getPackageCommand(), 'extract', '-C',
				installPath, package ]
			check_call(args)
		else:
			installPath = packageInfo.getInstallPath()
			if not installPath:
				sysExit('Build package "%s" doesn\'t have an install path'
					% package)

		# create the package links directory for the package and the .self
		# symlink
		packageLinksDir = (installRoot + '/packages/' + packageInfo.getName()
			+ '-' + packageInfo.getVersion())
		if os.path.exists(packageLinksDir):
			shutil.rmtree(packageLinksDir)
		os.makedirs(packageLinksDir)
		os.symlink(installPath, packageLinksDir + '/.self')

		return packageLinksDir


# -----------------------------------------------------------------------------

# init buildPlatform
if platform.system() == 'Haiku':
	buildPlatform = BuildPlatformHaiku()
else:
	buildPlatform = BuildPlatformUnix()
