# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .PackageInfo import PackageInfo, Resolvable, ResolvableExpression
from .ProvidesManager import ProvidesManager
from .Utils import versionCompare, sysExit

import os
from subprocess import CalledProcessError

# -- ProvidesInfo class -------------------------------------------------------

class ProvidesInfo(Resolvable):
	def __init__(self, package, providesString):
		super(ProvidesInfo, self).__init__(providesString)
		self.package = package

# -- RequiresUpdater class ----------------------------------------------------

class RequiresUpdater(object):
	def __init__(self, portPackages, requiredPackages):
		self._providesManager = ProvidesManager()

		# get the provides for the port packages
		for package in portPackages:
			self._providesManager.addProvidesFromPackage(package)

		# get the provides for the required packages
		for package in requiredPackages:
			if package.endswith('.hpkg'):
				self.addPackageFile(package)

	def addPackageFile(self, package):
		try:
			packageInfo = PackageInfo(package)
		except CalledProcessError:
			sysExit('failed to get provides for package "%s"' % package)

		self._providesManager.addProvidesFromPackageInfo(packageInfo)

	def addPackages(self, directory):
		for package in os.listdir(directory):
			if package.endswith('.hpkg') or package.endswith('.PackageInfo'):
				self.addPackageFile(directory + '/' + package)

	def updateRequiresList(self, requiresList):
		result = []
		for requires in requiresList:
			requires = requires.strip()
			if not requires.startswith('#'):
				result.append(self._updateRequires(requires))
		return result

	def getMatchingProvides(self, resolvableExpression):
		return self._providesManager.getMatchingProvides(resolvableExpression)

	def _updateRequires(self, requires):
		# split the requires string
		requires = requires.strip()
		partialRequires = requires
		isBase = requires.endswith('base')
		if isBase:
			partialRequires = requires[:-4].rstrip()

		resolvableExpression = ResolvableExpression(partialRequires)
		name = resolvableExpression.name
		operator = resolvableExpression.operator

		# check whether there's a matching provides and, if so, replace the
		# given requires
		matchingProvides = self.getMatchingProvides(resolvableExpression)
		if not matchingProvides:
			if self.getMatchingProvides(ResolvableExpression(name)):
				sysExit('found provides for "%s", but none matching the '
					'version requirement' % requires)
			return requires

		if not matchingProvides.version:
			return requires

		# Enforce the minimum found version, if the requires has no version
		# requirement or also a minimum. Otherwise enforce the exact version
		# found.
		resultOperator = '>=' if operator in [None, '> ', '>='] else '=='
		result = '%s %s %s' \
			% (matchingProvides.name, resultOperator, matchingProvides.version)
		if isBase:
			result += ' base'
		return result
