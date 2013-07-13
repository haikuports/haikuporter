# -*- coding: utf-8 -*-
#
# Copyright 2013 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.PackageInfo import PackageInfo
from HaikuPorter.Utils import (check_output, sysExit)

import platform


buildPlatform = None


# -- BuildPlatform class ------------------------------------------------------

class BuildPlatform(object):
	def __init__(self, machineTriple):
		self.machineTriple = machineTriple

	def getName(self):
		return platform.system()

	def getMachineTriple(self):
		return self.machineTriple

	def getArchitecture(self):
		index = self.machineTriple.find('-')
		if index >= 0:
			return self.machineTriple[:index]
		return self.machineTriple


# -- BuildPlatformHaiku class -------------------------------------------------

class BuildPlatformHaiku(BuildPlatform):
	def __init__(self):
		# get system haiku package version and architecture
		haikuPackageInfo = PackageInfo('/system/packages/haiku.hpkg')
		self.haikuVersion = haikuPackageInfo.getVersion()
		machine = MachineArchitecture.getTripleFor(
			haikuPackageInfo.getArchitecture())
		if not machine:
			sysExit('Unsupported Haiku build platform architecture %s'
				% haikuPackageInfo.getArchitecture())

		super(BuildPlatformHaiku, self).__init__(machine)

		self.findDirectoryCache = {}

	def init(self):
		pass

	def isHaiku(self):
		return True

	def getHaikuVersion(self):
		return self.haikuVersion

	def findDirectory(self, which):
		"""wraps invocation of 'finddir', uses caching"""
		if not which in self.findDirectoryCache:
			self.findDirectoryCache[which] \
				= check_output(['/bin/finddir', which]).rstrip()  # drop newline
		return self.findDirectoryCache[which]


# -- BuildPlatformUnix class --------------------------------------------------

class BuildPlatformUnix(BuildPlatform):
	def __init__(self):
		# get the machine triple from gcc
		machine = check_output('gcc -dumpmachine', shell=True).strip()

		super(BuildPlatformUnix, self).__init__(machine)

		self.findDirectoryMap = {
			'B_PACKAGE_LINKS_DIRECTORY': '/packages',
			'B_SYSTEM_DIRECTORY': '/boot/system',
			'B_SYSTEM_PACKAGES_DIRECTORY': '/boot/system/packages',
			'B_COMMON_PACKAGES_DIRECTORY': '/boot/common/packages',
			}

	def init(self):
		pass

	def isHaiku(self):
		return False

	def findDirectory(self, which):
		if not which in self.findDirectoryMap:
			sysExit('Unsupported findDirectory() constant "%s"' % which)
		return self.findDirectoryMap[which]


# init buildPlatform
if platform.system() == 'Haiku':
	buildPlatform = BuildPlatformHaiku()
else:
	buildPlatform = BuildPlatformUnix()
