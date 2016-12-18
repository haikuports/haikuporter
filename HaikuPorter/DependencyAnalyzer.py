# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Copyright 2014 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .BuildPlatform import buildPlatform
from .Options import getOption
from .PackageInfo import (PackageInfo, ResolvableExpression)
from .ProvidesManager import ProvidesManager
from .ShellScriptlets import getScriptletPrerequirements
from .Utils import sysExit

import copy
import os
import shutil
from subprocess import CalledProcessError

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
		self.packageNodes = set()
		self.requires = set()
		self.buildRequires = set()
		self.buildPrerequires = set()
		self.indegree = 0
		self.outdegree = 0

	@property
	def name(self):
		return self.portID

	@property
	def dependencies(self):
		return self.buildRequires | self.buildPrerequires

	@property
	def isPort(self):
		return True

	def addBuildRequires(self, elements):
		self.buildRequires |= elements

	def addBuildPrerequires(self, elements):
		self.buildPrerequires |= elements

	def isBuildable(self, repositoryPath, doneRepositoryPath):
		# check prerequires
		dependencyInfoFiles = self.port.getDependencyInfoFiles(repositoryPath)
		requiresTypes = [ 'BUILD_REQUIRES', 'BUILD_PREREQUIRES',
						  'SCRIPTLET_PREREQUIRES' ]
		repositories = [ doneRepositoryPath ];
		if not getOption('noSystemPackages'):
			repositories.append(
				buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))

		try:
			buildPlatform.resolveDependencies(dependencyInfoFiles,
											  requiresTypes,
											  repositories)
		except (CalledProcessError, LookupError):
			return False

		return True

	def markAsBuilt(self, doneRepositoryPath):
		self.port.writeDependencyInfosIntoRepository(doneRepositoryPath)

# -- PackageNode class ---------------------------------------------------------

class PackageNode(object):
	def __init__(self, portNode, packageID):
		self.portNode = portNode
		self.name = packageID
		self.requires = set()
		self.indegree = 0
		self.outdegree = 0

	@property
	def isPort(self):
		return False

	@property
	def dependencies(self):
		dependencies = copy.copy(self.requires)
		dependencies.add(self.portNode)
		return dependencies

	@property
	def isSystemPackage(self):
		return not self.portNode

	def addRequires(self, elements):
		self.requires |= elements

# -- DependencyAnalyzer class --------------------------------------------------

class DependencyAnalyzer(object):
	def __init__(self, repository):
		self.repository = repository
		self.portNodes = {}
		self.packageNodes = {}
		self.packageInfos = {}
		self.providesManager = ProvidesManager()

	def printDependencies(self):
		if not self.portNodes:
			self._doInitialDependencyResolution()

		print 'Required system packages:'
		for packageNode in sorted(self.systemPackageNodes,
				key=lambda packageNode: packageNode.name):
			print '	 %s' % packageNode.name

		print 'Ports required by haikuporter:'
		for packageNode in sorted(self.haikuporterRequires,
				key=lambda packageNode: packageNode.name):
			print '	 %s' % packageNode.portNode.name

		print 'Ports depending cyclically on each other:'
		for node in sorted(sorted(self.cyclicNodes, key=lambda node: node.name),
				key=lambda node: node.outdegree):
			print '	 %s (out-degree %d)' % (node.name, node.outdegree)

	def getBuildOrderForBootstrap(self):
		if not self.portNodes:
			self._doInitialDependencyResolution()

		doneRepositoryPath = self.repository.path + '/.build-order-done'
		if os.path.exists(doneRepositoryPath):
			shutil.rmtree(doneRepositoryPath)
		os.mkdir(doneRepositoryPath)

		done = []
		nodes = set(self.cyclicNodes)
		while nodes:
			lastDoneCount = len(done)
			for node in sorted(list(nodes), key=lambda node: node.name):
				print '# checking if %s is buildable ...' % node.name
				if node.isBuildable(self.repository.path, doneRepositoryPath):
					done.append(node.name)
					nodes.remove(node)
					node.markAsBuilt(doneRepositoryPath)
			if lastDoneCount == len(done):
				sysExit(u"None of these cyclic dependencies can be built:\n\t"
						+ "\n\t".join(sorted(map(lambda node: node.name,
												 nodes))))

		shutil.rmtree(doneRepositoryPath)

		return done

	def _doInitialDependencyResolution(self):
		# Iterate through the packages and resolve dependencies. We build a
		# dependency graph with two different node types: port nodes and package
		# nodes. A port is something we want to build, a package is a what we
		# depend on. A package automatically depends on the port it belongs to.
		# Furthermore it depends on the packages its requires specify. Build
		# requires and build prerequires are dependencies for a port.
		print 'Resolving dependencies ...'

		self._collectDependencyInfos(self.repository.path)
		self._collectSystemPackages()

		allActivePorts = []
		for portName in sorted(self.repository.portVersionsByName.keys()):
			activePortVersion = self.repository.getActiveVersionOf(portName)
			if not activePortVersion:
				print 'Warning: Skipping ' + portName + ', no version active'
				continue

			allActivePorts.append(portName + '-' + activePortVersion)

		for portID in allActivePorts:
			portNode = self._getPortNode(portID)
			for package in portNode.port.packages:
				packageID = package.versionedName
				packageNode = self._getPackageNode(packageID)
				packageInfo = self.packageInfos[packageID]
				packageNode.addRequires(
					self._resolveRequiresList(packageInfo.requires, portID,
						packageID))
				portNode.addBuildRequires(
					self._resolveRequiresList(packageInfo.buildRequires, portID,
						packageID))
				portNode.addBuildPrerequires(
					self._resolveRequiresList(packageInfo.buildPrerequires,
						portID, packageID))

		# determine the needed system packages
		self.systemPackageNodes = set()
		remainingPortNodes = set()
		nonSystemPackageNodes = set()

		for packageNode in self.packageNodes.itervalues():
			if packageNode.isSystemPackage:
				self.systemPackageNodes.add(packageNode)
			else:
				nonSystemPackageNodes.add(packageNode)
				remainingPortNodes.add(packageNode.portNode)

		# resolve system package dependencies
		for packageNode in self.systemPackageNodes:
			packageInfo = self.packageInfos[packageNode.name]
			packageNode.addRequires(
				self._resolveRequiresList(packageInfo.requires,
					'system packages', packageNode.name))

		nodeStack = list(self.systemPackageNodes)
		while nodeStack:
			packageNode = nodeStack.pop()
			for dependency in packageNode.requires:
				if (dependency in nonSystemPackageNodes
					and not dependency in self.systemPackageNodes):
					nodeStack.append(dependency)
					self.systemPackageNodes.add(dependency)

		# resolve the haikuporter dependencies
		scriptletPrerequirements = [ ResolvableExpression(requires)
				for requires in getScriptletPrerequirements() ]
		haikuporterDependencies \
			= self._resolveRequiresList(scriptletPrerequirements,
				'haikuporter', 'scriptlet requires')
		self.haikuporterRequires = set()
		for packageNode in haikuporterDependencies:
			if not packageNode.isSystemPackage:
				self.haikuporterRequires.add(packageNode)

		# ... and their requires closure
		nodeStack = list(self.haikuporterRequires)
		while nodeStack:
			packageNode = nodeStack.pop()
			for dependency in packageNode.requires:
				if (dependency in nonSystemPackageNodes
					and not dependency in self.haikuporterRequires):
					nodeStack.append(dependency)
					self.haikuporterRequires.add(dependency)

		# compute the in-degrees of the nodes
		nodes = set(remainingPortNodes)
		for portNode in remainingPortNodes:
			nodes |= portNode.packageNodes

		for node in nodes:
			for dependency in node.dependencies:
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
			for dependency in node.dependencies:
				if dependency in nodes:
					dependency.indegree -= 1
					if dependency.indegree == 0:
						indegreeZeroStack.append(dependency)

		# compute the out-degrees of the remaining nodes
		for node in nodes:
			outdegree = 0
			for dependency in node.dependencies:
				if dependency in nodes:
					outdegree += 1
			node.outdegree = outdegree

		outdegreeZeroStack = []
		for node in nodes:
			if node.outdegree == 0:
				outdegreeZeroStack.append(node)
				print '[%s] has out-degree 0' % node.name

		# remove the acyclic part of the graph that depends on nothing else
		while outdegreeZeroStack:
			node = outdegreeZeroStack.pop()
			nodes.remove(node)
			for otherNode in nodes:
				if (node in otherNode.dependencies
					and otherNode in nodes):
					otherNode.outdegree -= 1
					if otherNode.outdegree == 0:
						outdegreeZeroStack.append(otherNode)

		self.cyclicNodes = [
			node for node in nodes if node.isPort
		]

	def _collectDependencyInfos(self, path):
		for entry in os.listdir(path):
			if not entry.endswith('.DependencyInfo'):
				continue
			dependencyInfoFile = path + '/' + entry
			try:
				packageInfo = PackageInfo(dependencyInfoFile)
			except CalledProcessError:
				print ('Warning: Ignoring broken dependency-info file "%s"'
					   % dependencyInfoFile)
			self.providesManager.addProvidesFromPackageInfo(packageInfo)
			self.packageInfos[packageInfo.versionedName] = packageInfo

	def _collectSystemPackages(self):
		if getOption('noSystemPackages'):
			return

		path = buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY')
		for entry in os.listdir(path):
			if not entry.endswith('.hpkg'):
				continue
			packageFile = path + '/' + entry
			try:
				packageInfo = PackageInfo(packageFile)
			except CalledProcessError:
				print ('Warning: Ignoring broken package file "%s"'
					   % packageFile)
			self.providesManager.addProvidesFromPackageInfo(packageInfo)
			self.packageInfos[packageInfo.versionedName] = packageInfo

	def _resolveRequiresList(self, requiresList, portID, packageID):
		dependencies = set()
		for requires in requiresList:
			providesInfo = self.providesManager.getMatchingProvides(requires)
			if providesInfo:
				isSystemPackage \
					= buildPlatform.isSystemPackage(providesInfo.path)
				packageNode = self._getPackageNode(providesInfo.packageID,
												   isSystemPackage)
				dependencies.add(packageNode)
			else:
				print('Warning: Ignoring unresolvable requires "%s" of package'
					' %s in %s' % (requires, packageID, portID))
		return dependencies

	def _getPortNode(self, portID):
		if portID in self.portNodes:
			return self.portNodes[portID]

		# get the port and create the port node
		port = self.repository.allPorts[portID]
		portNode = PortNode(portID, port)
		self.portNodes[portID] = portNode

		# also create nodes for all of the port's packages
		portNode.port.parseRecipeFile(False)
		for package in port.packages:
			packageID = package.versionedName
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
		portID = self.repository.getPortIdForPackageId(packageID)
		self._getPortNode(portID)

		if not packageID in self.packageNodes:
			sysExit(u'package "%s" doesn\'t seem to exist' % packageID)
		return self.packageNodes[packageID]
