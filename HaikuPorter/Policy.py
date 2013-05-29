# -*- coding: utf-8 -*-
# copyright 2013 Ingo Weinhold

# -- Modules ------------------------------------------------------------------

from HaikuPorter.ConfigParser import ConfigParser
from HaikuPorter.Package import PackageType
from HaikuPorter.Utils import (check_output, isCommandAvailable, sysExit)

import os
import re

allowedTopLevelEntries = [
	'.PackageInfo',
	'add-ons',
	'apps',
	'bin',
	'boot',
	'data',
	'develop',
	'documentation',
	'lib',
	'preferences',
	'settings'
]

# -- Policy checker class -----------------------------------------------------

class Policy(object):
	def __init__(self, strict):
		self.strict = strict

	def setPort(self, port):
		self.port = port

	def setRequiredPackages(self, requiredPackages):
		# Create a map with the packages' provides. We need that later when
		# checking the created package.
		self.requiredPackagesProvides = {}
		for package in requiredPackages:
			provides = self._getPackageProvides(package)
			self.requiredPackagesProvides[os.path.basename(package)] = provides

	def checkPackage(self, package, packageFile):
		# TODO: Also check source packages once their directory layout has been
		# fixed.
		if package.type == PackageType.SOURCE:
			return

		self.package = package
		self.packageFile = packageFile

		self.provides = self._parseResolvableExpressionListForKey('PROVIDES')
		self.requires = self._parseResolvableExpressionListForKey('REQUIRES')

		self._checkTopLevelEntries()
		self._checkProvides()
		self._checkLibraryDependencies()
		self._checkGlobalSettingsFiles()
		self._checkUserSettingsFiles()

	def _checkTopLevelEntries(self):
		for entry in os.listdir('.'):
			if entry not in allowedTopLevelEntries:
				self._severeViolation('Invalid top-level package entry "%s"'
					% entry)

	def _parseResolvableExpressionListForKey(self, keyName):
		return self._parseResolvableExpressionList(
			self.package.getRecipeKeys()[keyName])

	def _parseResolvableExpressionList(self, list):
		names = set()
		for item in list:
			match = re.match('[^-/=!<>\s]+', item)
			if match:
				names.add(match.group(0))
		return names

	def _checkProvides(self):
		# everything in bin/ must be declared as cmd:*
		if os.path.exists('bin'):
			for entry in os.listdir('bin'):
				name = 'cmd:' + entry
				if not self._hasProvidesEntry(name):
					self._violation('no matching provides "%s" for "%s"'
						% (name, 'bin/' + entry))

		# library entries in lib/ must be declared as lib:*
		if os.path.exists('lib'):
			for entry in os.listdir('lib'):
				suffixIndex = entry.find('.so')
				if suffixIndex < 0:
					continue

				name = 'lib:' + entry[:suffixIndex]
				if not self._hasProvidesEntry(name):
					self._violation('no matching provides "%s" for "%s"'
						% (name, 'lib/' + entry))

	def _hasProvidesEntry(self, name):
		# make name a valid provides name by replacing '-' with '_'
		name = name.replace('-', '_')
		return name in self.provides

	def _hasRequiresEntry(self, name):
		# make name a valid provides name by replacing '-' with '_'
		name = name.replace('-', '_')
		return name in self.requires

	def _checkLibraryDependencies(self):
		# If there's no readelf (i.e. no binutils), there probably aren't any
		# executables/libraries.
		if not isCommandAvailable('readelf'):
			return

		# check all files in bin/ and dir/
		for dir in ['bin', 'lib']:
			if not os.path.exists(dir):
				continue

			for entry in os.listdir(dir):
				path = dir + '/' + entry
				if os.path.isfile(path):
					self._checkLibraryDependenciesOfFile(path)

	def _checkLibraryDependenciesOfFile(self, path):
		# skip static libraries outright
		if path.endswith('.a'):
			return

		# try to read the dynamic section of the file
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(['readelf', '--dynamic', path],
					stderr=devnull)
		except:
			return

		# extract the library names from the "(NEEDED)" lines of the output
		for line in output.split('\n'):
			if line.find('(NEEDED)') >= 0:
				match = re.match('[^[]*\[(.*)].*', line)
				if match:
					library = match.group(1)
					if self._isMissingLibraryDependency(library):
						self._violation('"%s" needs library "%s", but the '
							'package doesn\'t seem to declare that as a '
							'requirement' % (path, library))

	def _isMissingLibraryDependency(self, library):
		# the library might be provided by the package
		if os.path.exists('lib/' + library):
			return False

		# not provided by the package -- check whether it is required explicitly
		suffixIndex = library.find('.so')
		if suffixIndex >= 0:
			name = 'lib:' + library[:suffixIndex]
			if self._hasRequiresEntry(name):
				return False

		# Could be required implicitly by requiring (anything from) the package
		# that provides the library. Find the library in the file system.
		libraryPath = None
		for directory in ['/boot/common/lib', '/boot/system/lib']:
			path = directory + '/' + library
			if os.path.exists(path):
				libraryPath = path
				break

		# Find out which package the library belongs to.
		providingPackage = self._getPackageProvidingPath(libraryPath)
		if not providingPackage:
			print('Warning: failed to determine the package providing "%s"'
				% libraryPath)
			return False

		# Check whether the package is required.
		# Chop off ".hpkg" and the version part from the file name to get the
		# package name.
		packageName = providingPackage[:-5]
		index = packageName.find('-')
		if index >= 0:
			packageName = packageName[:index]
		if self._hasRequiresEntry(packageName):
			return False

		# check whether any of the package's provides are required
		packageProvides = self.requiredPackagesProvides[providingPackage]
		for name in packageProvides:
			if self._hasRequiresEntry(name):
				return False

		return True

	def _getPackageProvidingPath(self, path):
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(['catattr', '-d', 'SYS:PACKAGE', path],
					stderr=devnull)
				if output.endswith('\n'):
					output = output[:-1]
				return output
		except:
			return None

	def _getPackageProvides(self, package):
		# get the package listing
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(['package', 'list', package],
					stderr=devnull)
		except:
			return None

		# extract the provides
		provides = []
		for line in output.split('\n'):
			index = line.find('provides:')
			if index >= 0:
				index += 9
				provides.append(line[index:].strip())

		return self._parseResolvableExpressionList(provides)

	def _checkGlobalSettingsFiles(self):
		# Create a map for the declared global settings files and check them
		# while at it.
		globalSettingsFiles = {}
		for item in self.package.getRecipeKeys()['GLOBAL_SETTINGS_FILES']:
			components = ConfigParser.splitItemAndUnquote(item)
			if components:
				if not components[0].startswith('settings/'):
					self._violation('Package declares invalid global settings '
						'file "%s"' % components[0])

				if len(components) > 1:
					globalSettingsFiles[components[0]] = components[1]
					if not os.path.exists(components[0]):
						self._violation('Package declares non-existent global '
							'settings file "%s" as included' % components[0])
				else:
					globalSettingsFiles[components[0]] = None

		# iterate through the settings files in the package
		if os.path.exists('settings'):
			self._checkGlobalSettingsFilesRecursively(globalSettingsFiles,
				'settings')

	def _checkGlobalSettingsFilesRecursively(self, globalSettingsFiles, path):
		if not os.path.isdir(path):
			if path in globalSettingsFiles:
				if not globalSettingsFiles[path]:
					self._violation('File "%s" declared as not included global '
						'settings file' % path)
			else:
				self._violation('File "%s" not declared as global settings '
					'file' % path)
			return

		# path is a directory -- recurse
		for entry in os.listdir(path):
			self._checkGlobalSettingsFilesRecursively(globalSettingsFiles,
				path + '/' + entry)

	def _checkUserSettingsFiles(self):
		for item in self.package.getRecipeKeys()['USER_SETTINGS_FILES']:
			components = ConfigParser.splitItemAndUnquote(item)
			if not components:
				continue

			if not components[0].startswith('settings/'):
				self._violation('Package declares invalid user settings '
					'file "%s"' % components[0])

			if len(components) > 2:
				if not os.path.exists(components[2]):
					self._violation('Package declares non-existent template '
						'"%s" for user settings file "%s" as included'
						% (components[2], components[0]))

	def _violation(self, message):
		if self.strict:
			self._severeViolation(message)
		else:
			print 'POLICY WARNING: ' + message

	def _severeViolation(self, message):
		sysExit('POLICY ERROR: ' + message)
