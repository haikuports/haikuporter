# -*- coding: utf-8 -*-
# copyright 2007-2011 Brecht Machiels
# copyright 2009-2010 Chris Roberts
# copyright 2009-2011 Scott McCreary
# copyright 2009 Alexander Deynichenko
# copyright 2009 HaikuBot (aka RISC)
# copyright 2010-2011 Jack Laxson (Jrabbit)
# copyright 2011 Ingo Weinhold
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

from HaikuPorter.GlobalConfig import (globalConfiguration, 
									  readGlobalConfiguration)
from HaikuPorter.Options import getOption
from HaikuPorter.Port import Port
from HaikuPorter.RecipeTypes import MachineArchitecture, Status
from HaikuPorter.Utils import (check_output, ensureCommandIsAvailable, 
							   naturalCompare, sysExit, touchFile, warn)

import glob
import os
import re
import shutil
from subprocess import check_call
import sys


# -- path to haikuports-tree --------------------------------------------------

haikuportsRepoUrl = 'git@bitbucket.org:haikuports/haikuports.git'


# -- bareVersionCompare -------------------------------------------------------

def bareVersionCompare(left, right):
	"""Compares two given bare versions - returns:
		-1 if left is lower than right
		 1 if left is higher than right
		 0 if both versions are equal"""

	leftElements = left.split('.')
	rightElements = right.split('.')

	index = 0
	leftElementCount = len(leftElements)
	rightElementCount = len(rightElements)
	while True:
		if index + 1 > leftElementCount:
			if index + 1 > rightElementCount:
				return 0
			else:
				return -1
		elif index + 1 > rightElementCount:
			return 1
			
		result = naturalCompare(leftElements[index], rightElements[index])
		if result != 0:
			return result
		
		index += 1
		
# -- versionCompare -----------------------------------------------------------

def versionCompare(left, right):
	"""Compares two given versions that may include a pre-release - returns 
		-1 if left is lower than right
		 1 if left is higher than right
		 0 if both versions are equal"""

	leftElements = left.split('~', 1)
	rightElements = right.split('~', 1)

	result = bareVersionCompare(leftElements[0], rightElements[0])
	if result != 0:
		return result
	
	if len(leftElements) < 2:
		if len(rightElements) < 2:
			return 0
		else:
			return -1
	elif len(rightElements) < 2:
		return 1
	
	# compare pre-release strings
	return naturalCompare(leftElements[1], rightElements[1])


# -- Main Class ---------------------------------------------------------------

class Main:
	def __init__(self, options, args):
		self.options = options
		
		# read global settings
		readGlobalConfiguration()
		
		# set up the global variables we'll inherit to the shell
		self._initGlobalShellVariables()
	
		self.treePath = globalConfiguration['TREE_PATH'].rstrip('/')
		
		# create path where built packages will be collected
		self.packagesPath = self.treePath + '/packages'
		if not os.path.exists(self.packagesPath):
			os.mkdir(self.packagesPath)

		# the path where repository will be built
		self.repositoryPath = self.treePath + '/repository'

		# if requested, list all ports in the HaikuPorts tree
		if self.options.list:
			self._searchPorts(None)
			sys.exit()

		# if requested, search for a port
		if self.options.search:
			if not args:
				sysExit('You need to specify a search string.\n'
						"Invoke '" + sys.argv[0] + " -h' for usage "
						"information.")
			self._searchPorts(args[0])
			sys.exit()
		
		if self.options.location:
			if not args:
				sysExit('You need to specify a search string.\n'
						"Invoke '" + sys.argv[0] + " -h' for usage "
						"information.")
			# Provide the installed location of a port (for quick editing)
			print os.path.join(self.treePath, self.searchPorts(args[0]))
			sys.exit()

		# if requested, checkout or update ports tree
		if self.options.get:
			self._updatePortsTree()
			sys.exit()

		# if requested, print the location of the haikuports source tree
		if self.options.tree:
			print self.treePath
			sys.exit()

		# if requested, scan the ports tree for problems
		if self.options.lint:
			self._checkSourceTree()
			sys.exit()

		# if a ports-file has been given, read port specifications from it
		# and build them all
		self.portSpecs = []
		if self.options.portsfile:
			with open(self.options.portsfile, 'r') as portsFile:
				portSpecs = [ p.strip() for p in portsFile.readlines() ]
			portSpecs = [ p for p in portSpecs if len(p) > 0 ]
			for portSpec in portSpecs:
				self.portSpecs.append(
					self._splitPortSpecIntoNameVersionAndRevision(portSpec))
			if not self.portSpecs:
				sysExit("The given ports-file doesn't contain any ports.")
		else:
			# if there is no argument given, exit
			if not args:
				sysExit('You need to specify a search string.\nInvoke '
						"'" + sys.argv[0] + " -h' for usage information.")
			else:
				self.portSpecs.append(
					self._splitPortSpecIntoNameVersionAndRevision(args[0]))

		# check all port specifiers
		for portSpec in self.portSpecs:
			# find the port in the HaikuPorts tree
			category = self._getCategory(portSpec['name'])
			if category == None:
				sysExit('Port ' + portSpec['name'] + ' not found in tree.')
	
			baseDir = self.treePath + '/' + category + '/' + portSpec['name']
	
			# if the port version was not specified, list available versions
			if portSpec['version'] == None:
				versions = []
				dirList = os.listdir(baseDir)
				for item in dirList:
					if (not item.endswith('.recipe')):
						continue
					portElements = item[:-7].split('-')
					if len(portElements) == 2:
						versions.append(portElements[1])
				if len(versions) > 0:
					print('Following versions of %s are available:' 
						  % portSpec['name'])
					for version in versions:
						print '  ' + version
					sysExit('Please run haikuporter again, specifying a port '
							+ 'version')
				else:
					sysExit('No recipe files for %s found.' % portSpec['name'])
		
		# don't build or package when not patching
		if not self.options.patch:
			self.options.build = False
			self.options.package = False

		# update repository if it exists and isn't empty, populate it otherwise
		if (os.path.isdir(self.repositoryPath) 
			and os.listdir(self.repositoryPath)):
			self._updateRepository()
		else:
			self._populateRepository()
			
		# collect all available ports and validate each specified port
		allPorts = self._getAllPorts()
		for portSpec in self.portSpecs:
			portID = portSpec['name'] + '-' + portSpec['version']
			if portID not in allPorts:
				sysExit(portID + ' not found in tree.')
			port = allPorts[portID]
			portSpec['id'] = portID
			
			# show port description, if requested
			if self.options.about:
				port.printDescription()
			
			self._validateMainPort(port, portSpec['revision'])
			
		# do whatever's needed to the list of ports
		for portSpec in self.portSpecs:
			port = allPorts[portSpec['id']]
			
			if self.options.why:
				# find out about why another port is required
				if self.options.why not in allPorts:
					sysExit(self.options.why + ' not found in tree.')
				requiredPort = allPorts[self.options.why]
				self._validateMainPort(requiredPort)
				port.whyIsPortRequired(self.repositoryPath, self.packagesPath,
									   requiredPort)
				sys.exit(0)

			if self.options.build:
				self._buildMainPort(port)
			else:
				self._buildPort(port, True, self.packagesPath)

			# TODO: reactivate these!
			# if self.options.test:
			#	port.test()

	def _validateMainPort(self, port, revision = None):
		"""Parse the recipe file for the given port and get any required
		   confirmations"""
			
		# read data from the recipe file
		port.parseRecipeFile(True)
		
		# if a specific revision has been given, check if this port matches it
		if revision and port.revision != revision:
			sysExit(("port %s isn't available in revision %s (found revision "
					+ '%s instead)')
					% (port.versionedName, revision, port.revision))

		# warn when the port is not stable on this architecture
		status = port.getStatusOnCurrentArchitecture()
		if status != Status.STABLE:
			warn('This port is %s on this architecture.' % status)
			if not self.options.yes:
				answer = raw_input('Continue (y/n + enter)? ')
				if answer == '':
					sys.exit(1)
				if answer[0].lower() == 'y':
					print ' ok'
				else:
					sys.exit(1)

		if port.recipeKeys['MESSAGE']:
			print port.recipeKeys['MESSAGE']
			if not self.options.yes:
				answer = raw_input('Continue (y/n + enter)? ')
				if answer == '':
					sys.exit(1)
				if answer[0].lower() == 'y':
					print ' ok'
				else:
					sys.exit(1)

	def _buildMainPort(self, port):
		"""Build the given port with all its dependencies"""

		print '=' * 70
		print port.category + '::' + port.versionedName
		print '=' * 70
		
		# HPKGs are usually written into the 'packages' directory, but when
		# an obsolete port (one that's not in the repository) is being built,
		# its packages are stored into the .obsolete subfolder of the packages
		# directory.
		targetPath = self.packagesPath
		packageInfo = self.repositoryPath + '/' + port.packageInfoName
		if not os.path.exists(packageInfo):
			warn('building obsolete package')
			targetPath += '/.obsolete'
			if not os.path.exists(targetPath):
				os.makedirs(targetPath)
			
		(buildDependencies, portRepositoryPath) \
			= port.resolveBuildDependencies(self.repositoryPath,
											self.packagesPath)
		allPorts = self._getAllPorts()
		requiredPortsToBuild = []
		requiredPortIDs = {}
		for dependency in buildDependencies:
			if dependency.startswith(portRepositoryPath):
				packageInfoFileName = os.path.basename(dependency)
				packageID \
					= packageInfoFileName[:packageInfoFileName.rindex('.')]
				try:
					if packageID in allPorts:
						portID = packageID
					else:
						portID = self._getPortIdForPackageId(packageID)
					if portID not in requiredPortIDs:
						requiredPort = allPorts[portID]
						requiredPortsToBuild.append(requiredPort)
						requiredPortIDs[portID] = True
				except KeyError:
					sysExit('Inconsistency: ' + port.versionedName
							 + ' requires ' + packageID 
							 + ' but no corresponding port was found!')

		if requiredPortsToBuild:
			print 'The following required ports will be built first:'
			for requiredPort in requiredPortsToBuild:			
				print('\t' + requiredPort.category + '::' 
					  + requiredPort.versionedName)
			for requiredPort in requiredPortsToBuild:			
				self._buildPort(requiredPort, True, targetPath)
				
		self._buildPort(port, False, targetPath)

	def _buildPort(self, port, parseRecipe, targetPath):
		"""Build a single port"""

		print '-' * 70
		print port.category + '::' + port.versionedName
		print '-' * 70
		
		# pass-on options to port
		port.forceOverride = self.options.force
		port.beQuiet = self.options.quiet
		port.avoidChroot = not self.options.chroot
		
		if parseRecipe:
			port.parseRecipeFile(True)

		# clean the work directory, if requested
		if self.options.clean:
			port.cleanWorkDirectory()

		port.downloadSource()
		port.unpackSource()
		if self.options.patch:
			port.patchSource()

		if self.options.build:
			port.build(self.packagesPath, self.options.package, targetPath)
	

	def _initGlobalShellVariables(self):
		# extract the package info from the system package
		output = check_output('package list /system/packages/haiku.hpkg'
			+ ' | grep -E "^[[:space:]]*[[:alpha:]]+:[[:space:]]+"', 
			shell=True)

		# get the haiku version
		match = re.search(r"provides:\s*haiku\s+=\s*(\S+)", output)
		if not match:
			sysExit('Failed to get Haiku version!')
		self.haikuVersion = match.group(1)

		# get the architecture
		match = re.search(r"architecture:\s*(\S+)", output)
		if not match:
			sysExit('Failed to get Haiku architecture!')
		self.architecture = match.group(1)

		self.shellVariables = {
			'haikuVersion': self.haikuVersion,
			'architecture': self.architecture,
			'jobs': str(self.options.jobs),
		}
		if self.options.jobs > 1:
			self.shellVariables['jobArgs'] = '-j' + str(self.options.jobs)
		if self.options.quiet:
			self.shellVariables['quiet'] = '1'
			
		if globalConfiguration['IS_CROSSBUILD_REPOSITORY']:
			hostMachineTriple \
				= MachineArchitecture.getHostTripleFor(self.architecture)
			self.shellVariables['hostMachineTriple'] = hostMachineTriple
			self.shellVariables['hostMachineTripleAsName'] \
				= hostMachineTriple.replace('-', '_')
			targetArchitecture = getOption('targetArch')
			if not targetArchitecture:
				if 'TARGET_ARCHITECTURE' in globalConfiguration:
					targetArchitecture \
						= globalConfiguration['TARGET_ARCHITECTURE']
			if not targetArchitecture:
				sysExit('A cross-build repository is active, '
						'you must specify a target architecture.\n'
						'Please use --target-arch '
						'or set TARGET_ARCHITECTURE in haikuports.conf')
			targetArchitecture = targetArchitecture.lower()
			self.shellVariables['targetArchitecture'] = targetArchitecture
			targetMachineTriple \
				= MachineArchitecture.getTargetTripleFor(targetArchitecture)
			self.shellVariables['targetMachineTriple'] = targetMachineTriple
			self.shellVariables['targetMachineTripleAsName'] \
				= targetMachineTriple.replace('-', '_')

	def _updatePortsTree(self):
		"""Get/Update the port tree via svn"""
		print 'Refreshing the port tree: %s' % self.treePath
		ensureCommandIsAvailable('git')
		if os.path.exists(self.treePath + '/.git'):
			check_call(['git', 'pull'], cwd = self.treePath)
		else:
			check_call(['git', 'clone', haikuportsRepoUrl, self.treePath])

	def _searchPorts(self, regExp):
		"""Search for a port in the HaikuPorts tree"""
		if regExp:
			reSearch = re.compile(regExp)
		os.chdir(self.treePath)
		dirList = os.listdir(self.treePath)
		for category in dirList:
			if os.path.isdir(category) and category[0] != '.':
				subdirList = os.listdir(category)
				# remove items starting with '.'
				subdirList.sort()
				for portName in subdirList:
					if (portName[0][0] != '.' 
						and (not regExp or reSearch.search(portName))):
						print category + '/' + portName

	def _splitPortSpecIntoNameVersionAndRevision(self, portSpecString):
		elements = portSpecString.split('-')
		if len(elements) < 1 or len(elements) > 3:
			sysExit('Invalid port specifier ' + portSpecString)
		
		return  { 
			'specifier': portSpecString, 
			'name': elements[0],
			'version': elements[1] if len(elements) > 1 else None,
			'revision': elements[2] if len(elements) > 2 else None,
		}

	def _getCategory(self, portName):
		"""Find location of the specified port in the HaikuPorts tree"""
		hierarchy = []
		os.chdir(self.treePath)
		dirList = os.listdir(self.treePath)
		for item in dirList:
			if os.path.isdir(item) and item[0] != '.' and '-' in item:
				subdirList = os.listdir(item)
				# remove items starting with '.'
				subdirList.sort()
				while subdirList[0][0] == '.':
					del subdirList[0]

				# locate port
				try:
					if subdirList.index(portName) >= 0:
						# port was found in the category specified by 'item'
						return item
				except ValueError:
					pass
				hierarchy.append([item, subdirList])
		return None

	def _checkSourceTree(self):
		print 'Checking HaikuPorts tree at: ' + self.treePath

		allPorts = self._getAllPorts()
		for portName in sorted(self._portVersionsByName.keys(), key=str.lower):
			for version in self._portVersionsByName[portName]:
				portID = portName + '-' + version
				port = allPorts[portID]
				print '%s   [%s]' % (portID, port.category)
				try:
					port.validateRecipeFile(True)
				except SystemExit as e:
					print e.code

	def _populateRepository(self):
		"""Remove and refill the repository with all PackageInfo-files from
		   parseable recipes"""

		if os.path.exists(self.repositoryPath):
			shutil.rmtree(self.repositoryPath)
		newRepositoryPath = self.repositoryPath + '.new'
		if os.path.exists(newRepositoryPath):
			shutil.rmtree(newRepositoryPath)
		os.mkdir(newRepositoryPath)
		skippedDir = newRepositoryPath + '/.skipped'
		os.mkdir(skippedDir)
		print 'Populating repository ...'

		allPorts = self._getAllPorts()
		for portName in sorted(self._portVersionsByName.keys(), key=str.lower):
			for version in reversed(self._portVersionsByName[portName]):
				portID = portName + '-' + version
				port = allPorts[portID]
				try:
					sys.stdout.write(' ' * 60)
					sys.stdout.write('\r\t%s' % port.versionedName)
					sys.stdout.flush()
					port.parseRecipeFile(False)
					status = port.getStatusOnCurrentArchitecture()
					if status == Status.STABLE:
						if (port.checkFlag('build') 
							and not self.options.preserveFlags):
							print '   [build-flag reset]'
							port.unsetFlag('build')
						else:
							print
						port.writePackageInfosIntoRepository(newRepositoryPath)
						break
					else:
						# take notice of skipped recipe file
						touchFile(skippedDir + '/' + portID)
						print(' is skipped, as it is %s on this architecture'
							  % status)
				except SystemExit:
					# take notice of broken recipe file
					touchFile(skippedDir + '/' + portID)
					sys.stdout.write('\r')
					pass
		os.rename(newRepositoryPath, self.repositoryPath)

	def _updateRepository(self):
		"""Update all PackageInfo-files in the repository as needed"""
		
		allPorts = self._getAllPorts()
		
		brokenPorts = []

		# check for all known ports if their recipe has been changed
		print 'Checking if any package-infos need to be updated ...'
		skippedDir = self.repositoryPath + '/.skipped'
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
				mainPackageInfoFile = (self.repositoryPath + '/' 
									   + port.packageInfoName)
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
							print('\tremoving package-infos for ' + portID
								  + ', as newer version is active')
							port.removePackageInfosFromRepository(
								self.repositoryPath)
							port.obsoletePackages(self.packagesPath)
							break
						continue
					
					status = port.getStatusOnCurrentArchitecture()
					if status != Status.STABLE:
						touchFile(skippedDir + '/' + portID)
						print('\t%s is still marked as %s on this architecture' 
							  % (portID, status))
						continue

					higherVersionIsActive = True
					if os.path.exists(skippedDir + '/' + portID):
						os.remove(skippedDir + '/' + portID)
						
					print '\tupdating package infos of ' + portID
					port.writePackageInfosIntoRepository(self.repositoryPath)
					
				except SystemExit:
					if not higherVersionIsActive:
						# take notice of broken recipe file
						touchFile(skippedDir + '/' + portID)
						if os.path.exists(mainPackageInfoFile):
							brokenPorts.append(portID)
						else:
							print '\trecipe for %s is still broken' % portID

		self._removeStalePackageInfos(brokenPorts)

	def _removeStalePackageInfos(self, brokenPorts):
		"""check for any package-infos that no longer have a corresponding
		   recipe file"""
		
		allPorts = self._getAllPorts()

		print "Looking for stale package-infos ..."
		packageInfos = glob.glob(self.repositoryPath + '/*.PackageInfo')
		for packageInfo in packageInfos:
			packageInfoFileName = os.path.basename(packageInfo)
			packageID = packageInfoFileName[:packageInfoFileName.rindex('.')]
			portID = packageID

			# what we have in portID may be a packageID instead, in which case
			# we need to find the corresponding portID.
			if portID not in allPorts:
				portID = self._getPortIdForPackageId(portID)
			
			if not portID or portID not in allPorts or portID in brokenPorts:
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
			print '\tobsoleting package ' + packageFileName
			obsoletePackage = obsoleteDir + '/' + packageFileName
			if not os.path.exists(obsoleteDir):
				os.mkdir(obsoleteDir)
			os.rename(package, obsoletePackage)

	def _getPortIdForPackageId(self, packageId):
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

	def _getAllPorts(self):
		if hasattr(self, '_allPorts'):
			return self._allPorts

		# For now, we collect all ports into a dictionary that can be keyed
		# by name + '-' + version. Additionally, we keep a sorted list of 
		# available versions for each port name.
		self._allPorts = {}
		self._portVersionsByName = {}
		for category in sorted(os.listdir(self.treePath)):
			categoryPath = self.treePath + '/' + category
			if (not os.path.isdir(categoryPath) or category[0] == '.'
				or '-' not in category):
				continue
			for port in sorted(os.listdir(categoryPath)):
				portPath = categoryPath + '/' + port
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
						if name not in self._portVersionsByName:
							self._portVersionsByName[name] = [ version ]
						else:
							self._portVersionsByName[name].append(version)
						self._allPorts[name + '-' + version] \
							= Port(name, version, category, portPath, 
								   self.shellVariables)
					else:
						# invalid argument
						print("Warning: Couldn't parse port/version info: " 
							  + recipe)

		# Sort version list of each port
		for portName in self._portVersionsByName.keys():
			self._portVersionsByName[portName].sort(cmp=versionCompare)

		return self._allPorts
