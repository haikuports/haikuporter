# -*- coding: utf-8 -*-
#
# Copyright 2013 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Configuration import Configuration
from HaikuPorter.Utils import (check_output, sysExit)

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
			result += ' (' + self.compatibleVersion + ')'
		return result

	def getName(self):
		return self.name

	def getVersion(self):
		return self.version

	def getCompatibleVersion(self):
		return self.compatibleVersion


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

	def getName(self):
		return self.name

	def getOperator(self):
		return self.operator

	def getVersion(self):
		return self.version


# -- PackageInfo class --------------------------------------------------------

class PackageInfo(object):
	def __init__(self, path, silent = False):
		self.path = path

		# get an attribute listing of the package/package info file
		args = [ Configuration.getPackageCommand(), 'list', '-i', path ]
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

		# get provides and requires
		self.provides = []
		self.requires = []
		for line in output.splitlines():
			line = line.strip()
			if line.startswith('provides:'):
				self.provides.append(Resolvable(line[9:].lstrip()))
			elif line.startswith('requires:'):
				self.requires.append(ResolvableExpression(line[9:].lstrip()))

	def getName(self):
		return self.name

	def getVersion(self):
		return self.version

	def getArchitecture(self):
		return self.architecture

	def getInstallPath(self):
		return self.installPath

	def getProvides(self):
		return self.provides

	def getRequires(self):
		return self.requires

	def _extractField(self, output, fieldName):
		result = self._extractOptionalField(output, fieldName)
		match = re.search(r"%s:\s*(\S+)" % fieldName, output)
		if not result:
			sysExit('Failed to get %s of package "%s"' % (fieldName, self.path))
		return result

	def _extractOptionalField(self, output, fieldName):
		match = re.search(r"%s:\s*(\S+)" % fieldName, output)
		if match:
			return match.group(1)
		return None
