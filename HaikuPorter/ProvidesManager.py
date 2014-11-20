# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Copyright 2014 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .PackageInfo import Resolvable
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

	def addProvidesFromPackageInfo(self, packageInfo):
		for provides in packageInfo.provides:
			self._addPackageProvidesInfo(packageInfo, str(provides))

	def getMatchingProvides(self, resolvableExpression):
		name = resolvableExpression.name
		operator = resolvableExpression.operator
		version = resolvableExpression.version

		if not name in self._providesMap:
			return None

		providesList = self._providesMap[name]
		for provides in providesList:
			if not operator:
				return provides
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
			return provides
		return None

	def _addPackageProvidesInfo(self, packageInfo, providesString):
		provides = ProvidesInfo(packageInfo, providesString.strip())
		if provides.name in self._providesMap:
			self._providesMap[provides.name].append(provides)
		else:
			self._providesMap[provides.name] = [ provides ]
