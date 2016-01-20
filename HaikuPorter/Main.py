# -*- coding: utf-8 -*-
#
# Copyright 2007-2011 Brecht Machiels
# Copyright 2009-2010 Chris Roberts
# Copyright 2009-2011 Scott McCreary
# Copyright 2009 Alexander Deynichenko
# Copyright 2009 HaikuBot (aka RISC)
# Copyright 2010-2011 Jack Laxson (Jrabbit)
# Copyright 2011 Ingo Weinhold
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .BuildPlatform import buildPlatform
from .Configuration import Configuration
from .DependencyAnalyzer import DependencyAnalyzer
from .Options import getOption
from .Policy import Policy
from .RecipeAttributes import getRecipeFormatVersion
from .RecipeTypes import MachineArchitecture
from .Repository import Repository
from .Utils import ensureCommandIsAvailable, haikuportsRepoUrl, sysExit, warn

import os
import re
from subprocess import check_call
import sys
import traceback

# -- Main Class ---------------------------------------------------------------

class Main(object):
	def __init__(self, options, args):
		self.options = options
		try:
			self.run(args)
		except BaseException as exception:
			if getOption('debug'):
				traceback.print_exc()
			elif type(exception).__name__ == "SystemExit":
				if type(exception.code).__name__ != "int":
					print exception.code
			else:
				print exception
			exit(1)

	def run(self, args):
		self.policy = Policy(self.options.strictPolicy)

		self.repository = None

		# read global settings
		Configuration.init()

		self.treePath = Configuration.getTreePath()
		self.outputDirectory = Configuration.getOutputDirectory()

		self._checkFormatVersions()

		# determine if haikuporter has just been invoked for a short-term
		# command
		self.shallowInitIsEnough = (self.options.lint or self.options.tree
									or self.options.get or self.options.list
									or self.options.search
									or self.options.location)

		# init build platform
		buildPlatform.init(self.treePath, self.outputDirectory,
						   self.shallowInitIsEnough)

		# set up the global variables we'll inherit to the shell
		self._initGlobalShellVariables()

		# create path where built packages will be collected
		self.packagesPath = self.outputDirectory + '/packages'
		if not os.path.exists(self.packagesPath):
			os.mkdir(self.packagesPath)

		# if requested, checkout or update ports tree
		if self.options.get:
			self._updatePortsTree()
			return

		# if requested, print the location of the haikuports source tree
		if self.options.tree:
			print self.treePath
			return

		# if requested, scan the ports tree for problems
		if self.options.lint:
			if (not buildPlatform.isHaiku
				and Configuration.getLicensesDirectory() == None):
				sysExit('LICENSES_DIRECTORY must be set in configuration on '
					'this build platform!')
			self._createRepositoryIfNeeded(True)
			if not args:
				self._checkSourceTree("")
			else:
				self._checkSourceTree(args[0])
			return

		# if requested, list all ports in the HaikuPorts tree
		if self.options.list:
			self._createRepositoryIfNeeded(True)
			allPortNames = self.repository.searchPorts(None)
			for portName in sorted(allPortNames):
				print portName
			return

		# if requested, search for a port
		if self.options.search:
			if not args:
				sysExit('You need to specify a search string.\n'
						"Invoke '" + sys.argv[0] + " -h' for usage "
						"information.")
			self._createRepositoryIfNeeded(True)
			portNames = self.repository.searchPorts(args[0])
			for portName in portNames:
				versions = self.repository.portVersionsByName[portName]
				portID = portName + '-' + versions[0]
				port = self.repository.allPorts[portID]
				print port.category + '::' + portName
			return

		if self.options.location:
			if not args:
				sysExit('You need to specify a search string.\n'
						"Invoke '" + sys.argv[0] + " -h' for usage "
						"information.")
			# Provide the installed location of a port (for quick editing)
			self._createRepositoryIfNeeded(True)
			portNames = self.repository.searchPorts(args[0])
			for portName in portNames:
				versions = self.repository.portVersionsByName[portName]
				portID = portName + '-' + versions[0]
				port = self.repository.allPorts[portID]
				print os.path.join(self.treePath, port.category, portName)
			return

		if self.options.portsfile:
			# read portslist from file and convert into list of requires
			with open(self.options.portsfile, 'r') as portsFile:
				ports = [ p.strip() for p in portsFile.readlines() ]
			ports = [ p for p in ports if len(p) > 0 ]
			portsfileAsRequires = []
			for port in ports:
				portSpec = self._splitPortSpecIntoNameVersionAndRevision(port)
				if portSpec['version']:
					portsfileAsRequires.append(portSpec['name'] + ' =='
											   + portSpec['version'])
				else:
					portsfileAsRequires.append(portSpec['name'])
			if not portsfileAsRequires:
				sysExit("The given ports-file doesn't contain any ports.")
			self.shellVariables['portsfileAsRequires'] \
				= '\n'.join(portsfileAsRequires)

		self._createRepositoryIfNeeded(self.options.quiet, self.options.verbose)

		if self.options.analyzeDependencies:
			DependencyAnalyzer(self.repository).printDependencies()
			return

		bootstrapPorts = set()

		# if a ports-file has been given, read port specifications from it
		# and build them all (as faked requires of a specific meta port, such
		# that their runtime requires get pulled in, too)
		self.portSpecs = []
		self.builtPortIDs = set()
		if self.options.portsfile:
			# pretend the meta port responsible for building a list of ports
			# has been specified on the cmdline
			metaPortSpec = 'meta_portsfile-1'
			if not metaPortSpec in self.repository.allPorts:
				sysExit("no recipe found for '%s'" % metaPortSpec)
			self.portSpecs.append(
				self._splitPortSpecIntoNameVersionAndRevision(metaPortSpec))
		elif self.options.doBootstrap:
			# first untangle and build all ports with circular dependencies
			dependencyAnalyzer = DependencyAnalyzer(self.repository)
			portsToBuild = dependencyAnalyzer.getBuildOrderForBootstrap()
			print 'Untangling the ports with circular dependencies gave this:'
			print "	 " + "\n  ".join(portsToBuild)
			print 'After that, all other available ports will be built, too'
			portsNotYetBuilt = []
			for portId in portsToBuild:
				port = self.repository.allPorts[portId]
				mainPackage = port.mainPackage
				if (mainPackage
					and os.path.exists(
						self.packagesPath + '/' + mainPackage.hpkgName)):
					print('skipping port %s, since its main package already '
						'exists' % portId)
					continue
				portsNotYetBuilt.append(portId)
				bootstrapPorts.add(portId)
			# add all other ports, such that all available ports will be built
			for portId in self.repository.allPorts.keys():
				if not portId in bootstrapPorts:
					port = self.repository.allPorts[portId]
					mainPackage = port.mainPackage
					if (mainPackage
						and os.path.exists(
							self.packagesPath + '/' + mainPackage.hpkgName)):
						print('skipping port %s, since its main package '
							'already exists' % portId)
						continue
					portsNotYetBuilt.append(portId)
			# add all ports as if they were given on the cmdline
			self.portSpecs = [
				self._splitPortSpecIntoNameVersionAndRevision(port)
				for port in portsNotYetBuilt
			]
		else:
			# if there is no argument given, exit
			if not args:
				sysExit('You need to specify a search string.\nInvoke '
						"'" + sys.argv[0] + " -h' for usage information.")
			self.portSpecs.append(
				self._splitPortSpecIntoNameVersionAndRevision(args[0]))

		# don't build or package when not patching
		if not self.options.patch:
			self.options.build = False
			self.options.package = False

		# collect all available ports and validate each specified port
		allPorts = self.repository.allPorts
		portVersionsByName = self.repository.portVersionsByName
		for portSpec in self.portSpecs:

			# validate name of port
			portName = portSpec['name']
			if portName not in portVersionsByName:
				# for cross-build repository, try with target arch added
				portNameFound = False
				if Configuration.isCrossBuildRepository():
					nameWithTargetArch \
						= (portName + '_'
						+ self.shellVariables['targetArchitecture'])
					if nameWithTargetArch in portVersionsByName:
						portName = nameWithTargetArch
						portNameFound = True

				# it might actually be a package name
				if not portNameFound:
					portName = self.repository.getPortNameForPackageName(
						portName)
					if not portName:
						sysExit(portSpec['name'] + ' not found in repository')
				portSpec['name'] = portName

			# use specific version if given, otherwise use the highest buildable
			# version
			if portSpec['version']:
				portID = portSpec['name'] + '-' + portSpec['version']
			else:
				version = self.repository.getActiveVersionOf(portSpec['name'],
															 True)
				if not version:
					sysExit('No version of ' + portSpec['name']
							+ ' can be built')
				portID = portSpec['name'] + '-' + version

			if portID not in allPorts:
				sysExit(portID + ' not found in tree.')
			port = allPorts[portID]
			portSpec['id'] = portID

			# show port description, if requested
			if self.options.about:
				try:
					port.parseRecipeFile(False)
				except:
					pass
				port.printDescription()
				return

			self._validateMainPort(port, portSpec['revision'])

		if self.options.why:
			# find out about why another port is required
			port = allPorts[self.portSpecs[0]['id']]
			whySpec = self._splitPortSpecIntoNameVersionAndRevision(
				self.options.why)
			if not whySpec['version']:
				whySpec['version'] \
					= self.repository.getActiveVersionOf(whySpec['name'],
														 False)
			whyID = whySpec['name'] + '-' + whySpec['version']
			if not whyID in allPorts:
				sysExit(whyID + ' not found in tree.')
			requiredPort = allPorts[whyID]
			self._validateMainPort(requiredPort)
			port.whyIsPortRequired(self.repository.path, self.packagesPath,
								   requiredPort)
			return

		if self.options.getDependencies:
			self.options.noDependencies = True

		# do whatever's needed to the list of ports
		for portSpec in self.portSpecs:
			port = allPorts[portSpec['id']]

			if self.options.clean:
				port.cleanWorkDirectory()
			elif self.options.test:
				self._testPort(port)
			elif (self.options.build and not portSpec['id'] in bootstrapPorts
				and not self.options.noDependencies):
				self._buildMainPort(port)
			elif self.options.extractPatchset:
				port.extractPatchset()
			else:
				self._buildPort(port, True, self.packagesPath)

		# show summary of policy violations
		if Policy.violationsByPort:
			print 'Summary of policy violations in this session:'
			for portName in sorted(Policy.violationsByPort.keys()):
				print 'Policy violations of %s:' + portName
				for violation in Policy.violationsByPort[portName]:
					print '\t' + violation

	def _validateMainPort(self, port, revision = None):
		"""Parse the recipe file for the given port and get any required
		   confirmations"""

		# read data from the recipe file
		port.parseRecipeFile(True)

		# if a specific revision has been given, check if this port matches it
		if revision and port.revision != revision:
			sysExit(("Port %s isn't available in revision %s (found revision "
					+ '%s instead)')
					% (port.versionedName, revision, port.revision))

		# warn when the port is not buildable on this architecture
		if not port.isBuildableOnTargetArchitecture:
			status = port.statusOnTargetArchitecture
			warn('Port %s is %s on this architecture.'
				 % (port.versionedName, status))
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

		if port.versionedName in self.builtPortIDs:
			return

		print '=' * 70
		print port.category + '::' + port.versionedName
		print '=' * 70

		allPorts = self.repository.allPorts

		# make sure the correct dependencyInfo-file has been created
		self.repository.supportBackwardsCompatibility(port.name, port.version)

		# HPKGs are usually written into the 'packages' directory, but when
		# an obsolete port (one that's not in the repository) is being built,
		# its packages are stored into the .obsolete subfolder of the packages
		# directory.
		targetPath = self.packagesPath
		activeVersion = self.repository.getActiveVersionOf(port.name)
		if port.version != activeVersion:
			warn('building obsolete package')
			targetPath += '/.obsolete'
			if not os.path.exists(targetPath):
				os.makedirs(targetPath)

		buildDependencies = port.resolveBuildDependencies(self.repository.path,
														  self.packagesPath)
		requiredPortsToBuild = []
		requiredPortIDs = set()
		for dependency in buildDependencies:
			packageInfoFileName = os.path.basename(dependency)
			packageID = packageInfoFileName[:packageInfoFileName.rindex('.')]
			try:
				portID = self.repository.getPortIdForPackageId(packageID)
				if portID not in requiredPortIDs:
					requiredPort = allPorts[portID]
					if ((getOption('createSourcePackagesForBootstrap')
							or getOption('createSourcePackages'))
						and (not requiredPort.sourcePackage
							or requiredPort.sourcePackageExists(targetPath))):
						continue
					requiredPortsToBuild.append(requiredPort)
					requiredPortIDs.add(portID)
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

		if port.versionedName in self.builtPortIDs:
			return

		# make sure the correct dependencyInfo-file has been created
		self.repository.supportBackwardsCompatibility(port.name, port.version)

		print '-' * 70
		print port.category + '::' + port.versionedName
		print '\t' + port.recipeFilePath
		print '-' * 70

		# pass-on options to port
		port.forceOverride = self.options.force
		port.beQuiet = self.options.quiet
		port.avoidChroot = not self.options.chroot

		if parseRecipe:
			port.parseRecipeFile(True)

		if not port.isMetaPort:
			port.downloadSource()
			port.unpackSource()
			if self.options.patch:
				port.patchSource()

		if self.options.build:
			port.build(self.packagesPath, self.options.package, targetPath)

		self.builtPortIDs.add(port.versionedName)

	def _testPort(self, port):
		"""Build a single port"""

		if not port.checkFlag('build'):
			sysExit('Please build the port first.')

		print '-' * 70
		print 'TESTING ' + port.category + '::' + port.versionedName
		print '-' * 70

		# pass-on options to port
		port.beQuiet = self.options.quiet

		port.test(self.packagesPath)

	def _initGlobalShellVariables(self):
		# get the target haiku version and architecture
		targetArchitecture = buildPlatform.targetArchitecture
		if Configuration.isCrossBuildRepository():
			targetHaikuPackage = Configuration.getCrossDevelPackage()
			if not targetHaikuPackage:
				if not buildPlatform.isHaiku:
					sysExit('On this platform a haiku cross devel package '
						'must be specified (via --cross-devel-package)')
				targetHaikuPackage = ('/boot/system/develop/cross/'
					+ 'haiku_cross_devel_sysroot_%s.hpkg') \
					% targetArchitecture
		else:
			if (not buildPlatform.isHaiku and not self.shallowInitIsEnough
				and not (getOption('createSourcePackagesForBootstrap')
					or getOption('createSourcePackages'))):
				sysExit('Native building not supported on this platform '
					'(%s)' % buildPlatform.name)

		self.shellVariables = {
			'haikuVersion': 'r1~alpha1',	# just a dummy value for compatibility with old recipes
			'buildArchitecture': buildPlatform.architecture,
			'targetArchitecture': targetArchitecture,
			'jobs': str(self.options.jobs),
		}
		if self.options.jobs > 1:
			self.shellVariables['jobArgs'] = '-j' + str(self.options.jobs)
		if self.options.quiet:
			self.shellVariables['quiet'] = '1'

		if Configuration.isCrossBuildRepository():
			self.shellVariables['isCrossRepository'] = 'true';

			buildMachineTriple = buildPlatform.machineTriple
			targetMachineTriple \
				= MachineArchitecture.getTripleFor(targetArchitecture)

			# If build- and target machine triple are the same, force a
			# cross-build by faking the build-machine triple as something
			# different (which is still being treated identically by the actual
			# build process).
			if buildMachineTriple == targetMachineTriple:
				buildMachineTriple += '_build'

			self.shellVariables['buildMachineTriple'] = buildMachineTriple
			self.shellVariables['buildMachineTripleAsName'] \
				= buildMachineTriple.replace('-', '_')
			self.shellVariables['targetArchitecture'] = targetArchitecture
			self.shellVariables['targetMachineTriple'] = targetMachineTriple
			self.shellVariables['targetMachineTripleAsName'] \
				= targetMachineTriple.replace('-', '_')
		else:
			self.shellVariables['isCrossRepository'] = 'false'

	def _createRepositoryIfNeeded(self, quiet = False, verbose = False):
		"""create/update repository"""
		if self.repository:
			return
		self.repository = Repository(self.treePath, self.outputDirectory,
			self.packagesPath, self.shellVariables, self.policy,
			self.options.preserveFlags, quiet, verbose)

	def _updatePortsTree(self):
		"""Get/Update the port tree via svn"""
		print 'Refreshing the port tree: %s' % self.treePath
		ensureCommandIsAvailable('git')
		if os.path.exists(self.treePath + '/.git'):
			check_call(['git', 'pull'], cwd = self.treePath)
		else:
			check_call(['git', 'clone', haikuportsRepoUrl, self.treePath])

	def _splitPortSpecIntoNameVersionAndRevision(self, portSpecString):
		elements = portSpecString.split('-')
		if len(elements) < 1 or len(elements) > 3:
			sysExit('Invalid port specifier ' + portSpecString)

		return	{
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

	def _checkSourceTree(self, portArgument):
		if portArgument:
			print 'Checking ports of: ' + portArgument

			allPorts = self.repository.allPorts
			portVersionsByName = self.repository.portVersionsByName

			if portArgument in allPorts:
				# Full port name / ver
				port = allPorts[portArgument]
				print '%s	[%s]' % (portArgument, port.category)
				port.validateRecipeFile(True) # exit 1 if fail
				return
			elif portArgument in portVersionsByName:
				# Base port name
				somethingFailed = False
				for version in portVersionsByName[portArgument]:
					portID = portArgument + '-' + version
					port = allPorts[portID]
					print '%s	[%s]' % (portID, port.category)
					try:
						port.validateRecipeFile(True)
					except SystemExit as e:
						somethingFailed = True
						print e.code
				if somethingFailed:
					sys.exit(1)
			else:
				# Unknown
				sysExit('%s is not a known port!' % portArgument)

		else:
			print 'Checking HaikuPorts tree at: ' + self.treePath
			allPorts = self.repository.allPorts
			portVersionsByName = self.repository.portVersionsByName
			somethingFailed = False
			for portName in sorted(portVersionsByName.keys(), key=str.lower):
				for version in portVersionsByName[portName]:
					portID = portName + '-' + version
					port = allPorts[portID]
					print '%s	[%s]' % (portID, port.category)
					try:
						port.validateRecipeFile(True)
					except SystemExit as e:
						print e.code
						somethingFailed = True
			if somethingFailed:
				sys.exit(1)

	def _checkFormatVersions(self):
		# Read the format versions used by the tree and stop if they don't
		# match the ones supported by this instance of haikuporter.
		formatVersionsFile = self.treePath + '/FormatVersions'
		recipeFormatVersion = 0
		if os.path.exists(formatVersionsFile):
			with open(formatVersionsFile, 'r') as f:
				formatVersions = f.read()
			recipeFormatVersionMatch = re.search('^RecipeFormatVersion=(.+?)$',
												 formatVersions,
												 flags=re.MULTILINE)
			if recipeFormatVersionMatch:
				try:
					recipeFormatVersion = int(recipeFormatVersionMatch.group(1))
				except ValueError:
					pass

		if recipeFormatVersion > getRecipeFormatVersion():
			sysExit('The version of the recipe file format used in the ports '
					'tree is newer than the one supported by haikuporter.\n'
					'Please upgrade haikuporter.')
		if recipeFormatVersion < getRecipeFormatVersion():
			sysExit('The version of the recipe file format used in the ports '
					'tree is older than the one supported by haikuporter.\n'
					'Please upgrade the ports tree.')
