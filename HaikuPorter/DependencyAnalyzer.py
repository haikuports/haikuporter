# -*- coding: utf-8 -*-
# copyright 2013 Ingo Weinhold

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Port import Port
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
		self.requires = set()
		self.buildRequires = set()
		self.buildPrerequires = set()
		self.indegree = 0

	def isSystemPackage(self):
		return not self.port

	def getBuildDependencies(self):
		return self.buildRequires | self.buildPrerequires

	def doesBuildDependOn(self, node):
		return node in self.buildRequires or node in self.buildPrerequires

	def addRequires(self, elements):
		self.requires |= elements

	def addBuildRequires(self, elements):
		self.buildRequires |= elements

	def addBuildPrerequires(self, elements):
		self.buildPrerequires |= elements

# -- DependencyAnalyzer class --------------------------------------------------

class DependencyAnalyzer(object):
	def __init__(self, repository):
		self.repository = repository

		# Remove and re-create the no-requires repository directory. It
		# simplifies resolving the  immediate requires for all ports.
		print 'Preparing no-requires repository ...'

		self.noRequiresRepositoryPath = self.repository.path + '.no-requires'

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
			+ '.no-requires-system')

		if os.path.exists(self.noRequiresSystemRepositoryPath):
			shutil.rmtree(self.noRequiresSystemRepositoryPath)
		os.mkdir(self.noRequiresSystemRepositoryPath)

		# we temporarily need an empty directory to check the package infos
		self.emptyDirectory = self.noRequiresSystemRepositoryPath + '/empty'
		os.mkdir(self.emptyDirectory)

		for directory in ['/boot/system/packages', '/boot/common/packages']:
			for package in os.listdir(directory):
				if not package.endswith('.hpkg'):
					continue

				# extract the package info from the package file
				fileName = package[:-5] + '.PackageInfo'
				destinationPath = (self.noRequiresSystemRepositoryPath + '/'
					+ fileName)
				sourcePath = destinationPath + '.tmp'
				check_call(['package', 'extract', '-i', sourcePath,
					directory + '/' + package, '.PackageInfo'])

				# strip the requires section from the package info
				self._stripRequiresFromPackageInfo(sourcePath, destinationPath)
				os.remove(sourcePath)

				if not self._isPackageInfoValid(destinationPath):
					print ('Warning: Ignoring invalid package info from %s'
						% package)
					os.remove(destinationPath)

		os.rmdir(self.emptyDirectory)

		# iterate through the packages and resolve dependencies
		print 'Resolving requires ...'

		allPorts = self.repository.getAllPorts()
		self.portNodes = {}
		self.allRequires = {}
		for packageID in packageIDs:
			# get the port ID for the package
			portID = packageID
			if portID not in allPorts:
				portID = self.repository.getPortIdForPackageId(portID)

			portNode = self._getPortNode(portID)
			if portNode.areDependenciesResolved:
				continue

			portNode.port.parseRecipeFile(False)
			for package in portNode.port.packages:
				recipeKeys = package.getRecipeKeys()
				portNode.addRequires(
					self._resolveRequiresList(recipeKeys['REQUIRES']))
				portNode.addBuildRequires(
					self._resolveRequiresList(recipeKeys['BUILD_REQUIRES']))
				portNode.addBuildPrerequires(
					self._resolveRequiresList(recipeKeys['BUILD_PREREQUIRES']))

			portNode.areDependenciesResolved = True

		# print the needed system packages
		print 'Required system packages:'

		nonSystemPortNodes = []

		for portNode in self.portNodes.itervalues():
			if portNode.isSystemPackage():
				print '  %s' % portNode.portID
			else:
				nonSystemPortNodes.append(portNode)

#		# print the immediate dependencies of each port
#		print 'Immediate port build dependencies:'
#
#		for portNode in self.portNodes.itervalues():
#			if portNode.isSystemPackage():
#				continue
#			print '  %s:' % portNode.portID
#			for dependency in portNode.getBuildDependencies():
#				print '    %s' % dependency.portID

		# print the self-depending ports
		print 'Self depending ports:'

		portNodes = set()

		for portNode in nonSystemPortNodes:
			if portNode.doesBuildDependOn(portNode):
				print '  %s' % portNode.portID
			else:
				portNodes.add(portNode)

		# compute the in-degrees of the port nodes
		for portNode in portNodes:
			for dependency in portNode.getBuildDependencies():
				if dependency in portNodes:
					dependency.indegree += 1

		indegreeZeroStack = []
		for portNode in portNodes:
			if portNode.indegree == 0:
				indegreeZeroStack.append(portNode)

		# remove the acyclic part of the graph
		while indegreeZeroStack:
			portNode = indegreeZeroStack.pop()
			portNodes.remove(portNode)
			for dependency in portNode.getBuildDependencies():
				if dependency in portNodes:
					dependency.indegree -= 1
					if dependency.indegree == 0:
						indegreeZeroStack.append(dependency)

		# print the remaining cycle(s)
		print 'Ports depending cyclically on each other:'

		for portNode in portNodes:
			print '  %s' % portNode.portID

		# clean up
		shutil.rmtree(self.noRequiresRepositoryPath)
		shutil.rmtree(self.noRequiresSystemRepositoryPath)

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
			print 'Warning: Got multiple result for requires "%s"' % requires

		packageID = os.path.basename(lines[0])
		suffix = '.PackageInfo'
		if packageID.endswith(suffix):
			packageID = packageID[:-len(suffix)]

		if isSystemPackage:
			return self._getPortNode(packageID, True)

		portID = packageID
		if portID not in self.repository.getAllPorts():
			portID = self.repository.getPortIdForPackageId(portID)
		return self._getPortNode(portID)

	def _isPackageInfoValid(self, packageInfoPath):
		args = [ '/bin/pkgman', 'resolve-dependencies', packageInfoPath,
			self.emptyDirectory ]
		try:
			with open(os.devnull, "w") as devnull:
				check_call(args, stderr=devnull)
				return True
		except CalledProcessError:
			return False

	def _getPortNode(self, portID, isSystemPackage = False):
		if portID in self.portNodes:
			return self.portNodes[portID]
		port = None
		if not isSystemPackage:
			port = self.repository.getAllPorts()[portID]
		portNode = PortNode(portID, port)
		self.portNodes[portID] = portNode
		return portNode

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
