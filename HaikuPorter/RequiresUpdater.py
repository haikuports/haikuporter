# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Options import getOption
from HaikuPorter.PackageInfo import (PackageInfo, Resolvable,
									 ResolvableExpression)
from HaikuPorter.Utils import (check_output, versionCompare, sysExit)

import os
import re
from subprocess import CalledProcessError

# -- ProvidesInfo class -------------------------------------------------------

class ProvidesInfo(Resolvable):
	def __init__(self, package, providesString):
		super(ProvidesInfo, self).__init__(providesString)
		self.package = package

	def getPackage(self):
		return self.package

# -- RequiresUpdater class ----------------------------------------------------

class RequiresUpdater(object):
	def __init__(self, portPackages, requiredPackages):
		self.providesMap = {}

		# get the provides for the port packages
		for package in portPackages:
			for providesString in package.getRecipeKeys()['PROVIDES']:
				self._addPackageProvidesInfo(package.revisionedName,
					providesString)

		# get the provides for the required packages
		for package in requiredPackages:
			if package.endswith('.hpkg'):
				self.addPackageFile(package)

	def addPackageFile(self, package):
		try:
			packageInfo = PackageInfo(package)
		except CalledProcessError:
			sysExit('failed to get provides for package "%s"' % package)

		for provides in packageInfo.getProvides():
			self._addPackageProvidesInfo(package, str(provides))

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
		name = resolvableExpression.getName()
		operator = resolvableExpression.getOperator()
		version = resolvableExpression.getVersion()

		if not name in self.providesMap:
			return None

		providesList = self.providesMap[name]
		matchingProvides = None
		for provides in providesList:
			if not operator:
				return provides
			if not provides.version:
				continue
			matches = {
				'<':	lambda cmp: cmp < 0,
				'<=':	lambda cmp: cmp <= 0,
				'==':	lambda cmp: cmp == 0,
				'!=':	lambda cmp: cmp != 0,
				'>=':	lambda cmp: cmp >= 0,
				'>':	lambda cmp: cmp > 0,
			}[operator](versionCompare(provides.version, version))
			if not matches:
				continue
			if (provides.compatibleVersion
				and versionCompare(provides.compatibleVersion, version)
					> 0):
				continue
			return provides
		return None

	def _updateRequires(self, requires):
		# split the requires string
		requires = requires.strip()
		partialRequires = requires
		isBase = requires.endswith('base')
		if isBase:
			partialRequires = requires[:-4].rstrip()

		resolvableExpression = ResolvableExpression(partialRequires)
		name = resolvableExpression.getName()
		operator = resolvableExpression.getOperator()

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

	def _addPackageProvidesInfo(self, package, providesString):
		provides = ProvidesInfo(package, providesString.strip())
		if provides.name in self.providesMap:
			self.providesMap[provides.name].append(provides)
		else:
			self.providesMap[provides.name] = [ provides ]
