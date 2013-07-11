# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Utils import (check_output, versionCompare, sysExit)

import os
import re
from subprocess import CalledProcessError

# -- ProvidesInfo class -------------------------------------------------------

class ProvidesInfo(object):
	def __init__(self, package, providesString):
		self.package = package

		# split the string
		# <name> [ <op> <version> ] [ "compatible >= " <version> ")" ]
		if providesString.endswith(')'):
			index = providesString.rfind('(')
			versionIndex = providesString.rfind('>=')
			self.compatibleVersion = providesString[versionIndex + 2:-1].strip()
			providesString = providesString[:index].rstrip()
		else:
			self.compatibleVersion = None

		match = re.match('([^\s=]+)\s*=\s*([^\s]+)', providesString)
		if match:
			self.name = match.group(1)
			self.version = match.group(2)
		else:
			self.name = providesString
			self.version = None

# -- RequiresUpdater class ----------------------------------------------------

class RequiresUpdater(object):
	def __init__(self, portPackages, requiredPackages,
			addSystemPackages = True):
		self.providesMap = {}

		# get the provides for the port packages
		for package in portPackages:
			for providesString in package.getRecipeKeys()['PROVIDES']:
				self._addPackageProvidesInfo(package.revisionedName,
					providesString)

		# get the provides for the required packages
		for package in requiredPackages:
			if package.endswith('.hpkg'):
				self._getPackageProvides(package)

		# ... and for the system packages
		if addSystemPackages:
			systemDirectory = '/boot/system/packages'
			for package in os.listdir(systemDirectory):
				if package.endswith('.hpkg'):
					self._getPackageProvides(systemDirectory + '/' + package)

	def updateRequiresList(self, requiresList):
		result = []
		for requires in requiresList:
			requires = requires.strip()
			if not requires.startswith('#'):
				result.append(self._updateRequires(requires))
		return result

	def _updateRequires(self, requires):
		# split the requires string
		requires = requires.strip()
		partialRequires = requires
		isBase = requires.endswith('base')
		if isBase:
			partialRequires = requires[:-4].rstrip()

		match = re.match('([^\s=!<>]+)\s*([=!<>]+)\s*([^\s]+)', partialRequires)
		if match:
			name = match.group(1)
			operator = match.group(2)
			version = match.group(3)
		else:
			name = partialRequires
			operator = None
			version = None

		# check whether there's a matching provides and, if so, replace the
		# given requires
		if not name in self.providesMap:
			return requires

		providesList = self.providesMap[name]
		matchingProvides = None
		for provides in providesList:
			if not operator:
				matchingProvides = provides
				break;
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
			matchingProvides = provides

		if not matchingProvides:
			sysExit('found provides for "%s", but none matching the '
				'version requirement' % requires)

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

	def _getPackageProvides(self, package):
		# list the package and extract the provides from the output
		args = [ '/bin/package', 'list', package ]
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(args, stderr=devnull)
		except CalledProcessError:
			sysExit('failed to get provides for package "%s"' % package)

		for line in output.splitlines():
			index = line.find('provides:')
			if index < 0:
				continue
			self._addPackageProvidesInfo(package, line[index + 9:])

	def _addPackageProvidesInfo(self, package, providesString):
		provides = ProvidesInfo(package, providesString.strip())
		if provides.name in self.providesMap:
			self.providesMap[provides.name].append(provides)
		else:
			self.providesMap[provides.name] = [ provides ]
