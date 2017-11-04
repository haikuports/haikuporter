# -*- coding: utf-8 -*-
#
# Copyright 2017 Michael Lotz 
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .Configuration import Configuration
from .Options import getOption
from .PackageInfo import PackageInfo
from .Utils import sysExit, touchFile, versionCompare, warn

import glob
import json
import os
import re
import shutil


# -- PackageRepository class --------------------------------------------------

class PackageRepository(object):

	def __init__(self, packagesPath, repository, quiet):
		self.packagesPath = packagesPath
		if not os.path.exists(self.packagesPath):
			os.mkdir(self.packagesPath)

		self.obsoleteDir = os.path.join(self.packagesPath, '.obsolete')
		if not os.path.exists(self.obsoleteDir):
			os.mkdir(self.obsoleteDir)

		self.architectures = [Configuration.getTargetArchitecture(),
			'any', 'source']

		self.repository = repository
		self.quiet = quiet

	def prune(self):
		self.obsoletePackagesWithoutPort()
		self.obsoletePackagesNewerThanActiveVersion()
		self.obsoletePackagesWithNewerVersions()

	def packageList(self, packageSpec=None):
		if packageSpec == None:
			packageSpec = ''
		else:
			packageSpec += '-'

		packageSpec += '*.hpkg'
		return glob.glob(os.path.join(self.packagesPath, packageSpec))

	def packageInfoList(self, packageSpec=None):
		result = []
		for package in self.packageList(packageSpec):
			try:
				packageInfo = PackageInfo(package)
			except Exception as exception:
				warn('failed to get info of {}: {}'.format(package, exception))
				continue

			if not packageInfo.architecture in self.architectures:
				continue

			result.append(packageInfo)

		return result

	def obsoletePackage(self, path, reason=None):
		packageFileName = os.path.basename(path)
		if not self.quiet:
			print('\tobsoleting package {}: {}'.format(packageFileName, reason))

		os.rename(path, os.path.join(self.obsoleteDir, packageFileName))

	def obsoletePackagesForSpec(self, packageSpec, reason=None):
		"""remove all packages for the given packageSpec"""

		for package in packageList(packageSpec):
			self.obsoletePackage(package, reason)

	def obsoletePackagesWithoutPort(self):
		"""remove packages that have no corresponding port"""

		for package in self.packageInfoList():
			portName = self.repository.getPortNameForPackageName(package.name)
			activePort = self.repository.getActivePort(portName)
			if not activePort:
				self.obsoletePackage(package.path, 'no port for it exists')

	def obsoletePackagesNewerThanActiveVersion(self):
		"""remove packages newer than what their active port version produces"""

		for package in self.packageInfoList():
			portName = self.repository.getPortNameForPackageName(package.name)
			activePort = self.repository.getActivePort(portName)
			if not activePort:
				continue

			if versionCompare(package.version, activePort.fullVersion) > 0:
				self.obsoletePackage(package.path,
					'newer than active {}'.format(activePort.fullVersion))

	def obsoletePackagesWithNewerVersions(self):
		"""remove all packages where newer version packages are available"""

		newestPackages = dict()
		reason = 'newer version {} available'
		for package in self.packageInfoList():
			if package.name in newestPackages:
				newest = newestPackages[package.name]
				if versionCompare(newest.version, package.version) > 0:
					self.obsoletePackage(package.path,
						reason.format(newest.version))
					continue

				self.obsoletePackage(newest.path,
					reason.format(package.version))

			newestPackages[package.name] = package
