# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import glob
import os
import re
from subprocess import check_output

from .ConfigParser import ConfigParser
from .Configuration import Configuration
from .Utils import isCommandAvailable, sysExit, warn

allowedWritableTopLevelDirectories = [
	'cache',
	'non-packaged',
	'settings',
	'var'
]

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
	'servers'
] + allowedWritableTopLevelDirectories

# -- Policy checker class -----------------------------------------------------

class Policy(object):

	# log for policy warnings and errors
	violationsByPort = {}

	def __init__(self, strict):
		self.strict = strict

	def setPort(self, port, requiredPackages):
		self.port = port
		self.secondaryArchitecture = port.secondaryArchitecture
		self.secondaryArchSuffix = '_' + self.secondaryArchitecture \
			if self.secondaryArchitecture else ''
		self.secondaryArchSubDir = '/' + self.secondaryArchitecture \
			if self.secondaryArchitecture else ''

		# Get the provides of all of the port's packages. We need them to find
		# dependencies between packages of the port.
		self.portPackagesProvides = {}
		for package in port.packages:
			self.portPackagesProvides[package.name] = (
				self._parseResolvableExpressionList(
					package.recipeKeys['PROVIDES']))

		# Create a map with the packages' provides. We need that later when
		# checking the created package.
		self.requiredPackagesProvides = {}
		for package in requiredPackages:
			provides = self._getPackageProvides(package)
			self.requiredPackagesProvides[os.path.basename(package)] = provides

	def checkPackage(self, package, packageFile):
		self.package = package
		self.packageFile = packageFile
		self.violationEncountered = False

		self.provides = self._parseResolvableExpressionListForKey('PROVIDES')
		self.requires = self._parseResolvableExpressionListForKey('REQUIRES')

		self._checkTopLevelEntries()
		self._checkProvides()
		self._checkLibraryDependencies()
		self._checkMisplacedDevelopLibraries()
		self._checkGlobalWritableFiles()
		self._checkUserSettingsFiles()
		self._checkPostInstallAndPreUninstallScripts('POST_INSTALL_SCRIPTS', 'post-install')
		self._checkPostInstallAndPreUninstallScripts('PRE_UNINSTALL_SCRIPTS', 'pre-uninstall')

		if self.strict and self.violationEncountered:
			sysExit("packaging policy violation(s) in strict mode")

	def _checkTopLevelEntries(self):
		for entry in os.listdir(self.package.packagingDir):
			if entry not in allowedTopLevelEntries:
				self._violation('Invalid top-level package entry "%s"' % entry)

	def _parseResolvableExpressionListForKey(self, keyName):
		return self._parseResolvableExpressionList(
			self.package.recipeKeys[keyName])

	def _parseResolvableExpressionList(self, theList):
		names = set()
		for item in theList:
			match = re.match(r'[^-/=!<>\s]+', item)
			if match:
				names.add(match.group(0))
		return names

	def _checkProvides(self):
		# check if the package provides itself
		if self.package.name not in self.provides:
			self._violation('no matching self provides for "%s"'
				% self.package.name)

		# everything in bin/ must be declared as cmd:*
		binDir = os.path.join(self.package.packagingDir, 'bin')
		if os.path.exists(binDir):
			for entry in os.listdir(binDir):
				# ignore secondary architecture subdir
				if entry == self.package.secondaryArchitecture:
					continue
				name = self._normalizeResolvableName('cmd:' + entry)
				if name.lower() not in self.provides:
					self._violation('no matching provides "%s" for "%s"'
						% (name, 'bin/' + entry))

		# library entries in lib[/<arch>] must be declared as lib:*[_<arch>]
		libDir = os.path.join(self.package.packagingDir,
			'lib' + self.secondaryArchSubDir)
		if os.path.exists(libDir):
			for entry in os.listdir(libDir):
				suffixIndex = entry.find('.so')
				if suffixIndex < 0:
					continue

				name = self._normalizeResolvableName(
					'lib:' + entry[:suffixIndex] + self.secondaryArchSuffix)
				if name.lower() not in self.provides:
					self._violation('no matching provides "%s" for "%s"'
						% (name, 'lib/' + entry))

		# library entries in develop/lib[<arch>] must be declared as
		# devel:*[_<arch>]
		developLibDir = os.path.join(self.package.packagingDir,
			'develop/lib' + self.secondaryArchSubDir)
		if os.path.exists(developLibDir):
			for entry in os.listdir(developLibDir):
				suffixIndex = entry.find('.so')
				if suffixIndex < 0:
					suffixIndex = entry.find('.a')
					if suffixIndex < 0:
						continue

				name = self._normalizeResolvableName(
					'devel:' + entry[:suffixIndex] + self.secondaryArchSuffix)
				if name.lower() not in self.provides:
					self._violation('no matching provides "%s" for "%s"'
						% (name, 'develop/lib/' + entry))

	def _normalizeResolvableName(self, name):
		# make name a valid resolvable name by replacing '-' with '_'
		return name.replace('-', '_').lower()

	def _checkLibraryDependencies(self):
		# If there's no readelf (i.e. no binutils), there probably aren't any
		# executables/libraries.
		if not isCommandAvailable('readelf'):
			return

		# check all files in bin/, apps/ and lib[/<arch>]
		for directory in ['bin', 'apps', 'lib' + self.secondaryArchSubDir]:
			dir = os.path.join(self.package.packagingDir, directory)
			if not os.path.exists(dir):
				continue

			for entry in os.listdir(dir):
				path = os.path.join(dir, entry)
				if os.path.isfile(path):
					self._checkLibraryDependenciesOfFile(dir, path)
				elif directory != "bin" and os.path.isdir(path):
					for entry2 in os.listdir(path):
						path2 = os.path.join(path, entry2)
						if os.path.isfile(path2) and os.access(path2, os.X_OK):
							self._checkLibraryDependenciesOfFile(path, path2)

	def _checkLibraryDependenciesOfFile(self, dirPath, path):
		# skip static libraries outright
		if path.endswith('.a'):
			return

		# try to read the dynamic section of the file
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(['readelf', '--dynamic', path],
					stderr=devnull).decode('utf-8')
		except:
			return

		libraries = set()
		rpath = None
		# extract the library names from the "(NEEDED)" lines of the output
		for line in output.split('\n'):
			if line.find('(NEEDED)') >= 0:
				match = re.match(r'[^[]*\[(.*)].*', line)
				if match:
					libraries.add(os.path.basename(match.group(1)))
			if line.find('(RPATH)') >= 0:
				match = re.match(r'[^[]*\[(.*)].*', line)
				if match:
					rpath = match.group(1)

		for library in libraries:
			if self._isMissingLibraryDependency(library, dirPath, rpath):
				if (library.startswith('libgcc') or
					library.startswith('libsupc++')):
					continue
				if (library.startswith('libstdc++')):
					suffixIndex = library.find('.so')
					resolvableName = self._normalizeResolvableName(
						'lib:' + library[:suffixIndex] + self.secondaryArchSuffix)
					self.package.recipeKeys['REQUIRES'] += [ resolvableName ]
				else:
					self._violation('"%s" needs library "%s", but the '
						'package doesn\'t seem to declare that as a '
						'requirement' % (path, library))

	def _isMissingLibraryDependency(self, library, dirPath, rpath):
		if library.startswith('_APP_'):
			return False

		# the library might be provided by the package ($libDir)
		libDir = os.path.join(self.package.packagingDir,
			'lib' + self.secondaryArchSubDir + '/' + library)
		if os.path.exists(libDir):
			return False
		if len(glob.glob(libDir + '*')) == 1:
			return False

		# the library might be provided by the package (%A/lib)
		libDir = os.path.join(dirPath, 'lib/' + library)
		if os.path.exists(libDir):
			return False
		if len(glob.glob(libDir + '*')) == 1:
			return False

		# the library might be provided by the package, same dir (%A)
		libDir = os.path.join(dirPath, library)
		if os.path.exists(libDir):
			return False
		if len(glob.glob(libDir + '*')) == 1:
			return False

		# the library might be provided by the package in rpath
		if rpath is not None:
			for rpath1 in rpath.split(':'):
				if rpath1.find('/.self/') != -1:
					rpathDir = os.path.join(self.package.packagingDir,
						rpath1[rpath1.find('/.self/') + len('/.self/'):] + '/' + library)
					if os.path.exists(rpathDir):
						return False
				elif rpath1.find('$ORIGIN') != -1:
					rpathDir = os.path.join(dirPath,
						rpath1[rpath1.find('$ORIGIN/') + len('$ORIGIN/'):] + '/' + library)
					if os.path.exists(rpathDir):
						return False

		# not provided by the package -- check whether it is required explicitly
		suffixIndex = library.find('.so')
		resolvableName = None
		if suffixIndex >= 0:
			resolvableName = self._normalizeResolvableName(
				'lib:' + library[:suffixIndex] + self.secondaryArchSuffix)
			if resolvableName in self.requires:
				return False

		# The library might be provided by a sibling package.
		providingPackage = None
		for packageName in self.portPackagesProvides.keys():
			packageProvides = self.portPackagesProvides[packageName]
			if resolvableName in packageProvides:
				providingPackage = packageName
				break

		if not providingPackage:
			# Could be required implicitly by requiring (anything from) the
			# package that provides the library. Find the library in the file
			# system.
			libraryPath = None
			for directory in ['/boot/system/lib']:
				path = directory + self.secondaryArchSubDir + '/' + library
				if os.path.exists(path):
					libraryPath = path
					break

			if not libraryPath:
				# Don't complain if we're running on non-haiku host.
				if os.path.exists('/boot/system/lib'):
					self._violation('can\'t find used library "%s"' % library)
				return False

			# Find out which package the library belongs to.
			providingPackage = self._getPackageProvidingPath(libraryPath)
			if not providingPackage:
				print('Warning: failed to determine the package providing "%s"'
					% libraryPath)
				return False

			# Chop off ".hpkg" and the version part from the file name to get
			# the package name.
			packageName = providingPackage[:-5]
			index = packageName.find('-')
			if index >= 0:
				packageName = packageName[:index]

			packageProvides = self.requiredPackagesProvides.get(
				providingPackage, [])

		# Check whether the package is required.
		if packageName in self.requires:
			return False

		# check whether any of the package's provides are required
		for name in packageProvides:
			if name in self.requires:
				return False

		return True

	def _getPackageProvidingPath(self, path):
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(
					['catattr', '-d', 'SYS:PACKAGE_FILE', path], stderr=devnull).decode('utf-8')
				if output.endswith('\n'):
					output = output[:-1]
				return output
		except:
			return None

	def _getPackageProvides(self, package):
		# get the package listing
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(
					[Configuration.getPackageCommand(), 'list', package],
					stderr=devnull).decode('utf-8')
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

	def _checkMisplacedDevelopLibraries(self):
		libDir = os.path.join(self.package.packagingDir,
			'lib' + self.secondaryArchSubDir)
		if not os.path.exists(libDir):
			return

		for entry in os.listdir(libDir):
			if not entry.endswith('.a') and not entry.endswith('.la'):
				continue

			path = libDir + '/' + entry
			self._violation('development library entry "%s" should be placed '
				'in "develop/lib%s"' % (path, self.secondaryArchSubDir))

	def _checkGlobalWritableFiles(self):
		# Create a map for the declared global writable files and check them
		# while at it.
		types = {False: 'file', True: 'directory'}
		globalWritableFiles = {}
		fileTypes = {}
		for item in self.package.recipeKeys['GLOBAL_WRITABLE_FILES']:
			if item.strip().startswith('#'):
				continue

			components = ConfigParser.splitItemAndUnquote(item)
			if components:
				path = components[0]
				directory = path
				index = path.find('/')
				if index >= 0:
					directory = path[0:index]

				isDirectory = False
				updateType = None
				if len(components) > 1:
					if components[1] == 'directory':
						isDirectory = True
						if len(components) > 2:
							updateType = components[2]
					else:
						updateType = components[1]

				fileType = types[isDirectory]
				fileTypes[components[0]] = fileType

				if directory not in allowedWritableTopLevelDirectories:
					self._violation('Package declares invalid global writable '
						'%s "%s"' % (fileType, components[0]))

				globalWritableFiles[components[0]] = updateType

				if updateType:
					absPath = os.path.join(self.package.packagingDir, path)
					if not os.path.exists(absPath):
						self._violation('Package declares non-existent global '
							'writable %s "%s" as included' % (fileType, path))
					elif os.path.isdir(absPath) != isDirectory:
						self._violation('Package declares non-existent global '
							'writable %s "%s", but it\'s a %s'
							% (fileType, path, types[not isDirectory]))

		# iterate through the writable directories in the package
		for directory in allowedWritableTopLevelDirectories:
			dir = os.path.join(self.package.packagingDir, directory)
			if os.path.exists(dir):
				self._checkGlobalWritableFilesRecursively(globalWritableFiles,
					fileTypes, directory)

	def _checkGlobalWritableFilesRecursively(self, globalWritableFiles,
			fileTypes, path):
		if path in globalWritableFiles:
			if not globalWritableFiles[path]:
				self._violation('Included "%s" declared as not included global '
					'writable %s' % (path, fileTypes[path]))
			return

		absPath = os.path.join(self.package.packagingDir, path)
		if not os.path.isdir(absPath):
			self._violation('Included file "%s" not declared as global '
				'writable file' % path)
			return

		# entry is a directory -- recurse
		for entry in os.listdir(absPath):
			self._checkGlobalWritableFilesRecursively(globalWritableFiles,
				fileTypes, path + '/' + entry)

	def _checkUserSettingsFiles(self):
		for item in self.package.recipeKeys['USER_SETTINGS_FILES']:
			if item.strip().startswith('#'):
				continue

			components = ConfigParser.splitItemAndUnquote(item)
			if not components:
				continue

			if not components[0].startswith('settings/'):
				self._violation('Package declares invalid user settings '
					'file "%s"' % components[0])
			if len(components) > 1 and components[1] == 'directory':
				continue

			if len(components) > 2:
				template = os.path.join(self.package.packagingDir,
					components[2])
				if not os.path.exists(template):
					self._violation('Package declares non-existent template '
						'"%s" for user settings file "%s" as included'
						% (components[2], components[0]))

	def _checkPostInstallAndPreUninstallScripts(self, recipeKey, scriptType):
		# check whether declared scripts exist
		declaredFiles = set()
		for script in self.package.recipeKeys[recipeKey]:
			if script.lstrip().startswith('#'):
				continue

			components = ConfigParser.splitItemAndUnquote(script)
			if not components:
				continue
			script = components[0]
			declaredFiles.add(script)

			absScript = os.path.join(self.package.packagingDir, script)
			if not os.path.exists(absScript):
				self._violation('Package declares non-existent %s '
					'script "%s"' % (scriptType, script))

		# check whether existing scripts are declared
		relativeDir = 'boot/' + scriptType
		dir = os.path.join(self.package.packagingDir, relativeDir)
		if os.path.exists(dir):
			for script in os.listdir(dir):
				path = relativeDir + '/' + script
				if path not in declaredFiles:
					self._violation('script "%s" not declared as %s '
						'script' % (path, scriptType))

	def _violation(self, message):
		self.violationEncountered = True
		if self.strict:
			violation = 'POLICY ERROR: ' + message
		else:
			violation = 'POLICY WARNING: ' + message
		warn(violation)
		if self.port.versionedName not in Policy.violationsByPort:
			Policy.violationsByPort[self.port.versionedName] = [violation]
		else:
			Policy.violationsByPort[self.port.versionedName].append(violation)
