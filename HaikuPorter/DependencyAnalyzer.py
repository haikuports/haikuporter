# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.BuildPlatform import buildPlatform
from HaikuPorter.Configuration import Configuration
from HaikuPorter.ShellScriptlets import getScriptletPrerequirements
from HaikuPorter.Utils import (check_output, sysExit)

import glob
import os
import shutil
from subprocess import check_call, CalledProcessError

# -----------------------------------------------------------------------------

requiresDummyPackageInfo = r'''
name			_dummy_
version			1-1
architecture	any
summary			"dummy"
description		"dummy"
packager		"dummy <dummy@dummy.dummy>"
vendor			"Haiku Project"
licenses		"MIT"
copyrights		"none"
provides {
	_dummy_ = 1-1
}
requires {
	%s
}
'''

# -- PortNode class ------------------------------------------------------------

class PortNode(object):
	def __init__(self, portID, port):
		self.portID = portID
		self.port = port
		self.areDependenciesResolved = False
		self.packageNodes = set()
		self.requires = set()
		self.buildRequires = set()
		self.buildPrerequires = set()
		self.indegree = 0
		self.outdegree = 0

	def getName(self):
		return self.portID

	def getDependencies(self):
		return self.buildRequires | self.buildPrerequires

	def isPort(self):
		return True

	def doesBuildDependOnSelf(self):
		return not (self.buildRequires.isdisjoint(self.packageNodes)
			and self.buildPrerequires.isdisjoint(self.packageNodes))

	def addBuildRequires(self, elements):
		self.buildRequires |= elements

	def addBuildPrerequires(self, elements):
		self.buildPrerequires |= elements

	def isBuildable(self, packageInfoPath, doneRepositoryPath):
		# check prerequires
		requiresTypes = [ 'BUILD_PREREQUIRES', 'SCRIPTLET_PREREQUIRES' ]
		packageInfoFiles = self.port.generatePackageInfoFiles(requiresTypes,
															  packageInfoPath)
		args = ([ '/bin/pkgman', 'resolve-dependencies' ] + packageInfoFiles
				+ [
					doneRepositoryPath,
					buildPlatform.findDirectory('B_COMMON_PACKAGES_DIRECTORY'),
					buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'),
				])
		try:
			with open(os.devnull, "w") as devnull:
				check_call(args, stdout=devnull, stderr=devnull)
		except CalledProcessError:
			return False

		# check build requires
		requiresTypes = [ 'BUILD_REQUIRES' ]
		packageInfoFiles = self.port.generatePackageInfoFiles(requiresTypes,
															  packageInfoPath)
		args = ([ '/bin/pkgman', 'resolve-dependencies' ] + packageInfoFiles
				+ [
					doneRepositoryPath,
					buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'),
				])
		try:
			with open(os.devnull, "w") as devnull:
				check_call(args, stdout=devnull, stderr=devnull)
		except CalledProcessError:
			return False

		return True

	def markAsBuilt(self, doneRepositoryPath):
		self.port.writePackageInfosIntoRepository(doneRepositoryPath)

# -- PackageNode class ---------------------------------------------------------

class PackageNode(object):
	def __init__(self, portNode, packageID):
		self.portNode = portNode
		self.packageID = packageID
		self.requires = set()
		self.indegree = 0
		self.outdegree = 0

	def getName(self):
		return self.packageID

	def isPort(self):
		return False

	def getRequires(self):
		return self.requires

	def getDependencies(self):
		dependencies = self.requires
		dependencies.add(self.portNode)
		return dependencies

	def isSystemPackage(self):
		return not self.portNode

	def addRequires(self, elements):
		self.requires |= elements

# -- DependencyAnalyzer class --------------------------------------------------

class DependencyAnalyzer(object):
	def __init__(self, repository):
		self.repository = repository

		# Remove and re-create the no-requires repository directory. It
		# simplifies resolving the  immediate requires for all ports.
		print 'Preparing no-requires repository ...'

		self.noRequiresRepositoryPath = self.repository.path + '/.no-requires'

		if os.path.exists(self.noRequiresRepositoryPath):
			shutil.rmtree(self.noRequiresRepositoryPath)
		os.mkdir(self.noRequiresRepositoryPath)

		packageInfos = glob.glob(self.repository.path + '/*.PackageInfo')
		packageIDs = []
		for packageInfo in packageInfos:
			packageInfoFileName = os.path.basename(packageInfo)
			packageIDs.append(
				packageInfoFileName[:packageInfoFileName.rindex('.')])
			destinationPath = (self.noRequiresRepositoryPath + '/'
				+ packageInfoFileName)
			self._stripRequiresFromPackageInfo(packageInfo, destinationPath)

		# Remove and re-create the system no-requires repository directory. It
		# contains the package info for system packages without requires.
		print 'Preparing no-requires system repository ...'

		self.noRequiresSystemRepositoryPath = (self.repository.path
			+ '/.no-requires-system')

		if os.path.exists(self.noRequiresSystemRepositoryPath):
			shutil.rmtree(self.noRequiresSystemRepositoryPath)
		os.mkdir(self.noRequiresSystemRepositoryPath)

		# we temporarily need an empty directory to check the package infos
		self.emptyDirectory = self.noRequiresSystemRepositoryPath + '/empty'
		os.mkdir(self.emptyDirectory)

		for directory in [
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'),
			buildPlatform.findDirectory('B_COMMON_PACKAGES_DIRECTORY'),
		]:
			for package in os.listdir(directory):
				if not package.endswith('.hpkg'):
					continue

				# extract the package info from the package file
				fileName = package[:-5] + '.PackageInfo'
				destinationPath = (self.noRequiresSystemRepositoryPath + '/'
					+ fileName)
				sourcePath = destinationPath + '.tmp'
				check_call([Configuration.getPackageCommand(), 'extract', '-i',
					sourcePath, directory + '/' + package, '.PackageInfo'])

				# strip the requires section from the package info
				self._stripRequiresFromPackageInfo(sourcePath, destinationPath)
				os.remove(sourcePath)

				if not self._isPackageInfoValid(destinationPath):
					print ('Warning: Ignoring invalid package info from %s'
						% package)
					os.remove(destinationPath)

		os.rmdir(self.emptyDirectory)

		# Iterate through the packages and resolve dependencies. We build a
		# dependency graph with two different node types: port nodes and package
		# nodes. A port is something we want to build, a package is a what we
		# depend on. A package automatically depends on the port it belongs to.
		# Furthermore it depends on the packages its requires specify. Build
		# requires and build prerequires are dependencies for a port.
		print 'Resolving dependencies ...'

		allPorts = self.repository.getAllPorts()
		self.portNodes = {}
		self.packageNodes = {}
		self.allRequires = {}
		for packageID in packageIDs:
			# get the port ID for the package
			portID = packageID
			if portID not in allPorts:
				portID = self.repository.getPortIdForPackageId(portID)

			portNode = self._getPortNode(portID)
			if portNode.areDependenciesResolved:
				continue

			for package in portNode.port.packages:
				packageID = package.name + '-' + portNode.port.version
				packageNode = self._getPackageNode(packageID)

				recipeKeys = package.getRecipeKeys()
				packageNode.addRequires(
					self._resolveRequiresList(recipeKeys['REQUIRES']))
				portNode.addBuildRequires(
					self._resolveRequiresList(recipeKeys['BUILD_REQUIRES']))
				portNode.addBuildPrerequires(
					self._resolveRequiresList(recipeKeys['BUILD_PREREQUIRES']))

			portNode.areDependenciesResolved = True

		# determine the needed system packages
		self.systemPackageNodes = set()
		remainingPortNodes = set()
		nonSystemPackageNodes = set()

		for packageNode in self.packageNodes.itervalues():
			if packageNode.isSystemPackage():
				self.systemPackageNodes.add(packageNode)
			else:
				nonSystemPackageNodes.add(packageNode)
				remainingPortNodes.add(packageNode.portNode)

		# resolve the haikuporter dependencies
		haikuporterDependencies = self._resolveRequiresList(
			getScriptletPrerequirements())
		self.haikuporterRequires = set()
		for packageNode in haikuporterDependencies:
			if not packageNode.isSystemPackage():
				self.haikuporterRequires.add(packageNode)

		# ... and their requires closure
		nodeStack = list(self.haikuporterRequires)
		while nodeStack:
			packageNode = nodeStack.pop()
			portNode = packageNode.portNode
			for dependency in packageNode.getRequires():
				if (dependency in nonSystemPackageNodes
					and not dependency in self.haikuporterRequires):
					nodeStack.append(dependency)
					self.haikuporterRequires.add(dependency)

		# compute the in-degrees of the nodes
		nodes = set(remainingPortNodes)
		for portNode in remainingPortNodes:
			nodes |= portNode.packageNodes

		for node in nodes:
			for dependency in node.getDependencies():
				if dependency in nodes:
					dependency.indegree += 1

		indegreeZeroStack = []
		for node in nodes:
			if node.indegree == 0:
				indegreeZeroStack.append(node)

		# remove the acyclic part of the graph that nothing else depends on
		while indegreeZeroStack:
			node = indegreeZeroStack.pop()
			nodes.remove(node)
			for dependency in node.getDependencies():
				if dependency in nodes:
					dependency.indegree -= 1
					if dependency.indegree == 0:
						indegreeZeroStack.append(dependency)

		# compute the out-degrees of the remaining nodes
		for node in nodes:
			outdegree = 0
			for dependency in node.getDependencies():
				if dependency in nodes:
					outdegree += 1
			node.outdegree = outdegree

		outdegreeZeroStack = []
		for node in nodes:
			if node.outdegree == 0:
				outdegreeZeroStack.append(node)
				print '[%s] has out-degree 0' % node.getName()

		# remove the acyclic part of the graph that depends on nothing else
		while outdegreeZeroStack:
			node = outdegreeZeroStack.pop()
			nodes.remove(node)
			for otherNode in nodes:
				if (node in otherNode.getDependencies()
					and otherNode in nodes):
					otherNode.outdegree -= 1
					if otherNode.outdegree == 0:
						outdegreeZeroStack.append(otherNode)

		self.cyclicNodes = [
			node for node in nodes if node.isPort()
		]

		# clean up
		shutil.rmtree(self.noRequiresRepositoryPath)
		shutil.rmtree(self.noRequiresSystemRepositoryPath)

	def printDependencies(self):
		print 'Required system packages:'
		for packageNode in self.systemPackageNodes:
			print '  %s' % packageNode.getName()

		print 'Ports required by haikuporter:'
		for packageNode in self.haikuporterRequires:
			print '  %s' % packageNode.portNode.getName()

		print 'Ports depending cyclically on each other:'
		for node in self.cyclicNodes:
			print '  %s (out-degree %d)' % (node.getName(), node.outdegree)

	def getBuildOrderForBootstrap(self):
		packageInfoPath = self.repository.path + '/.package-infos'
		doneRepositoryPath = self.repository.path + '/.build-order-done'
		if os.path.exists(doneRepositoryPath):
			shutil.rmtree(doneRepositoryPath)
		os.mkdir(doneRepositoryPath)

		done = []
		nodes = set(self.cyclicNodes)
		while nodes:
			lastDoneCount = len(done)
			for node in sorted(list(nodes), key=PortNode.getName):
				if os.path.exists(packageInfoPath):
					shutil.rmtree(packageInfoPath)
				os.mkdir(packageInfoPath)
				if node.isBuildable(packageInfoPath, doneRepositoryPath):
					done.append(node.getName())
					nodes.remove(node)
					node.markAsBuilt(doneRepositoryPath)
			if lastDoneCount == len(done):
				sysExit("None of these cyclic dependencies can be built:\n\t"
						+ "\n\t".join(sorted(map(lambda node: node.getName(),
												 nodes))))

		shutil.rmtree(doneRepositoryPath)
		shutil.rmtree(packageInfoPath)

		return done

	def _resolveRequiresList(self, requiresList):
		dependencies = set()
		for requires in requiresList:
			# filter comments
			index = requires.find('#')
			if index >= 0:
				requires = requires[:index]
			requires = requires.strip()
			if not requires:
				continue

			# resolve the requires
			if requires in self.allRequires:
				resolved = self.allRequires[requires]
			else:
				resolved = self._resolveRequires(requires)
				self.allRequires[requires] = resolved
			if resolved:
				dependencies.add(resolved)
			else:
				print 'Warning: Ignoring unresolvable requires "%s"' % requires
		return dependencies

	def _resolveRequires(self, requires):
		# write the dummy package info with the requires to be resolved
		dummyPath = (self.noRequiresRepositoryPath
			+ '/_dummy_-1-1-any.PackageInfo')
		with open(dummyPath, 'w') as dummyFile:
			dummyFile.write(requiresDummyPackageInfo % requires)

		# let pkgman resolve the dependency
		isSystemPackage = False
		args = [ '/bin/pkgman', 'resolve-dependencies', dummyPath,
			self.noRequiresRepositoryPath ]
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(args, stderr=devnull)
		except CalledProcessError:
			try:
				args[-1] = self.noRequiresSystemRepositoryPath
				with open(os.devnull, "w") as devnull:
					output = check_output(args, stderr=devnull)
					isSystemPackage = True
			except CalledProcessError:
				return None

		lines = output.splitlines()
		if not lines:
			return None
		if len(lines) > 1:
			print 'Warning: Got multiple results for requires "%s"' % requires

		packageID = os.path.basename(lines[0])
		suffix = '.PackageInfo'
		if packageID.endswith(suffix):
			packageID = packageID[:-len(suffix)]
		packageIDComponents = packageID.split('-')
		if len(packageIDComponents) > 1:
			packageID = packageIDComponents[0] + '-' + packageIDComponents[1]
		else:
			packageID = packageIDComponents[0]

		return self._getPackageNode(packageID, isSystemPackage)

	def _isPackageInfoValid(self, packageInfoPath):
		args = [ '/bin/pkgman', 'resolve-dependencies', packageInfoPath,
			self.emptyDirectory ]
		try:
			with open(os.devnull, "w") as devnull:
				check_call(args, stderr=devnull)
				return True
		except CalledProcessError:
			return False

	def _getPortNode(self, portID):
		if portID in self.portNodes:
			return self.portNodes[portID]

		# get the port and create the port node
		port = self.repository.getAllPorts()[portID]
		portNode = PortNode(portID, port)
		self.portNodes[portID] = portNode

		# also create nodes for all of the port's packages
		portNode.port.parseRecipeFile(False)
		for package in port.packages:
			packageID = package.name + '-' + port.version
			packageNode = PackageNode(portNode, packageID)
			self.packageNodes[packageID] = packageNode
			portNode.packageNodes.add(packageNode)

		return portNode

	def _getPackageNode(self, packageID, isSystemPackage = False):
		if packageID in self.packageNodes:
			return self.packageNodes[packageID]

		if isSystemPackage:
			packageNode = PackageNode(None, packageID)
			self.packageNodes[packageID] = packageNode
			return packageNode

		# get the port -- that will also create nodes for all of the port's
		# packages
		portID = packageID
		if portID not in self.repository.getAllPorts():
			portID = self.repository.getPortIdForPackageId(portID)
		self._getPortNode(portID)

		if not packageID in self.packageNodes:
			sysExit('package "%s" doesn\'t seem to exist' % packageID)
		return self.packageNodes[packageID]

	def _stripRequiresFromPackageInfo(self, sourcePath, destinationPath):
		with open(sourcePath, 'r') as sourceFile:
			with open(destinationPath, 'w') as destinationFile:
				isInRequires = False
				for line in sourceFile:
					if isInRequires:
						if line == '}\n':
							isInRequires = False
					else:
						if line == 'requires {\n':
							isInRequires = True
						else:
							destinationFile.write(line)
