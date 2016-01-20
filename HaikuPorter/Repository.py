# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .Configuration import Configuration
from .Options import getOption
from .Port import Port
from .Utils import sysExit, touchFile, versionCompare, warn

import glob
import json
import os
import re
import shutil
from subprocess import check_call, check_output
import sys
from textwrap import dedent


# -- Repository class ---------------------------------------------------------

class Repository(object):

	currentFormatVersion = 1

	def __init__(self, treePath, outputDirectory, packagesPath, shellVariables,
			policy, preserveFlags, quiet = False, verbose = False):
		self.treePath = treePath
		self.outputDirectory = outputDirectory
		self.path = self.outputDirectory + '/repository'
		self.inputSourcePackagesPath \
			= self.outputDirectory + '/input-source-packages'
		self.packagesPath = packagesPath
		self.shellVariables = shellVariables
		self.policy = policy
		self.quiet = quiet
		self.verbose = verbose

		self._formatVersionFilePath = self.path + '/.formatVersion'
		self._portIdForPackageIdFilePath \
			= self.path + '/.portIdForPackageIdMap'
		self._portNameForPackageNameFilePath \
			= self.path + '/.portNameForPackageNameMap'

		# check repository format
		formatVersion = self._readFormatVersion()
		if formatVersion > Repository.currentFormatVersion:
			sysExit('The version of the repository format used in\n\t%s'
					'\nis newer than the one supported by haikuporter.\n'
					'Please upgrade haikuporter.' % self.path)

		# update repository if it exists and isn't empty, populate it otherwise
		self._initAllPorts()
		self._initPortForPackageMaps()
		if (os.path.isdir(self.path) and os.listdir(self.path)
			and os.path.exists(self._portIdForPackageIdFilePath)
			and os.path.exists(self._portNameForPackageNameFilePath)
			and formatVersion == Repository.currentFormatVersion):
			self._updateRepository()
		else:
			if formatVersion < Repository.currentFormatVersion:
				warn('Found old repository format - repopulating the '
					 'repository ...')
			self._populateRepository(preserveFlags)
			self._writeFormatVersion()
		self._writePortForPackageMaps()

	def getPortIdForPackageId(self, packageId):
		"""return the port-ID for the given package-ID"""

		return self._portIdForPackageId.get(packageId, None)

	def getPortNameForPackageName(self, packageName):
		"""return the port name for the given package name"""

		return self._portNameForPackageName.get(packageName, None)

	@property
	def allPorts(self):
		return self._allPorts

	@property
	def portVersionsByName(self):
		return self._portVersionsByName

	def getActiveVersionOf(self, portName, warnAboutSkippedVersions = False):
		"""return the highest buildable version of the port with the given
		   name"""
		if not portName in self._portVersionsByName:
			return None

		versions = self._portVersionsByName[portName]
		for version in reversed(versions):
			portID = portName + '-' + version
			port = self._allPorts[portID]
			if port.hasBrokenRecipe:
				if warnAboutSkippedVersions:
					warn('skipping %s, as the recipe is broken' % portID)
					try:
						port.parseRecipeFileRaisingExceptions(True)
					except SystemExit as e:
						print e.code
				continue
			if not port.isBuildableOnTargetArchitecture:
				if warnAboutSkippedVersions:
					status = port.statusOnTargetArchitecture
					warn(('skipping %s, as it is %s on the target '
						  + 'architecture.') % (portID, status))
				continue
			return version

		return None

	def searchPorts(self, regExp):
		"""Search for one or more ports in the HaikuPorts tree, returning
		   a list of found matches"""
		if regExp:
			reSearch = re.compile(regExp)

		ports = []
		portNames = self.portVersionsByName.keys()
		for portName in portNames:
			if not regExp or reSearch.search(portName):
				ports.append(portName)

		return sorted(ports)

	def _initAllPorts(self):
		# Collect all ports into a dictionary that can be keyed by
		# name + '-' + version. Additionally, we keep a sorted list of
		# available versions for each port name.
		self._allPorts = {}
		self._portVersionsByName = {}

		## REFACTOR into separate methods

		# every existing input source package defines a port (which overrules
		# any corresponding port in the recipe tree)
		if os.path.exists(self.inputSourcePackagesPath):
			for fileName in sorted(os.listdir(self.inputSourcePackagesPath)):
				if not ('_source-' in fileName
						or '_source_rigged-' in fileName):
					continue

				recipeFilePath \
					= self._partiallyExtractSourcePackageIfNeeded(fileName)

				recipeName = os.path.basename(recipeFilePath)
				name, version = recipeName[:-7].split('-')
				if name not in self._portVersionsByName:
					self._portVersionsByName[name] = [ version ]
				else:
					self._portVersionsByName[name].append(version)

				portPath = os.path.dirname(recipeFilePath)
				if self.outputDirectory == self.treePath:
					portOutputPath = portPath
				else:
					portOutputPath = (self.outputDirectory
									  + '/input-source-packages/' + name)
				self._allPorts[name + '-' + version] \
					= Port(name, version, '<source-package>', portPath,
						   portOutputPath, self.path, self.shellVariables,
						   self.policy)

		# collect ports from the recipe tree
		for category in sorted(os.listdir(self.treePath)):
			categoryPath = self.treePath + '/' + category
			if (not os.path.isdir(categoryPath) or category[0] == '.'
				or '-' not in category):
				continue
			for port in sorted(os.listdir(categoryPath)):
				portPath = categoryPath + '/' + port
				portOutputPath = (self.outputDirectory + '/' + category + '/'
					+ port)
				if not os.path.isdir(portPath) or port[0] == '.':
					continue
				for recipe in os.listdir(portPath):
					recipePath = portPath + '/' + recipe
					if (not os.path.isfile(recipePath)
						or not recipe.endswith('.recipe')):
						continue
					portElements = recipe[:-7].split('-')
					if len(portElements) == 2:
						name, version = portElements
						versionedName = name + '-' + version
						if versionedName in self._allPorts:
							# this version of the current port already was
							# defined - skip
							if not self.quiet and not getOption('doBootstrap'):
								otherPort = self._allPorts[versionedName]
								if otherPort.category == '<source-package>':
									warn('%s/%s	 is overruled by input source '
										 'package' % (category, versionedName))
								else:
									warn('%s/%s	 is overruled by duplicate in '
										  '%s - please remove one of them'
										  % (category, versionedName,
											 otherPort.category))
							continue
						if name not in self._portVersionsByName:
							self._portVersionsByName[name] = [ version ]
						else:
							self._portVersionsByName[name].append(version)
						self._allPorts[name + '-' + version] = Port(name,
							version, category, portPath, portOutputPath,
							self.path, self.shellVariables, self.policy)
					else:
						# invalid argument
						if not self.quiet:
							print("Warning: Couldn't parse port/version info: "
								  + recipe)

		# Create ports for the secondary architectures. Not all make sense or
		# are supported, but we won't know until we have parsed the recipe file.
		secondaryArchitectures = Configuration.getSecondaryTargetArchitectures()
		if secondaryArchitectures:
			for port in self._allPorts.values():
				for architecture in secondaryArchitectures:
					newPort = Port(port.baseName, port.version, port.category,
						port.baseDir, port.outputDir, self.path,
						self.shellVariables, port.policy, architecture)
					self._allPorts[newPort.versionedName] = newPort

					name = newPort.name
					version = newPort.version
					if name not in self._portVersionsByName:
						self._portVersionsByName[name] = [ version ]
					else:
						self._portVersionsByName[name].append(version)

		# Sort version list of each port
		for portName in self._portVersionsByName.keys():
			self._portVersionsByName[portName].sort(cmp=versionCompare)

	def _initPortForPackageMaps(self):
		"""Initialize dictionaries that map package names/IDs to port
		   names/IDs"""

		self._portIdForPackageId = {}
		if os.path.exists(self._portIdForPackageIdFilePath):
			try:
				with open(self._portIdForPackageIdFilePath, 'r') as fh:
					self._portIdForPackageId = json.load(fh)
			except BaseException as e:
				print e

		self._portNameForPackageName = {}
		if os.path.exists(self._portNameForPackageNameFilePath):
			try:
				with open(self._portNameForPackageNameFilePath, 'r') as fh:
					self._portNameForPackageName = json.load(fh)
			except BaseException as e:
				print e

	def _writePortForPackageMaps(self):
		"""Writes dictionaries that map package names/IDs to port
		   names/IDs to a file"""

		try:
			with open(self._portIdForPackageIdFilePath, 'w') as fh:
				json.dump(self._portIdForPackageId, fh, sort_keys = True,
						  indent = 4, separators = (',', ' : '))
		except BaseException as e:
			print e

		try:
			with open(self._portNameForPackageNameFilePath, 'w') as fh:
				json.dump(self._portNameForPackageName, fh, sort_keys = True,
						  indent = 4, separators = (',', ' : '))
		except BaseException as e:
			print e

	def _readFormatVersion(self):
		"""Read format version of repository from file"""

		formatVersion = 0
		if os.path.exists(self._formatVersionFilePath):
			try:
				with open(self._formatVersionFilePath, 'r') as fh:
					data = json.load(fh)
				formatVersion = data.get('formatVersion', 0)
			except BaseException as e:
				print e
		return formatVersion

	def _writeFormatVersion(self):
		"""Writes the version of the repository format into a file"""

		try:
			data = {
				'formatVersion': Repository.currentFormatVersion
			}
			with open(self._formatVersionFilePath, 'w') as fh:
				json.dump(data, fh, indent = 4, separators = (',', ' : '))
		except BaseException as e:
			print e

	def _populateRepository(self, preserveFlags):
		"""Remove and refill the repository with all DependencyInfo-files from
		   parseable recipes"""

		if os.path.exists(self.path):
			shutil.rmtree(self.path)
		newRepositoryPath = self.path + '.new'
		if os.path.exists(newRepositoryPath):
			shutil.rmtree(newRepositoryPath)
		os.mkdir(newRepositoryPath)
		skippedDir = newRepositoryPath + '/.skipped'
		os.mkdir(skippedDir)
		if not self.quiet:
			print 'Populating repository ...'

		allPorts = self.allPorts
		for portName in sorted(self._portVersionsByName.keys(), key=str.lower):
			for version in reversed(self._portVersionsByName[portName]):
				portID = portName + '-' + version
				port = allPorts[portID]
				try:
					if not self.quiet:
						sys.stdout.write(' ' * 60)
						sys.stdout.write('\r\t%s' % port.versionedName)
						sys.stdout.flush()
					port.parseRecipeFile(False)
					if port.isBuildableOnTargetArchitecture:
						if (port.checkFlag('build')
							and not preserveFlags):
							if not self.quiet:
								print '	  [build-flag reset]'
							port.unsetFlag('build')
						else:
							if not self.quiet:
								print
						port.writeDependencyInfosIntoRepository(newRepositoryPath)
						for package in port.packages:
							self._portIdForPackageId[package.versionedName] \
								= port.versionedName
							self._portNameForPackageName[package.name] \
								= port.name
						break
					else:
						# take notice of skipped recipe file
						touchFile(skippedDir + '/' + portID)
						if not self.quiet:
							status = port.statusOnTargetArchitecture
							print((' is skipped, as it is %s on target '
								  + 'architecture') % status)
				except SystemExit as e:
					# take notice of broken recipe file
					touchFile(skippedDir + '/' + portID)
					if not self.quiet:
						print ""
					if self.verbose:
						print e.code
		os.rename(newRepositoryPath, self.path)

	def supportBackwardsCompatibility(self, buildName, buildVersion):
		"""Update all DependencyInfo-files in the repository as needed for
		   the given port"""

		allPorts = self.allPorts
		brokenPorts = []
		skippedDir = self.path + '/.skipped'

		if not self.quiet:
			print 'Checking if package dependencies need to be updated ...'

		for portName in sorted(self._portVersionsByName.keys(), key=str.lower):
			for version in reversed(self._portVersionsByName[portName]):
				portID = portName + '-' + version
				port = allPorts[portID]

				# ignore recipes that were skipped last time unless they've
				# been changed since then
				if (os.path.exists(skippedDir + '/' + portID)
					and (os.path.getmtime(port.recipeFilePath)
						 <= os.path.getmtime(skippedDir + '/' + portID))):
					continue

				# ignore recipes without the correct name
				if (buildName != portName):
					continue

				mainDependencyInfoFile = (self.path + '/'
										  + port.dependencyInfoName)
				if (version != buildVersion):
					# remove dependency infos from incorrect version, if it exists
					if os.path.exists(mainDependencyInfoFile):
						if not self.quiet:
							print('\tremoving dependency-infos for '
								  + portID + ', as different version is active')
						port.removeDependencyInfosFromRepository(self.path)
						port.obsoletePackages(self.packagesPath)
					continue

				# try to parse updated recipe
				try:
					port.parseRecipeFile(False)

					if not port.isBuildableOnTargetArchitecture:
						touchFile(skippedDir + '/' + portID)
						if not self.quiet:
							status = port.statusOnTargetArchitecture
							print(('\t%s is still marked as %s on target '
								   + 'architecture') % (portID, status))
						continue

					if os.path.exists(skippedDir + '/' + portID):
						os.remove(skippedDir + '/' + portID)

					if not self.quiet:
						print '\tupdating dependency infos of ' + portID
					port.writeDependencyInfosIntoRepository(self.path)
					for package in port.packages:
						self._portIdForPackageId[package.versionedName] \
							= port.versionedName
						self._portNameForPackageName[package.name] \
							= port.name
				except SystemExit as e:
					# take notice of broken recipe file
					touchFile(skippedDir + '/' + portID)
					if os.path.exists(mainDependencyInfoFile):
						brokenPorts.append(portID)
					elif not self.quiet:
						print '\trecipe for %s is still broken:' % portID
						print '\n'.join(['\t'+line for line in e.code.split('\n')])

	def _updateRepository(self):
		"""Update all DependencyInfo-files in the repository as needed"""

		allPorts = self.allPorts

		brokenPorts = []
		## REFACTOR into separate methods

		# check for all known ports if their recipe has been changed
		if not self.quiet:
			print 'Checking if any package-infos need to be updated ...'
		skippedDir = self.path + '/.skipped'
		for portName in sorted(self._portVersionsByName.keys(), key=str.lower):
			higherVersionIsActive = False
			for version in reversed(self._portVersionsByName[portName]):
				portID = portName + '-' + version
				port = allPorts[portID]

				# ignore recipes that were skipped last time unless they've
				# been changed since then
				if (os.path.exists(skippedDir + '/' + portID)
					and (os.path.getmtime(port.recipeFilePath)
						 <= os.path.getmtime(skippedDir + '/' + portID))):
					continue

				# update all dependency-infos of port if the recipe is newer
				# than the main package-info of that port
				mainDependencyInfoFile = (self.path + '/'
										  + port.dependencyInfoName)
				if (os.path.exists(mainDependencyInfoFile)
					and not higherVersionIsActive
					and (os.path.getmtime(port.recipeFilePath)
						 <= os.path.getmtime(mainDependencyInfoFile))):
					higherVersionIsActive = True
					break

				# try to parse updated recipe
				try:
					port.parseRecipeFile(False)

					if higherVersionIsActive:
						# remove dependency infos from lower version, if it exists
						if os.path.exists(mainDependencyInfoFile):
							if not self.quiet:
								print('\tremoving dependency-infos for '
									  + portID + ', as newer version is active')
							port.removeDependencyInfosFromRepository(self.path)
							port.obsoletePackages(self.packagesPath)
							break
						continue

					if not port.isBuildableOnTargetArchitecture:
						touchFile(skippedDir + '/' + portID)
						if not self.quiet:
							status = port.statusOnTargetArchitecture
							print(('\t%s is still marked as %s on target '
								   + 'architecture') % (portID, status))
						continue

					higherVersionIsActive = True
					if os.path.exists(skippedDir + '/' + portID):
						os.remove(skippedDir + '/' + portID)

					if not self.quiet:
						print '\tupdating dependency infos of ' + portID
					port.writeDependencyInfosIntoRepository(self.path)
					for package in port.packages:
						self._portIdForPackageId[package.versionedName] \
							= port.versionedName
						self._portNameForPackageName[package.name] \
							= port.name

				except SystemExit as e:
					if not higherVersionIsActive:
						# take notice of broken recipe file
						touchFile(skippedDir + '/' + portID)
						if os.path.exists(mainDependencyInfoFile):
							brokenPorts.append(portID)
						else:
							if not self.quiet:
								print '\trecipe for %s is still broken:' % portID
								print '\n'.join(['\t'+line for line in e.code.split('\n')])

		self._removeStaleDependencyInfos(brokenPorts)
		self._removeStalePortForPackageMappings(brokenPorts)

	def _removeStaleDependencyInfos(self, brokenPorts):
		"""check for any dependency-infos that no longer have a corresponding
		   recipe file"""

		allPorts = self.allPorts

		if not self.quiet:
			print "Looking for stale dependency-infos ..."
		dependencyInfos = glob.glob(self.path + '/*.DependencyInfo')
		for dependencyInfo in dependencyInfos:
			dependencyInfoFileName = os.path.basename(dependencyInfo)
			packageID \
				= dependencyInfoFileName[:dependencyInfoFileName.rindex('.')]
			portID = self.getPortIdForPackageId(packageID)

			if not portID or portID not in allPorts or portID in brokenPorts:
				if not self.quiet:
					print '\tremoving ' + dependencyInfoFileName
				os.remove(dependencyInfo)

				# obsolete corresponding package, if any
				self._removePackagesForDependencyInfo(dependencyInfo)

	def _removePackagesForDependencyInfo(self, dependencyInfo):
		"""remove all packages for the given dependency-info"""

		(packageSpec, unused) = os.path.basename(dependencyInfo).rsplit('.', 1)
		packages = glob.glob(self.packagesPath + '/' + packageSpec + '-*.hpkg')
		obsoleteDir = self.packagesPath + '/.obsolete'
		for package in packages:
			packageFileName = os.path.basename(package)
			if not self.quiet:
				print '\tobsoleting package ' + packageFileName
			obsoletePackage = obsoleteDir + '/' + packageFileName
			if not os.path.exists(obsoleteDir):
				os.mkdir(obsoleteDir)
			os.rename(package, obsoletePackage)

	def _removeStalePortForPackageMappings(self, brokenPorts):
		"""drops any port-for-package mappings that refer to non-existing or
		   broken ports"""

		for packageId, portId in self._portIdForPackageId.items():
			if portId not in self._allPorts or portId in brokenPorts:
				del self._portIdForPackageId[packageId]

		for packageName, portName in self._portNameForPackageName.items():
			if portName not in self._portVersionsByName:
				del self._portNameForPackageName[packageName]
			if portName in self._portVersionsByName:
				for version in self._portVersionsByName[portName]:
					portId = portName + '-' + version
					if portId not in brokenPorts:
						break
				else:
					# no version exists of this port that is not broken
					del self._portNameForPackageName[packageName]

	def _partiallyExtractSourcePackageIfNeeded(self, sourcePackageName):
		"""extract the recipe and potentially contained patches/licenses from
		   a source package, unless that has already been done"""

		sourcePackagePath \
			= self.inputSourcePackagesPath + '/' + sourcePackageName
		(name, version, revision, unused) = sourcePackageName.split('-')
		# determine port name by dropping '_source' or '_source_rigged'
		if name.endswith('_source_rigged'):
			name = name[:-14]
		elif name.endswith('_source'):
			name = name[:-7]
		relativeBasePath \
			= 'develop/sources/%s-%s-%s' % (name, version, revision)
		recipeName = name + '-' + version + '.recipe'
		recipeFilePath = (self.inputSourcePackagesPath + '/' + relativeBasePath
						  + '/' + recipeName)

		if (not os.path.exists(recipeFilePath)
			or (os.path.getmtime(recipeFilePath)
				<= os.path.getmtime(sourcePackagePath))):
			# extract recipe, patches and licenses (but skip everything else)
			allowedEntries = [
				relativeBasePath + '/' + recipeName,
				relativeBasePath + '/additional-files',
				relativeBasePath + '/licenses',
				relativeBasePath + '/patches',
			]
			entries = check_output([Configuration.getPackageCommand(), 'list',
								  '-p', sourcePackagePath]).splitlines()
			entries = [
				entry for entry in entries if entry in allowedEntries
			]
			check_call([Configuration.getPackageCommand(), 'extract',
						'-C', self.inputSourcePackagesPath, sourcePackagePath]
					   + entries)

			# override all SOURCE_URIs in recipe to point to the source package
			textToAdd = dedent(r'''
				# Added by haikuporter:
				SOURCE_URI='pkg:%s'
				for i in {2..1000}; do
					eval currentSrcUri=\$SOURCE_URI_$i
					if [ -z "$currentSrcUri" ]; then
						break
					fi
					eval SOURCE_URI_$i="$SOURCE_URI"
				done
				'''[1:]) % sourcePackagePath
			with open(recipeFilePath, 'a') as recipeFile:
				recipeFile.write('\n' + textToAdd)

		return recipeFilePath
