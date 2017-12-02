# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .BuildPlatform import buildPlatform
from .Configuration import Configuration
from .Options import getOption
from .Port import Port
from .Utils import sysExit, touchFile, versionCompare, warn

import codecs
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

	def __init__(self, treePath, outputDirectory, repositoryPath,
			packagesPath, shellVariables,
			policy, preserveFlags, quiet = False, verbose = False):
		self.treePath = treePath
		self.outputDirectory = outputDirectory
		self.path = repositoryPath
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
			sysExit(u'The version of the repository format used in\n\t%s'
					u'\nis newer than the one supported by haikuporter.\n'
					u'Please upgrade haikuporter.' % self.path)

		Port.setRepositoryDir(self.path)

		# update repository if it exists and isn't empty, populate it otherwise
		self._initAllPorts()
		self._initPortForPackageMaps()
		if (os.path.isdir(self.path) and os.listdir(self.path)
			and os.path.exists(self._portIdForPackageIdFilePath)
			and os.path.exists(self._portNameForPackageNameFilePath)
			and formatVersion == Repository.currentFormatVersion):
			if not getOption('noRepositoryUpdate'):
				self._updateRepository()
		else:
			if getOption('noRepositoryUpdate'):
				sysExit(u'no or outdated repository found but no update allowed')
			if formatVersion < Repository.currentFormatVersion:
				warn(u'Found old repository format - repopulating the '
					 u'repository ...')
			self._populateRepository(preserveFlags)
			self._writeFormatVersion()
		self._writePortForPackageMaps()
		self._activePorts = None

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
	def activePorts(self):
		if self._activePorts != None:
			return self._activePorts

		self._activePorts = []
		for portName in self._portVersionsByName.keys():
			activePortVersion = self.getActiveVersionOf(portName)
			if not activePortVersion:
				continue
			self._activePorts.append(
				self._allPorts[portName + '-' + activePortVersion])

		return self._activePorts

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
					warn(u'skipping %s, as the recipe is broken' % portID)
					try:
						port.parseRecipeFileRaisingExceptions(True)
					except SystemExit as e:
						print e.code
				continue
			if not port.isBuildableOnTargetArchitecture:
				if warnAboutSkippedVersions:
					status = port.statusOnTargetArchitecture
					warn((u'skipping %s, as it is %s on the target '
						  + 'architecture.') % (portID, status))
				continue
			return version

		return None

	def getActivePort(self, portName):
		"""return the highest buildable version of the port with the given
		   name"""
		version = self._portNameVersionForPortName(portName)
		if version == None:
			return None

		return self._allPorts[version]

	def _portNameVersionForPortName(self, portName):
		portVersion = self.getActiveVersionOf(portName)
		if not portVersion:
			return None
		return portName + '-' + portVersion

	def searchPorts(self, regExp, returnPortNameVersions = False):
		"""Search for one or more ports in the HaikuPorts tree, returning
		   a list of found matches"""
		if regExp:
			if getOption('literalSearchStrings'):
				regExp = re.escape(regExp)
			reSearch = re.compile(regExp)

		ports = []
		portNames = self.portVersionsByName.keys()
		for portName in portNames:
			if not regExp or reSearch.search(portName):
				if returnPortNameVersions:
					portNameVersion = self._portNameVersionForPortName(portName)
					if portNameVersion is not None:
						ports.append(portNameVersion)
				else:
					ports.append(portName)

		return sorted(ports)

	def _fileNameForPackageName(self, packageName):
		portName = self._portNameForPackageName[packageName]
		portVersion = self.getActiveVersionOf(portName)
		if not portVersion:
			return None

		port = self._allPorts[portName + '-' + portVersion]
		for package in port.packages:
			if package.name == packageName:
				return package.hpkgName

	def searchPackages(self, regExp, returnFileNames = True):
		"""Search for one or more packages in the HaikuPorts tree, returning
		   a list of found matches"""
		if regExp:
			if getOption('literalSearchStrings'):
				regExp = re.escape(regExp)
			reSearch = re.compile(regExp)

		packages = []
		packageNames = self._portNameForPackageName.keys()
		for packageName in packageNames:
			if not regExp or reSearch.search(packageName):
				if returnFileNames:
					packageName = self._fileNameForPackageName(packageName)
					if not packageName:
						continue

				packages.append(packageName)

		return sorted(packages)

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
						   portOutputPath, self.shellVariables,
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
									warn(u'%s/%s	 is overruled by input source '
										 u'package' % (category, versionedName))
								else:
									warn(u'%s/%s	 is overruled by duplicate in '
										  u'%s - please remove one of them'
										  % (category, versionedName,
											 otherPort.category))
							continue
						if name not in self._portVersionsByName:
							self._portVersionsByName[name] = [ version ]
						else:
							self._portVersionsByName[name].append(version)
						self._allPorts[name + '-' + version] = Port(name,
							version, category, portPath, portOutputPath,
							self.shellVariables, self.policy)
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
						port.baseDir, port.outputDir, self.shellVariables,
						port.policy, architecture)
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

		self._portNameForPackageName = {}
		self._portIdForPackageId = {}
		self._updateRepository(None, preserveFlags)
		return

	def supportBackwardsCompatibility(self, name, version):
		self._updateRepository({ 'name': name, 'version': version })

	def _updateRepository(self, explicitPortVersion=None, preserveFlags=True):
		"""Update all DependencyInfo-files in the repository as needed"""

		allPorts = self.allPorts

		activePorts = []
		updatedPorts = {}

		# check for all known ports if their recipe has been changed
		if os.path.exists(self.path):
			if not self.quiet:
				print 'Checking if any package-infos need to be updated ...'
		else:
			os.makedirs(self.path)
			if not self.quiet:
				print 'Populating repository ...'

		skippedDir = os.path.join(self.path, '.skipped')
		if not os.path.exists(skippedDir):
			os.mkdir(skippedDir)

		for portName in sorted(self._portVersionsByName.keys(),
				key=unicode.lower):

			if explicitPortVersion and explicitPortVersion['name'] == portName:
				versions = [explicitPortVersion['version']]
			else:
				versions = reversed(self._portVersionsByName[portName])

			for version in versions:
				portID = portName + '-' + version
				port = allPorts[portID]
				skippedFlag = os.path.join(skippedDir, portID)

				# ignore recipes that were skipped last time unless they've
				# been changed since then
				if (os.path.exists(skippedFlag)
					and (os.path.getmtime(port.recipeFilePath)
						<= os.path.getmtime(skippedFlag))):
					continue

				# update all dependency-infos of port if the recipe is newer
				# than the main package-info of that port
				mainDependencyInfoFile = os.path.join(self.path,
					port.dependencyInfoName)
				if (os.path.exists(mainDependencyInfoFile)
					and (os.path.getmtime(port.recipeFilePath)
						<= os.path.getmtime(mainDependencyInfoFile))):
					activePorts.append(portID)
					break

				# try to parse updated recipe
				try:
					port.parseRecipeFile(False)

					if not port.isBuildableOnTargetArchitecture:
						touchFile(skippedFlag)
						if not self.quiet:
							status = port.statusOnTargetArchitecture
							print(('\t%s is still marked as %s on target '
								+ 'architecture') % (portID, status))
						continue

					if os.path.exists(skippedFlag):
						os.remove(skippedFlag)

					if not preserveFlags and port.checkFlag('build'):
						if not self.quiet:
							print('\t[build-flag reset]')
						port.unsetFlag('build')

					if not self.quiet:
						print('\tupdating dependency infos of ' + portID)

					port.writeDependencyInfosIntoRepository()
					updatedPorts[portID] = port
					break

				except SystemExit as e:
					# take notice of broken recipe file
					touchFile(skippedFlag)
					if not os.path.exists(mainDependencyInfoFile):
						if not self.quiet:
							print '\trecipe for %s is still broken:' % portID
							print '\n'.join(['\t'+line for line in e.code.split('\n')])

		# This also drops mappings for updated ports to remove any possibly
		# removed sub-packages.
		self._removeStalePortForPackageMappings(activePorts)

		# Add port for package mappings for updated ports.
		for portID, port in updatedPorts.iteritems():
			for package in port.packages:
				self._portIdForPackageId[package.versionedName] \
					= port.versionedName
				self._portNameForPackageName[package.name] \
					= port.name
			activePorts.append(portID)

		# Note that removing stale dependency infos uses the port for package
		# mappings to determine what to keep. This step must therefore come
		# after the stale port for package mapping removal.
		self._removeStaleDependencyInfos(activePorts)

	def _removeStaleDependencyInfos(self, activePorts):
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

			if not portID or portID not in activePorts:
				if not self.quiet:
					print '\tremoving ' + dependencyInfoFileName
				os.remove(dependencyInfo)

				if not getOption('noPackageObsoletion'):
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

	def _removeStalePortForPackageMappings(self, activePorts):
		"""drops any port-for-package mappings that refer to non-existing or
		   broken ports"""

		for packageId, portId in self._portIdForPackageId.items():
			if portId not in activePorts:
				del self._portIdForPackageId[packageId]

		for packageName, portName in self._portNameForPackageName.items():
			if portName not in self._portVersionsByName:
				del self._portNameForPackageName[packageName]
				continue

			for version in self._portVersionsByName[portName]:
				portId = portName + '-' + version
				if portId in activePorts:
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
				for i in {001..999}; do
					eval currentSrcUri=\$SOURCE_URI_$i
					if [ -z "$currentSrcUri" ]; then
						break
					fi
					eval SOURCE_URI_$i="$SOURCE_URI"
				done
				'''[1:]) % sourcePackagePath
			with codecs.open(recipeFilePath, 'a', 'utf-8') as recipeFile:
				recipeFile.write('\n' + textToAdd)

		return recipeFilePath
