# -*- coding: utf-8 -*-
#
# Copyright 2013-2014 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .Configuration import Configuration
from .Utils import sysExit

from copy import deepcopy
from subprocess import check_output
import codecs
import json
import os
import pickle
import re


# -- Resolvable class ---------------------------------------------------------

class Resolvable(object):
	# HPKG:		<name> [ <op> <version> [ "(compatible >= " <version> ")" ]]
	# Recipe: 	<name> [ <op> <version> [ "compat >= " <version> ]]
	versionPattern = re.compile(r'([^\s=]+)\s*(=\s*([^\s]+)\s*'
		+ r'((\(compatible|compat)\s*>=\s*([^\s)]+))?)?')

	def __init__(self, string):
		match = Resolvable.versionPattern.match(string)
		self.name = match.group(1)
		self.version = match.group(3)
		self.compatibleVersion = match.group(6)

	def __str__(self):
		result = self.name
		if self.version:
			result += ' = ' + self.version
		if self.compatibleVersion:
			result += ' (compatible >= ' + self.compatibleVersion + ')'
		return result


# -- ResolvableExpression class -----------------------------------------------

class ResolvableExpression(object):
	expressionPattern = re.compile(r'([^\s=!<>]+)\s*([=!<>]+)?\s*([^\s]+)?')

	def __init__(self, string, ignoreBase=False):
		match = ResolvableExpression.expressionPattern.match(string)
		self.name = match.group(1)
		self.operator = match.group(2)
		self.version = match.group(3)
		self.base = not ignoreBase and string.endswith(' base')

	def __str__(self):
		result = self.name
		if self.operator:
			result += ' ' + self.operator + ' ' + self.version
		if self.base:
			result += ' base'
		return result


# -- PackageInfo class --------------------------------------------------------

class PackageInfo(object):
	hpkgCache = None
	hpkgCacheDir = None
	hpkgCachePath = None

	def __init__(self, path):
		self.path = path

		if path.endswith('.hpkg') or path.endswith('.PackageInfo'):
			self._parseFromHpkgOrPackageInfoFile()
		elif path.endswith('.DependencyInfo'):
			self._parseFromDependencyInfoFile()
		else:
			sysExit(u"don't know how to extract package-info from " + path)

	@property
	def versionedName(self):
		return self.name + '-' + self.version

	@classmethod
	def _initializeCache(self):
		self.hpkgCache = {}
		self.hpkgCacheDir = Configuration.getRepositoryPath()
		self.hpkgCachePath = os.path.join(self.hpkgCacheDir, 'hpkgInfoCache')
		if not os.path.exists(self.hpkgCachePath):
			return

		prune = False
		with open(self.hpkgCachePath, 'rb') as cacheFile:
			while True:
				try:
					entry = pickle.load(cacheFile)
					path = entry['path']
					if not os.path.exists(path) \
						or os.path.getmtime(path) > entry['modifiedTime']:
						prune = True
						continue

					self.hpkgCache[path] = entry
				except EOFError:
					break

		if prune:
			with open(self.hpkgCachePath, 'wb') as cacheFile:
				for entry in self.hpkgCache.itervalues():
					pickle.dump(entry, cacheFile, pickle.HIGHEST_PROTOCOL)

	@classmethod
	def _writeToCache(self, packageInfo):
		self.hpkgCache[packageInfo['path']] = deepcopy(packageInfo)
		if not os.path.exists(self.hpkgCacheDir):
			os.makedirs(self.hpkgCacheDir)

		with open(self.hpkgCachePath, 'ab') as cacheFile:
			pickle.dump(packageInfo, cacheFile, pickle.HIGHEST_PROTOCOL)

	def _parseFromHpkgOrPackageInfoFile(self, silent=False):
		if self.path.endswith('.hpkg'):
			if PackageInfo.hpkgCache == None:
				PackageInfo._initializeCache()

			if self.path in PackageInfo.hpkgCache:
				self.__dict__ = deepcopy(PackageInfo.hpkgCache[self.path])
				return

		# get an attribute listing of the package/package info file
		args = [Configuration.getPackageCommand(), 'list', '-i', self.path]
		if silent:
			with open(os.devnull, "w") as devnull:
				output = check_output(args, stderr=devnull)
		else:
			output = check_output(args)

		# get various single-occurrence fields
		self.name = self._extractField(output, 'name')
		self.version = self._extractField(output, 'version')
		self.architecture = self._extractField(output, 'architecture')
		self.installPath = self._extractOptionalField(output, 'install path')

		# get provides and requires (no buildrequires or -prerequires exist)
		self.provides = []
		self.requires = []
		self.buildRequires = []
		self.buildPrerequires = []
		for line in output.splitlines():
			line = line.strip()
			if line.startswith('provides:'):
				self.provides.append(Resolvable(line[9:].lstrip()))
			elif line.startswith('requires:'):
				self.requires.append(ResolvableExpression(line[9:].lstrip(),
					True))

		if self.path.endswith('.hpkg'):
			self.modifiedTime = os.path.getmtime(self.path)
			PackageInfo._writeToCache(self.__dict__)

	def _parseFromDependencyInfoFile(self):
		with codecs.open(self.path, 'r', 'utf-8') as fh:
			dependencyInfo = json.load(fh)

		# get various single-occurrence fields
		self.name = dependencyInfo['name']
		self.version = dependencyInfo['version']
		self.architecture = dependencyInfo['architecture']

		# get provides and requires
		self.provides = [
			Resolvable(p) for p in dependencyInfo['provides']
		]
		self.requires = [
			ResolvableExpression(r) for r in dependencyInfo['requires']
		]
		self.buildRequires = [
			ResolvableExpression(r) for r in dependencyInfo['buildRequires']
		]
		self.buildPrerequires = [
			ResolvableExpression(r) for r in dependencyInfo['buildPrerequires']
		]

	def _extractField(self, output, fieldName):
		result = self._extractOptionalField(output, fieldName)
		if not result:
			sysExit(u'Failed to get %s of package "%s"' % (fieldName, self.path))
		return result

	def _extractOptionalField(self, output, fieldName):
		regExp = re.compile(r'^\s*%s:\s*(\S+)' % fieldName, re.MULTILINE)
		match = regExp.search(output)
		if match:
			return match.group(1)
		return None
