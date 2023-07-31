# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Copyright 2014 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from . import BuildPlatform

from .Configuration import Configuration
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
		self._providesSourceMap = {}
		self.architectures = [BuildPlatform.buildPlatform.targetArchitecture,
			'any', 'source']

	def addProvidesFromPackage(self, package):
		for providesString in package.recipeKeys['PROVIDES']:
			self._addPackageProvidesInfo(package.revisionedName, providesString)

	def addProvidesFromPackageInfo(self, packageInfo):
		if (packageInfo.architecture not in self.architectures
			and not (Configuration.isCrossBuildRepository()
				and '_cross_' in packageInfo.path)):
			return

		for provides in packageInfo.provides:
			self._addPackageProvidesInfo(packageInfo, str(provides))

	def getMatchingProvides(self, resolvableExpression, anyHpkg=False,
		ignoreBase=False):
		name = resolvableExpression.name
		operator = resolvableExpression.operator
		version = resolvableExpression.version
		base = resolvableExpression.base

		if name not in self._providesMap:
			return None

		updateDependencies = getOption('updateDependencies')
		missingDependencies = getOption('missingDependencies')

		providesList = self._providesMap[name]

		found = None
		foundIsHpkg = False
		for provides in providesList:
			provideIsHpkg = (provides.packageInfo.path.endswith('.hpkg')
				if isinstance(provides.packageInfo, PackageInfo) else False)
			if not ignoreBase and base and provideIsHpkg:
				continue
			if not operator:
				if not updateDependencies and not missingDependencies:
					return provides
				if (found is None or
					(anyHpkg and provideIsHpkg) or
					(provideIsHpkg and not foundIsHpkg and
						(missingDependencies or found.version is None
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
			if not updateDependencies and not missingDependencies:
				return provides
			if (found is None or
				(anyHpkg and provideIsHpkg) or
				(provideIsHpkg and not foundIsHpkg and
					(missingDependencies or found.version is None
						or versionCompare(provides.version, found.version) >= 0))):
				found = provides
				foundIsHpkg = provideIsHpkg
		return found

	@staticmethod
	def _providesSource(packageInfo):
		return packageInfo.path if isinstance(packageInfo, PackageInfo) \
			else packageInfo


	def _addPackageProvidesInfo(self, packageInfo, providesString):
		provides = ProvidesInfo(packageInfo, providesString.strip())

		source = self._providesSource(packageInfo)
		if source in self._providesSourceMap:
			self._providesSourceMap[source].append(provides)
		else:
			self._providesSourceMap[source] = [provides]

		if provides.name in self._providesMap:
			self._providesMap[provides.name].append(provides)
		else:
			self._providesMap[provides.name] = [provides]

	def removeProvidesOfPackageInfo(self, packageInfo):
		source = self._providesSource(packageInfo)
		providesList = self._providesSourceMap.pop(source)
		for provides in providesList:
			self._providesMap[provides.name].remove(provides)
