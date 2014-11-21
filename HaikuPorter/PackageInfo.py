# -*- coding: utf-8 -*-
#
# Copyright 2013-2014 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .Configuration import Configuration
from .Utils import (check_output, sysExit)

from copy import deepcopy
import json
import os
import re


# -- Resolvable class ---------------------------------------------------------

class Resolvable(object):
	def __init__(self, string):
		# split off the compat-version part
		# <name> [ <op> <version> ] [ "compatible >= " <version> ")" ]
		self.compatibleVersion = None
		if string.endswith(')'):
			index = string.rfind('(')
			versionIndex = string.rfind('>=')
			if versionIndex > 0:
				self.compatibleVersion = string[versionIndex + 2:-1].strip()
				string = string[:index].rstrip()

		match = re.match('([^\s=]+)\s*=\s*([^\s]+)', string)
		if match:
			self.name = match.group(1)
			self.version = match.group(2)
		else:
			self.name = string
			self.version = None

	def __str__(self):
		result = self.name
		if self.version:
			result += ' = ' + self.version
		if self.compatibleVersion:
			result += ' (compatible >= ' + self.compatibleVersion + ')'
		return result


# -- ResolvableExpression class -----------------------------------------------

class ResolvableExpression(object):
	def __init__(self, string):
		match = re.match('([^\s=!<>]+)\s*([=!<>]+)\s*([^\s]+)', string)
		if match:
			self.name = match.group(1)
			self.operator = match.group(2)
			self.version = match.group(3)
		else:
			self.name = string
			self.operator = None
			self.version = None

	def __str__(self):
		if self.operator:
			return self.name + ' ' + self.operator + ' ' + self.version
		return self.name


# -- PackageInfo class --------------------------------------------------------

class PackageInfo(object):

	hpkgCache = {}

	def __init__(self, path):
		self.path = path

		if path.endswith('.hpkg') or path.endswith('.PackageInfo'):
			self._parseFromHpkgOrPackageInfoFile()
		elif path.endswith('.DependencyInfo'):
			self._parseFromDependencyInfoFile()
		else:
			sysExit("don't know how to extract package-info from " + path)

	@property
	def versionedName(self):
		return self.name + '-' + self.version

	def _parseFromHpkgOrPackageInfoFile(self, silent = False):
		if self.path.endswith('.hpkg'):
			if self.path in PackageInfo.hpkgCache:
				self.__dict__ = deepcopy(PackageInfo.hpkgCache[self.path])
				return

		# get an attribute listing of the package/package info file
		args = [ Configuration.getPackageCommand(), 'list', '-i', self.path ]
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
				self.requires.append(ResolvableExpression(line[9:].lstrip()))

		if self.path.endswith('.hpkg'):
			PackageInfo.hpkgCache[self.path] = deepcopy(self.__dict__)

	def _parseFromDependencyInfoFile(self):
		with open(self.path, 'r') as fh:
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
		pass

	def _extractField(self, output, fieldName):
		result = self._extractOptionalField(output, fieldName)
		if not result:
			sysExit('Failed to get %s of package "%s"' % (fieldName, self.path))
		return result

	def _extractOptionalField(self, output, fieldName):
		regExp = re.compile('^\s*%s:\s*(\S+)' % fieldName, re.MULTILINE)
		match = regExp.search(output)
		if match:
			return match.group(1)
		return None
