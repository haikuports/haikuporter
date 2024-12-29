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

import codecs
import datetime
import json
import os
import shutil
from functools import cmp_to_key
from subprocess import STDOUT, CalledProcessError, check_call, check_output

from .BuildPlatform import buildPlatform
from .ConfigParser import ConfigParser
from .Configuration import Configuration
from .Options import getOption
from .RecipeTypes import Architectures, Status
from .ShellScriptlets import getScriptletPrerequirements
from .Utils import (ensureCommandIsAvailable, escapeForPackageInfo,
                    haikuporterRepoUrl, haikuportsRepoUrl, info,
                    naturalCompare, sysExit, touchFile, warn)

# -- The supported package types ----------------------------------------------

class PackageType(str):
	DEBUG_INFO = 'debuginfo'
	DEVELOPMENT = 'devel'
	DOCUMENTATION = 'doc'
	GENERAL = 'general'
	SOURCE = 'source'

	@staticmethod
	def byName(name):
		"""Lookup the type by name"""

		if name == PackageType.DEBUG_INFO:
			return PackageType.DEBUG_INFO
		elif name == PackageType.DEVELOPMENT:
			return PackageType.DEVELOPMENT
		elif name == PackageType.DOCUMENTATION:
			return PackageType.DOCUMENTATION
		elif name == PackageType.SOURCE:
			return PackageType.SOURCE
		else:
			return PackageType.GENERAL


# -- Base class for all packages ----------------------------------------------

class Package(object):
	def __init__(self, packageType, name, port, recipeKeys, policy,
			isRiggedSourcePackage=False):
		self.type = packageType
		if 'PACKAGE_NAME' in recipeKeys:
			self.name = recipeKeys['PACKAGE_NAME']
		if not self.name:
			self.name = name
		if 'PACKAGE_VERSION' in recipeKeys:
			self.version = recipeKeys['PACKAGE_VERSION']
		if not self.version:
			self.version = port.version
		self.revision = port.revision
		self.secondaryArchitecture = port.secondaryArchitecture

		self.workDir = port.workDir
		self.buildPackageDir = port.buildPackageDir
		self.packagingDir = port.packagingBaseDir + '/' + self.name
		self.hpkgDir = port.hpkgDir
		self.recipeKeys = recipeKeys
		self.policy = policy

		self.versionedName = self.name + '-' + self.version
		self.fullVersion = self.version + '-' + self.revision
		self.revisionedName = self.name + '-' + self.fullVersion

		self.packageInfoName = self.versionedName + '.PackageInfo'
		self.dependencyInfoName = self.versionedName + '.DependencyInfo'

		self.isRiggedSourcePackage = isRiggedSourcePackage

		if packageType == PackageType.SOURCE:
			if self.isRiggedSourcePackage:
				# let rigged source packages use the target architecture, as
				# (potentially) they have been patched specifically for that
				# target architecture
				self.architecture = port.targetArchitecture
			else:
				self.architecture = Architectures.SOURCE
		elif ((port.secondaryArchitecture is not None and
			  port.secondaryArchitecture in self.recipeKeys['SECONDARY_ARCHITECTURES']) or
			  port.targetArchitecture in self.recipeKeys['ARCHITECTURES']):
			# if this package can be built for the current target architecture,
			# we do so and create a package for the host architecture (which
			# is the same as the target architecture, except for "_cross_"
			# packages, which are built for the host on which the build runs.)
			self.architecture = port.hostArchitecture
		elif Architectures.ANY in self.recipeKeys['ARCHITECTURES']:
			self.architecture = Architectures.ANY
		else:
			sysExit('package %s cannot be built for architecture %s'
					% (self.versionedName, port.targetArchitecture))

		self.fullVersionedName = self.versionedName + '-' + self.architecture
		self.fullRevisionedName = self.revisionedName + '-' + self.architecture
		self.hpkgName = self.fullRevisionedName + '.hpkg'

		self.targetMachineTripleAsName \
			= port.shellVariables.get('targetMachineTripleAsName', '')

		self.buildPackage = None
		self.activeBuildPackage = None

	def getStatusOnArchitecture(self, architecture):
		"""Return the status of this package on the given architecture (which
		   must be a hardware architecture, i.e. not ANY or SOURCE)"""

		if architecture in self.recipeKeys['ARCHITECTURES']:
			return self.recipeKeys['ARCHITECTURES'][architecture]
		elif Architectures.ANY in self.recipeKeys['ARCHITECTURES']:
			return self.recipeKeys['ARCHITECTURES'][Architectures.ANY]
		elif Architectures.SOURCE in self.recipeKeys['ARCHITECTURES']:
			return Status.STABLE
		return Status.UNSUPPORTED

	def isBuildableOnArchitecture(self, architecture):
		"""Returns whether or not this package is buildable on the given
		   architecture"""
		status = self.getStatusOnArchitecture(architecture)
		allowUntested = Configuration.shallAllowUntested()
		return (status == Status.STABLE
			or (status == Status.UNTESTED and allowUntested))

	def getStatusOnSecondaryArchitecture(self, architecture,
			secondaryArchitecture):
		# check the secondary architecture
		if secondaryArchitecture:
			secondaryStatus = Status.UNSUPPORTED
			secondaryArchitectures = self.recipeKeys['SECONDARY_ARCHITECTURES']
			if secondaryArchitecture in secondaryArchitectures:
				secondaryStatus = secondaryArchitectures[secondaryArchitecture]

			return secondaryStatus
		else:
			return self.getStatusOnArchitecture(architecture)

	def isBuildableOnSecondaryArchitecture(self, architecture,
			secondaryArchitecture, forceAllowUnstable=False):
		status = self.getStatusOnSecondaryArchitecture(architecture,
			secondaryArchitecture)
		allowUntested = Configuration.shallAllowUntested()
		return (status == Status.STABLE
			or (status == Status.UNTESTED and allowUntested)
			or forceAllowUnstable)

	def dependencyInfoFile(self, repositoryPath):
		return os.path.join(repositoryPath, self.dependencyInfoName)

	def writeDependencyInfoIntoRepository(self, repositoryPath):
		"""Write a DependencyInfo-file for this package into the repository"""

		requires = ['BUILD_REQUIRES', 'BUILD_PREREQUIRES', 'REQUIRES',
			'TEST_REQUIRES']
		self.generateDependencyInfo(self.dependencyInfoFile(repositoryPath),
			requires)

	def removeDependencyInfoFromRepository(self, repositoryPath):
		"""Remove DependencyInfo-file from repository, if it's there"""

		dependencyInfoFile = self.dependencyInfoFile(repositoryPath)
		if os.path.exists(dependencyInfoFile):
			os.remove(dependencyInfoFile)

	def generateDependencyInfoWithoutProvides(self, dependencyInfoPath,
											  requiresToUse):
		"""Create a .DependencyInfo file that doesn't include any provides
		   except for the one matching the package name"""

		self._generateDependencyInfo(dependencyInfoPath, requiresToUse,
			fakeProvides=True, architectures=Architectures.ANY)

	def generateDependencyInfo(self, dependencyInfoPath, requiresToUse):
		"""Create a .DependencyInfo file (used for dependency resolving)"""

		self._generateDependencyInfo(dependencyInfoPath, requiresToUse)

	def adjustToChroot(self):
		"""Adjust directories to chroot()-ed environment"""

		# adjust all relevant directories
		pathLengthToCut = len(self.workDir)
		self.buildPackageDir = self.buildPackageDir[pathLengthToCut:]
		self.packagingDir = self.packagingDir[pathLengthToCut:]
		self.hpkgDir = self.hpkgDir[pathLengthToCut:]
		self.workDir = '/'

	def populatePackagingDir(self, port):
		"""Prefill packaging directory with stuff from the outside"""

		licenseDir = port.baseDir + '/licenses'
		if os.path.exists(licenseDir):
			shutil.copytree(licenseDir, self.packagingDir + '/data/licenses')

	def makeHpkg(self, requiresUpdater):
		"""Create a package suitable for distribution"""

		packageFile = self.hpkgDir + '/' + self.hpkgName
		if os.path.exists(packageFile):
			os.remove(packageFile)

		# policy check, add some requires
		self.policy.checkPackage(self, packageFile)

		if (requiresUpdater and self.type != PackageType.SOURCE):
			requiresList = self.recipeKeys['REQUIRES']
			self.recipeKeys['UPDATED_REQUIRES'] \
				= requiresUpdater.updateRequiresList(requiresList)
			requiresName = 'UPDATED_REQUIRES'
		else:
			requiresName = 'REQUIRES'

		self._generatePackageInfo(self.packagingDir + '/.PackageInfo',
			[requiresName], getOption('quiet'), False, True, self.architecture)

		# mimeset the files that shall go into the package
		info('mimesetting files for package ' + self.hpkgName + ' ...')
		dataDir = os.path.join(self.packagingDir, 'data')
		mimeDBDir = os.path.join(dataDir, 'mime_db')
		check_call([Configuration.getMimesetCommand(), '--all', '--mimedb',
			'data/mime_db', '--mimedb',
			buildPlatform.getSystemMimeDbDirectory(), '.'],
			cwd=self.packagingDir)

		# If data/mime_db is empty, remove it.
		if not os.listdir(mimeDBDir):
			os.rmdir(mimeDBDir)
			if not os.listdir(dataDir):
				os.rmdir(dataDir)
		else:
			t = datetime.datetime(2001, 8, 18, 0, 0)
			for superMimeType in os.listdir(mimeDBDir):
				touchFile(mimeDBDir + "/" + superMimeType, t)

		# Create the package
		info('creating package ' + self.hpkgName + ' ...')
		output = check_output([Configuration.getPackageCommand(), 'create', packageFile],
			cwd=self.packagingDir).decode('utf-8')
		info(output)

		# Clean up after ourselves
		shutil.rmtree(self.packagingDir)

	def createBuildPackage(self):
		"""Create the build package"""

		# create a package info for a build package
		buildPackageInfo = (self.buildPackageDir + '/' + self.revisionedName
							+ '-build.PackageInfo')
		self._generatePackageInfo(buildPackageInfo,
			['REQUIRES', 'BUILD_REQUIRES', 'BUILD_PREREQUIRES'], True, False,
			False, self.architecture)

		# create the build package
		buildPackage = (self.buildPackageDir + '/' + self.revisionedName
						+ '-build.hpkg')
		cmdlineArgs = [Configuration.getPackageCommand(), 'create', '-bi',
			buildPackageInfo, '-I', self.packagingDir, buildPackage]
		if getOption('quiet'):
			cmdlineArgs.insert(2, '-q')
		try:
			output = check_output(cmdlineArgs, stderr=STDOUT).decode('utf-8')
		except CalledProcessError as exception:
			raise Exception('failure creating the build package: '
				+ "\n\tcommand: '%s'" % ' '.join(exception.cmd)
				+ "\n\treturn code: '%s'" % exception.returncode
				+ "\n\toutput: '%s'" % exception.output[:-1].decode('utf-8'))
		info(output)
		self.buildPackage = buildPackage
		os.remove(buildPackageInfo)

	def activateBuildPackage(self):
		"""Activate the build package"""

		self.activeBuildPackage = buildPlatform.activateBuildPackage(
			self.workDir, self.buildPackage, self.revisionedName)

	def removeBuildPackage(self):
		"""Deactivate and remove the build package"""

		if self.activeBuildPackage:
			buildPlatform.deactivateBuildPackage(self.workDir,
				self.activeBuildPackage, self.revisionedName)
			self.activeBuildPackage = None
		if self.buildPackage and os.path.exists(self.buildPackage):
			os.remove(self.buildPackage)
			self.buildPackage = None

	def _generatePackageInfo(self, packageInfoPath, requiresToUse, quiet,
			fakeEmptyProvides, withActivationActions, architecture):
		"""Create a .PackageInfo file for inclusion in a package or for
		   dependency resolving"""

		if not architecture:
			architecture = self.architecture

		# If it exists, remove the file first. Otherwise we might write to the
		# wrong file, if it is a symlink.
		if os.path.exists(packageInfoPath):
			os.remove(packageInfoPath)

		with codecs.open(packageInfoPath, 'w', 'utf-8') as infoFile:
			if fakeEmptyProvides:
				infoFile.write('name\t\t\tfaked_' + self.name + '\n')
			else:
				infoFile.write('name\t\t\t' + self.name + '\n')
			infoFile.write('version\t\t\t' + self.fullVersion + '\n')
			infoFile.write('architecture\t\t' + architecture + '\n')
			infoFile.write('summary\t\t\t"'
				+ escapeForPackageInfo(self.recipeKeys['SUMMARY'])
				+ '"\n'
			)

			infoFile.write('description\t\t"')
			infoFile.write(
				escapeForPackageInfo('\n'.join(self.recipeKeys['DESCRIPTION'])))
			infoFile.write('"\n')

			infoFile.write('packager\t\t"' + Configuration.getPackager() + '"\n')
			infoFile.write('vendor\t\t\t"' + Configuration.getVendor() + '"\n')

			# These keys aren't mandatory so we need to check if they exist
			if self.recipeKeys['LICENSE']:
				infoFile.write('licenses {\n')
				for aLicense in self.recipeKeys['LICENSE']:
					infoFile.write('\t"' + aLicense + '"\n')
				infoFile.write('}\n')

			if self.recipeKeys['COPYRIGHT']:
				infoFile.write('copyrights {\n')
				for aCopyright in self.recipeKeys['COPYRIGHT']:
					infoFile.write('\t"' + aCopyright + '"\n')
				infoFile.write('}\n')

			requires = []
			for requiresKey in requiresToUse:
				if requiresKey == 'SCRIPTLET_PREREQUIRES':
					# Add prerequirements for executing chroot scriptlets.
					# For cross-built packages, pass in the target machine name,
					# but take care to not do that for packages that implement
					# the cross-building themselves (i.e. binutils and gcc),
					# as those are running in the context of the build machine.
					targetMachineTripleAsName = self.targetMachineTripleAsName
					if (Configuration.isCrossBuildRepository()
						and '_cross_' in self.name):
						targetMachineTripleAsName = ''
					requiresForKey = getScriptletPrerequirements(
						targetMachineTripleAsName)
				else:
					requiresForKey = self.recipeKeys[requiresKey]
				for require in requiresForKey:
					if require not in requires:
						requires.append(require)

			if fakeEmptyProvides:
				infoFile.write('provides {\n\tfaked_' + self.name + ' = '
							   + self.version + '\n}\n')
			else:
				self._writePackageInfoListByKey(infoFile, 'PROVIDES',
												'provides')
			self._writePackageInfoList(infoFile, requires, 'requires')
			self._writePackageInfoListByKey(infoFile, 'SUPPLEMENTS',
											'supplements')
			self._writePackageInfoListByKey(infoFile, 'CONFLICTS', 'conflicts')
			self._writePackageInfoListByKey(infoFile, 'FRESHENS', 'freshens')
			self._writePackageInfoListByKey(infoFile, 'REPLACES', 'replaces')

			self._writePackageInfoListQuotePaths(infoFile,
				self.recipeKeys['HOMEPAGE'], 'urls')

			if withActivationActions:
				self._writePackageInfoListQuotePaths(infoFile,
					self.recipeKeys['GLOBAL_WRITABLE_FILES'],
					'global-writable-files')
				self._writePackageInfoListQuotePaths(infoFile,
					self.recipeKeys['USER_SETTINGS_FILES'],
					'user-settings-files')
				self._writePackageInfoListByKey(infoFile, 'PACKAGE_USERS',
					'users')
				self._writePackageInfoListByKey(infoFile, 'PACKAGE_GROUPS',
					'groups')
				self._writePackageInfoListQuotePaths(infoFile,
					self.recipeKeys['POST_INSTALL_SCRIPTS'],
					'post-install-scripts')
				self._writePackageInfoListQuotePaths(infoFile,
					self.recipeKeys['PRE_UNINSTALL_SCRIPTS'],
					'pre-uninstall-scripts')

			# Generate SourceURL lines for all ports, regardless of license.
			# Re-use the download URLs, as specified in the recipe.
			infoFile.write('source-urls {\n')
			for index in sorted(list(self.recipeKeys['SOURCE_URI'].keys()),
					key=cmp_to_key(naturalCompare)):
				uricount = 1
				for uri in self.recipeKeys['SOURCE_URI'][index]:
					if 'file://' in uri:
						# skip local URIs
						continue

					if uricount < 2:
						infoFile.write('# Download\n')
						infoFile.write('\t"' + uri + '"\n')
					else:
						infoFile.write('# Location ' + str(uricount) + '\n')
						infoFile.write('\t"' + uri + '"\n')
					uricount += 1

			# TODO: fix or drop the following URLs
			# Point directly to the file in subversion.
			#recipeurl_base = ('http://ports.haiku-files.org/'
			#				  + 'svn/haikuports/trunk/' + self.category + '/'
			#				  + self.name)
			#
			#recipeurl = (recipeurl_base + '/' + self.name+ '-' + self.version
			#			 + '.recipe')

			#infoFile.write('\t"Port-file <' + recipeurl + '>"\n')
			#patchFilePath = (self.patchesDir + '/' + self.name + '-'
			#				 + self.version + '.patch')
			#if os.path.exists(patchFilePath):
			#	patchurl = (recipeurl_base + '/patches/' + self.name + '-'
			#				+ self.version + '.patch')
			#	infoFile.write('\t"Patches <' + patchurl + '>"\n')

			infoFile.write('}\n')

		if not quiet:
			with codecs.open(packageInfoPath, 'r', 'utf-8') as infoFile:
				info(infoFile.read())

	def _writePackageInfoListByKey(self, infoFile, key, keyword):
		self._writePackageInfoList(infoFile, self.recipeKeys[key], keyword)

	def _writePackageInfoList(self, infoFile, theList, keyword):
		if theList:
			infoFile.write(keyword + ' {\n')
			for item in theList:
				infoFile.write('\t' + item + '\n')
			infoFile.write('}\n')

	def _writePackageInfoListQuotePaths(self, infoFile, theList, keyword):
		if theList:
			infoFile.write(keyword + ' {\n')
			for item in theList:
				# quote unquoted components that look like paths
				components = ConfigParser.splitItem(item)
				item = ''
				for component in components:
					if component[0] != '"' and component.find('/') >= 0:
						component = '"' + component + '"'
					if item:
						item += ' '
					item += component
				infoFile.write('\t' + item + '\n')
			infoFile.write('}\n')

	def _generateDependencyInfo(self, dependencyInfoPath, requiresToUse,
								**kwargs):
		"""Create a .DependencyInfo file (used for dependency resolving)"""

		architecture = kwargs.get('architecture', self.architecture)
		fakeProvides = kwargs.get('fakeProvides', False)

		# If it exists, remove the file first. Otherwise we might write to the
		# wrong file, if it is a symlink.
		if os.path.exists(dependencyInfoPath):
			os.remove(dependencyInfoPath)

		with codecs.open(dependencyInfoPath, 'w', 'utf-8') as infoFile:
			dependencyInfo = {
				'name': self.name,
				'version': self.version,
				'architecture': architecture,
				'provides': self.recipeKeys['PROVIDES'],
				'requires': [],
				'buildRequires': [],
				'buildPrerequires': [],
				'testRequires': []
			}

			if fakeProvides:
				dependencyInfo['provides'] = []

			requiresKeyMap = {
				'BUILD_REQUIRES': 'buildRequires',
				'BUILD_PREREQUIRES': 'buildPrerequires',
				'TEST_REQUIRES': 'testRequires',
				'REQUIRES': 'requires',
				'SCRIPTLET_PREREQUIRES': 'buildPrerequires',
			}
			for requiresKey in requiresToUse:
				if requiresKey == 'SCRIPTLET_PREREQUIRES':
					# Add prerequirements for executing chroot scriptlets.
					# For cross-built packages, pass in the target machine name,
					# but take care to not do that for packages that implement
					# the cross-building themselves (i.e. binutils and gcc),
					# as those are running in the context of the build machine.
					targetMachineTripleAsName = self.targetMachineTripleAsName
					if (Configuration.isCrossBuildRepository()
						and '_cross_' in self.name):
						targetMachineTripleAsName = ''
					requiresForKey = getScriptletPrerequirements(
						targetMachineTripleAsName)
				else:
					requiresForKey = self.recipeKeys[requiresKey]

				requiresList = dependencyInfo[requiresKeyMap[requiresKey]]
				for require in requiresForKey:
					require = require.partition('#')[0].strip()
					if require and require not in requiresList:
						requiresList.append(require)

			json.dump(dependencyInfo, infoFile, sort_keys=True,
				indent=4, separators=(',', ' : '))
			infoFile.write('\n')

# -- A source package ---------------------------------------------------------

class SourcePackage(Package):
	def populatePackagingDir(self, port):
		"""Prefill packaging directory with stuff from the outside"""

		if self.isRiggedSourcePackage:
			info("Populating rigged source package ...")
		else:
			info("Populating source package ...")

		super(SourcePackage, self).populatePackagingDir(port)

		targetBaseDir = (self.packagingDir + '/develop/sources/'
						 + port.revisionedName)
		for source in port.sources:
			targetDir = (targetBaseDir + '/'
						 + os.path.basename(source.sourceBaseDir))
			# export sources and additional files (if any)
			source.exportSources(targetDir, self.isRiggedSourcePackage)
			source.populateAdditionalFiles(targetBaseDir)

		# copy patches, if there are any
		if port.patchesDir and os.path.exists(port.patchesDir):
			patchesTargetDir = targetBaseDir + '/patches'
			for patchFileName in os.listdir(port.patchesDir):
				if not (patchFileName.startswith(port.versionedName + '.')
						or patchFileName.startswith(port.versionedName + '-')):
					continue
				if not os.path.exists(patchesTargetDir):
					os.mkdir(patchesTargetDir)
				patchFilePath = port.patchesDir + '/' + patchFileName
				shutil.copy(patchFilePath, patchesTargetDir)

		# copy licenses, if there are any
		if port.licensesDir and os.path.exists(port.licensesDir):
			licensesTargetDir = targetBaseDir + '/licenses'
			if not os.path.exists(licensesTargetDir):
				os.mkdir(licensesTargetDir)
			for licenseFileName in os.listdir(port.licensesDir):
				licenseFilePath = port.licensesDir + '/' + licenseFileName
				shutil.copy(licenseFilePath, licensesTargetDir)

		# add ReadMe with references to the used repositories
		haikuportsRev = '<unknown>'
		if os.path.exists(Configuration.getTreePath() + '/.git'):
			try:
				ensureCommandIsAvailable('git')
				haikuportsRev \
					= check_output(['git', 'rev-parse', '--short', 'HEAD'],
						cwd=Configuration.getTreePath(), stderr=STDOUT).decode('utf-8')
			except:
				warn('unable to determine revision of haikuports tree')
		with open(targetBaseDir + '/ReadMe', 'w') as readmeFile:
			readmeFile.write((
				'These are the sources (and optionally patches) that were\n'
				'used to build the "%s"-package(s).\n\n'
				'In order to build them, please checkout the haikuports tree\n'
				'and use the haikuporter tool to run the build for you.\n\n'
				'haikuports-URL: %s (revision %s)\n'
				'haikuporter-URL: %s\n')
				% (port.name, haikuportsRepoUrl, haikuportsRev.strip(),
				   haikuporterRepoUrl))

		# copy recipe file
		shutil.copy(port.recipeFilePath, targetBaseDir)

# -- package factory function -------------------------------------------------

def packageFactory(packageType, name, port, recipeKeys, policy):
	"""Creates a package matching the given type"""

	if packageType == PackageType.SOURCE:
		return SourcePackage(packageType, name, port, recipeKeys, policy)
	else:
		return Package(packageType, name, port, recipeKeys, policy)

# -- source package factory function ------------------------------------------

def sourcePackageFactory(name, port, recipeKeys, policy, rigged):
	"""Creates a source package"""

	return SourcePackage(PackageType.SOURCE, name, port, recipeKeys, policy,
						 rigged)
