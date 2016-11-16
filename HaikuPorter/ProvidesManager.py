# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Copyright 2014 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .Options import getOption
from .PackageInfo import PackageInfo, Resolvable
from .Utils import versionCompare

# -- ProvidesInfo class -------------------------------------------------------

class ProvidesInfo(Resolvable):
	def __init__(self, packageInfo, providesString):
		super(ProvidesInfo, self).__init__(providesString)
		self.packageInfo = packageInfo

	@property
	def packageID(self):
		return self.packageInfo.versionedName

	@property
	def path(self):
		return self.packageInfo.path

# -- ProvidesManager class ----------------------------------------------------

class ProvidesManager(object):
	def __init__(self):
		self._providesMap = {}

	def addProvidesFromPackage(self, package):
		for providesString in package.recipeKeys['PROVIDES']:
			self._addPackageProvidesInfo(package.revisionedName, providesString)

	def addProvidesFromPackageInfo(self, packageInfo):
		for provides in packageInfo.provides:
			self._addPackageProvidesInfo(packageInfo, str(provides))

	def getMatchingProvides(self, resolvableExpression, anyHpkg=False):
		name = resolvableExpression.name
		operator = resolvableExpression.operator
		version = resolvableExpression.version

		if not name in self._providesMap:
			return None

		updateDependencies = getOption('updateDependencies')

		providesList = self._providesMap[name]

		found = None
		foundIsHpkg = False
		for provides in providesList:
			provideIsHpkg = (provides.packageInfo.path.endswith('.hpkg')
				if isinstance(provides.packageInfo, PackageInfo) else False)
			if not operator:
				if not updateDependencies:
					return provides
				if (found is None or
					(anyHpkg and provideIsHpkg) or
					(provideIsHpkg and not foundIsHpkg and
						(found.version is None
							or versionCompare(provides.version, found.version) >= 0))):
					found = provides
					foundIsHpkg = provideIsHpkg
				continue
			if not provides.version:
				continue
			matches = {
				'<':	lambda compareResult: compareResult < 0,
				'<=':	lambda compareResult: compareResult <= 0,
				'==':	lambda compareResult: compareResult == 0,
				'!=':	lambda compareResult: compareResult != 0,
				'>=':	lambda compareResult: compareResult >= 0,
				'>':	lambda compareResult: compareResult > 0,
			}[operator](versionCompare(provides.version, version))
			if not matches:
				continue
			if (provides.compatibleVersion
				and versionCompare(provides.compatibleVersion, version) > 0):
				continue
			if not updateDependencies:
				return provides
			if (found is None or
				(anyHpkg and provideIsHpkg) or
				(provideIsHpkg and not foundIsHpkg and
					(found.version is None
						or versionCompare(provides.version, found.version) >= 0))):
				found = provides
				foundIsHpkg = provideIsHpkg
		return found

	def _addPackageProvidesInfo(self, packageInfo, providesString):
		provides = ProvidesInfo(packageInfo, providesString.strip())
		if provides.name in self._providesMap:
			self._providesMap[provides.name].append(provides)
		else:
			self._providesMap[provides.name] = [ provides ]
