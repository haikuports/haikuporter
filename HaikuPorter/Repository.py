# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Configuration import Configuration
from HaikuPorter.Options import getOption
from HaikuPorter.Port import Port
from HaikuPorter.Utils import (check_output, touchFile, versionCompare, warn)

import glob
import os
import re
import shutil
from subprocess import check_call
import sys


# -- Repository class ---------------------------------------------------------

class Repository(object):
	def __init__(self, treePath, outputDirectory, packagesPath, shellVariables,
			policy, preserveFlags, quiet = False):
		self.treePath = treePath
		self.outputDirectory = outputDirectory
		self.path = self.outputDirectory + '/repository'
		self.inputSourcePackagesPath \
			= self.outputDirectory + '/input-source-packages'
		self.packagesPath = packagesPath
		self.shellVariables = shellVariables
		self.policy = policy
		self.quiet = quiet

		# update repository if it exists and isn't empty, populate it otherwise
		self._initAllPorts()
		if (os.path.isdir(self.path)
			and os.listdir(self.path)):
			self._updateRepository()
		else:
			self._populateRepository(preserveFlags)

	def getPortIdForPackageId(self, packageId):
		"""return the port-ID for the given package-ID"""

		# cut out subparts from the package name until we find a port
		# with that name:
		(portName, version) = packageId.rsplit('-', 1)
		(portName, unused1, unused2) = portName.rpartition('_')
		while portName:
			portID = portName + '-' + version
			if portID in self._allPorts:
				return portID
			(portName, unused1, unused2) = portName.rpartition('_')

		# no corresponding port-ID was found
		return None

	def getPortNameForPackageName(self, packageName):
		"""return the port name for the given package name"""

		# cut out subparts from the package name until we find a port
		# with that name:
		portName = packageName
		(portName, unused1, unused2) = portName.rpartition('_')
		while portName:
			if portName in self._portVersionsByName:
				return portName
			(portName, unused1, unused2) = portName.rpartition('_')

		# no corresponding port-ID was found
		return None

	def getAllPorts(self):
		return self._allPorts

	def getPortVersionsByName(self):
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
			if port.hasBrokenRecipe():
				if warnAboutSkippedVersions:
					warn('skipping %s, as the recipe is broken:' % portID)
					try:
						port.parseRecipeFile(True)
					except SystemExit as e:
						print e
				continue
			if not port.isBuildableOnTargetArchitecture():
				if warnAboutSkippedVersions:
					status = port.getStatusOnTargetArchitecture()
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
		portNames = self.getPortVersionsByName().keys()
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

		# every existing input source package defines a port (which overrules
		# any corresponding port in the recipe tree)
		if os.path.exists(self.inputSourcePackagesPath):
			for fileName in sorted(os.listdir(self.inputSourcePackagesPath)):
				if not fileName.endswith('-source.hpkg'):
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
						   portOutputPath, self.shellVariables, self.policy)

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
							# defined by an input source package - skip
							if not self.quiet and not getOption('doBootstrap'):
								print('Warning: ' + versionedName + ' in tree '
									  'is overruled by input source package')
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

	def _populateRepository(self, preserveFlags):
		"""Remove and refill the repository with all PackageInfo-files from
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

		allPorts = self.getAllPorts()
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
					if port.isBuildableOnTargetArchitecture():
						if (port.checkFlag('build')
							and not preserveFlags):
							if not self.quiet:
								print '   [build-flag reset]'
							port.unsetFlag('build')
						else:
							if not self.quiet:
								print
						port.writePackageInfosIntoRepository(newRepositoryPath)
						break
					else:
						# take notice of skipped recipe file
						touchFile(skippedDir + '/' + portID)
						if not self.quiet:
							status = port.getStatusOnTargetArchitecture()
							print((' is skipped, as it is %s on target '
								  + 'architecture') % status)
				except SystemExit:
					# take notice of broken recipe file
					touchFile(skippedDir + '/' + portID)
					if not self.quiet:
						sys.stdout.write('\r')
					pass
		os.rename(newRepositoryPath, self.path)

	def _updateRepository(self):
		"""Update all PackageInfo-files in the repository as needed"""

		allPorts = self.getAllPorts()

		brokenPorts = []

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

				# update all package-infos of port if the recipe is newer than
				# the main package-info of that port
				mainPackageInfoFile = (self.path + '/' + port.packageInfoName)
				if (os.path.exists(mainPackageInfoFile)
					and not higherVersionIsActive
					and (os.path.getmtime(port.recipeFilePath)
						 <= os.path.getmtime(mainPackageInfoFile))):
					higherVersionIsActive = True
					break

				# try tp parse updated recipe
				try:
					port.parseRecipeFile(False)

					if higherVersionIsActive:
						# remove package infos from lower version, if it exists
						if os.path.exists(mainPackageInfoFile):
							if not self.quiet:
								print('\tremoving package-infos for ' + portID
									  + ', as newer version is active')
							port.removePackageInfosFromRepository(self.path)
							port.obsoletePackages(self.packagesPath)
							break
						continue

					if not port.isBuildableOnTargetArchitecture():
						touchFile(skippedDir + '/' + portID)
						if not self.quiet:
							status = port.getStatusOnTargetArchitecture()
							print(('\t%s is still marked as %s on target '
								   + 'architecture') % (portID, status))
						continue

					higherVersionIsActive = True
					if os.path.exists(skippedDir + '/' + portID):
						os.remove(skippedDir + '/' + portID)

					if not self.quiet:
						print '\tupdating package infos of ' + portID
					port.writePackageInfosIntoRepository(self.path)

				except SystemExit:
					if not higherVersionIsActive:
						# take notice of broken recipe file
						touchFile(skippedDir + '/' + portID)
						if os.path.exists(mainPackageInfoFile):
							brokenPorts.append(portID)
						else:
							if not self.quiet:
								print '\trecipe for %s is still broken' % portID

		self._removeStalePackageInfos(brokenPorts)

	def _removeStalePackageInfos(self, brokenPorts):
		"""check for any package-infos that no longer have a corresponding
		   recipe file"""

		allPorts = self.getAllPorts()

		if not self.quiet:
			print "Looking for stale package-infos ..."
		packageInfos = glob.glob(self.path + '/*.PackageInfo')
		for packageInfo in packageInfos:
			packageInfoFileName = os.path.basename(packageInfo)
			packageID = packageInfoFileName[:packageInfoFileName.rindex('.')]
			portID = packageID

			# what we have in portID may be a packageID instead, in which case
			# we need to find the corresponding portID.
			if portID not in allPorts:
				portID = self.getPortIdForPackageId(portID)

			if not portID or portID not in allPorts or portID in brokenPorts:
				if not self.quiet:
					print '\tremoving ' + packageInfoFileName
				os.remove(packageInfo)

				# obsolete corresponding package, if any
				self._removePackagesForPackageInfo(packageInfo)

	def _removePackagesForPackageInfo(self, packageInfo):
		"""remove all packages for the given package-info"""

		(packageSpec, unused) = os.path.basename(packageInfo).rsplit('.', 1)
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

	def _partiallyExtractSourcePackageIfNeeded(self, sourcePackageName):
		"""extract the recipe and potentially contained patches/licenses from
		   a source package, unless that has already been done"""

		sourcePackagePath \
			= self.inputSourcePackagesPath + '/' + sourcePackageName
		(name, version, revision, unused) = sourcePackageName.split('-')
		name = name[:-7]	# drop '_source'
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

			# add SRC_URI to recipe which points to the source package
			with open(recipeFilePath, 'a') as recipeFile:
				recipeFile.write('\n# Added by haikuporter:\n')
				recipeFile.write('SRC_URI="pkg:%s"\n' % sourcePackagePath)

		return recipeFilePath
