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

from HaikuPorter.BuildPlatform import buildPlatform
from HaikuPorter.Configuration import Configuration
from HaikuPorter.DependencyAnalyzer import DependencyAnalyzer
from HaikuPorter.PackageInfo import PackageInfo
from HaikuPorter.Policy import Policy
from HaikuPorter.RecipeTypes import MachineArchitecture, Status
from HaikuPorter.Repository import Repository
from HaikuPorter.Utils import (check_output, ensureCommandIsAvailable,
							   haikuportsRepoUrl, sysExit, warn)

import os
import re
from subprocess import check_call
import sys


# -- Main Class ---------------------------------------------------------------

class Main(object):
	def __init__(self, options, args):
		self.options = options

		self.policy = Policy(self.options.strictPolicy)

		self.repository = None

		# read global settings
		Configuration.init()

		self.treePath = Configuration.getTreePath()

		# init build platform
		buildPlatform.init(self.treePath)

		# set up the global variables we'll inherit to the shell
		self._initGlobalShellVariables()

		# create path where built packages will be collected
		self.packagesPath = self.treePath + '/packages'
		if not os.path.exists(self.packagesPath):
			os.mkdir(self.packagesPath)

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

		# if requested, list all ports in the HaikuPorts tree
		if self.options.list:
			self._createRepositoryIfNeeded(True)
			allPortNames = self.repository.searchPorts(None)
			for portName in allPortNames:
				print portName
			sys.exit()

		# if requested, search for a port
		if self.options.search:
			if not args:
				sysExit('You need to specify a search string.\n'
						"Invoke '" + sys.argv[0] + " -h' for usage "
						"information.")
			self._createRepositoryIfNeeded(True)
			portNames = self.repository.searchPorts(args[0])
			for portName in portNames:
				print portName
			sys.exit()

		if self.options.location:
			if not args:
				sysExit('You need to specify a search string.\n'
						"Invoke '" + sys.argv[0] + " -h' for usage "
						"information.")
			# Provide the installed location of a port (for quick editing)
			self._createRepositoryIfNeeded(True)
			portNames = self.repository.searchPorts(args[0])
			for portName in portNames:
				print os.path.join(self.treePath, portName)
			sys.exit()

		self._createRepositoryIfNeeded()

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
		elif self.options.analyzeDependencies:
			pass
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

		if self.options.analyzeDependencies:
			DependencyAnalyzer(self.repository)
			return

		# collect all available ports and validate each specified port
		allPorts = self.repository.getAllPorts()
		portVersionsByName = self.repository.getPortVersionsByName()
		for portSpec in self.portSpecs:

			# validate name of port
			if portSpec['name'] not in portVersionsByName:
				if not Configuration.isCrossBuildRepository():
					sysExit(portSpec['name'] + ' not found in repository')
				# for cross-build repository, try with target arch added
				nameWithTargetArch \
					= (portSpec['name'] + '_'
					   + self.shellVariables['targetArchitecture'])
				if nameWithTargetArch not in portVersionsByName:
					sysExit(portSpec['name'] + ' not found in repository')
				portSpec['name'] = nameWithTargetArch

			# use specific version if given, otherwise try with all available
			# versions
			versions = []
			if portSpec['version']:
				versions.append(portSpec['version'])
			else:
				versions = portVersionsByName[portSpec['name']]

			# try to find a version of the current port that is buildable
			for version in versions:
				portID = portSpec['name'] + '-' + version
				if portID not in allPorts:
					sysExit(portID + ' not found in tree.')
				port = allPorts[portID]
				status = port.getStatusOnTargetArchitecture()
				if (status != Status.STABLE
					and (status != Status.UNTESTED
						or not Configuration.shallAllowUntested())):
					warn('skipping %s, as it is %s on the target architecture.'
						 % (portID, status))
					continue

				# notice ID of buildable port version
				portSpec['id'] = portID
				break
			else:
				if portSpec['version']:
					sysExit(portSpec['name'] + '-' + portSpec['version']
							+ " can't be built")
				else:
					sysExit('No version of ' + portSpec['name']
							+ ' can be built')

			# show port description, if requested
			if self.options.about:
				try:
					port.parseRecipeFile(False)
				except:
					pass
				port.printDescription()
				sys.exit(0)

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
				port.whyIsPortRequired(self.repository.path, self.packagesPath,
									   requiredPort)
				sys.exit(0)

			if self.options.build:
				self._buildMainPort(port)
			elif self.options.extractPatchset:
				port.extractPatchset()
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
		status = port.getStatusOnTargetArchitecture()
		if (status != Status.STABLE
			and (status != Status.UNTESTED
				 or not Configuration.shallAllowUntested())):
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
		packageInfo = self.repository.path + '/' + port.packageInfoName
		if not os.path.exists(packageInfo):
			warn('building obsolete package')
			targetPath += '/.obsolete'
			if not os.path.exists(targetPath):
				os.makedirs(targetPath)

		(buildDependencies, portRepositoryPath) \
			= port.resolveBuildDependencies(self.repository.path,
											self.packagesPath)
		allPorts = self.repository.getAllPorts()
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
						portID \
							= self.repository.getPortIdForPackageId(packageID)
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
		# get the target haiku version and architecture
		targetArchitecture = buildPlatform.getTargetArchitecture()
		if Configuration.isCrossBuildRepository():
			targetHaikuPackage = Configuration.getCrossDevelPackage()
			if not targetHaikuPackage:
				if not buildPlatform.isHaiku():
					sysExit('On this platform a haiku cross devel package must '
			 			'be specified (via --cross-devel-package)')
				targetHaikuPackage = ('/boot/system/develop/cross/'
					+ 'haiku_cross_devel_sysroot_%s.hpkg') % targetArchitecture

			targetHaikuPackageInfo = PackageInfo(targetHaikuPackage)
			targetHaikuVersion = targetHaikuPackageInfo.getVersion()
		else:
			if not buildPlatform.isHaiku():
				sysExit('Native building not supported on this platform (%s)'
					% buildPlatform.getName())
			targetHaikuVersion = buildPlatform.getHaikuVersion()

		self.shellVariables = {
			'haikuVersion': targetHaikuVersion,
			'buildArchitecture': buildPlatform.getArchitecture(),
			'targetArchitecture': targetArchitecture,
			'jobs': str(self.options.jobs),
		}
		if self.options.jobs > 1:
			self.shellVariables['jobArgs'] = '-j' + str(self.options.jobs)
		if self.options.quiet:
			self.shellVariables['quiet'] = '1'

		if Configuration.isCrossBuildRepository():
			self.shellVariables['isCrossRepository'] = 'true';

			buildMachineTriple = buildPlatform.getMachineTriple()
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

	def _createRepositoryIfNeeded(self, quiet = False):
		"""create/update repository"""
		if self.repository:
			return
		self.repository = Repository(self.treePath, self.packagesPath,
			self.shellVariables, self.policy, self.options.preserveFlags, quiet)

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

		allPorts = self.repository.getAllPorts()
		portVersionsByName = self.repository.getPortVersionsByName()
		for portName in sorted(portVersionsByName.keys(), key=str.lower):
			for version in portVersionsByName[portName]:
				portID = portName + '-' + version
				port = allPorts[portID]
				print '%s   [%s]' % (portID, port.category)
				try:
					port.validateRecipeFile(True)
				except SystemExit as e:
					print e.code
