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
from HaikuPorter.ConfigParser import ConfigParser
from HaikuPorter.Configuration import Configuration
from HaikuPorter.Options import getOption
from HaikuPorter.RecipeTypes import Architectures, Status
from HaikuPorter.ShellScriptlets import getScriptletPrerequirements
from HaikuPorter.Utils import (check_output, escapeForPackageInfo,
							   haikuporterRepoUrl, haikuportsRepoUrl,
							   naturalCompare, sysExit)

import os
import shutil
from subprocess import check_call


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
	def __init__(self, packageType, name, port, recipeKeys, policy):
		self.type = packageType
		self.name = name
		self.version = port.version
		self.revision = port.revision

		self.workDir = port.workDir
		self.packageInfoDir = port.packageInfoDir
		self.buildPackageDir = port.buildPackageDir
		self.packagingDir = port.packagingBaseDir + '/' + self.name
		self.hpkgDir = port.hpkgDir
		self.recipeKeys = recipeKeys
		self.policy = policy

		self.versionedName = self.name + '-' + self.version
		self.fullVersion = self.version + '-' + self.revision
		self.revisionedName = self.name + '-' + self.fullVersion

		self.packageInfoName = self.versionedName + '.PackageInfo'

		if packageType == PackageType.SOURCE:
			self.architecture = Architectures.SOURCE
		elif port.targetArchitecture in self.recipeKeys['ARCHITECTURES']:
			# if this package can be built for the current target architecture,
			# we do so and create a package for the host architecture (which
			# is the same as the target architecture, except for "_cross_"
			# packages, which are built for the host on which the build runs.
			self.architecture = port.hostArchitecture
		elif Architectures.ANY in self.recipeKeys['ARCHITECTURES']:
			self.architecture = Architectures.ANY
		else:
			sysExit('package %s can not be built for architecture %s'
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
		elif (Architectures.ANY in self.recipeKeys['ARCHITECTURES']
			  or Architectures.SOURCE in self.recipeKeys['ARCHITECTURES']):
			return Status.STABLE
		return Status.UNSUPPORTED

	def getRecipeKeys(self):
		return self.recipeKeys

	def writePackageInfoIntoRepository(self, repositoryPath):
		"""Write a PackageInfo-file for this package into the repository"""

		packageInfoFile = repositoryPath + '/' + self.packageInfoName
		self.generatePackageInfo(packageInfoFile,
			[ 'BUILD_REQUIRES', 'REQUIRES' ], True)

	def removePackageInfoFromRepository(self, repositoryPath):
		"""Remove PackageInfo-file from repository, if it's there"""

		packageInfoFile = repositoryPath + '/' + self.packageInfoName
		if os.path.exists(packageInfoFile):
			os.remove(packageInfoFile)

	def obsoletePackage(self, packagesPath):
		"""Moves the package-file into the 'obsolete' sub-directory"""

		obsoleteDir = packagesPath + '/.obsolete'
		packageFile = packagesPath + '/' + self.hpkgName
		if os.path.exists(packageFile):
			print '\tobsoleting package ' + self.hpkgName
			obsoletePackage = obsoleteDir + '/' + self.hpkgName
			if not os.path.exists(obsoleteDir):
				os.mkdir(obsoleteDir)
			os.rename(packageFile, obsoletePackage)

	def generatePackageInfoWithoutProvides(self, packageInfoPath,
			requiresToUse):
		"""Create a .PackageInfo file that doesn't include any provides except
		   for the one matching the package name"""

		self._generatePackageInfo(packageInfoPath, requiresToUse, True, True,
								  Architectures.ANY)

	def generatePackageInfo(self, packageInfoPath, requiresToUse, quiet):
		"""Create a .PackageInfo file for inclusion in a package or for
		   dependency resolving"""

		self._generatePackageInfo(packageInfoPath, requiresToUse, quiet, False,
								  self.architecture)

	def adjustToChroot(self):
		"""Adjust directories to chroot()-ed environment"""

		# adjust all relevant directories
		pathLengthToCut = len(self.workDir)
		self.packageInfoDir = self.packageInfoDir[pathLengthToCut:]
		self.buildPackageDir = self.buildPackageDir[pathLengthToCut:]
		self.packagingDir = self.packagingDir[pathLengthToCut:]
		self.hpkgDir = self.hpkgDir[pathLengthToCut:]
		self.workDir = '/'
		self.patchesDir = '/patches'

	def prepopulatePackagingDir(self, port):
		"""Prefill packaging directory with stuff from the outside"""

		licenseDir = port.baseDir + '/licenses'
		if os.path.exists(licenseDir):
			shutil.copytree(licenseDir, self.packagingDir + '/data/licenses')

	def makeHpkg(self, requiresUpdater):
		"""Create a package suitable for distribution"""

		requiresList = self.recipeKeys['REQUIRES']
		self.recipeKeys['UPDATED_REQUIRES'] \
			= requiresUpdater.updateRequiresList(requiresList)

		self.generatePackageInfo(self.packagingDir + '/.PackageInfo',
								 ['UPDATED_REQUIRES'], getOption('quiet'))

		packageFile = self.hpkgDir + '/' + self.hpkgName
		if os.path.exists(packageFile):
			os.remove(packageFile)

		# mimeset the files that shall go into the package
		print 'mimesetting files for package ' + self.hpkgName + ' ...'
		mimeDBDir = 'data/mime_db'
		os.chdir(self.packagingDir)
		check_call([Configuration.getMimesetCommand(), '--all', '--mimedb',
			mimeDBDir, '--mimedb', buildPlatform.getSystemMimeDbDirectory(),
			'.'])

		# If data/mime_db is empty, remove it.
		if not os.listdir(mimeDBDir):
			os.rmdir(mimeDBDir)
			if not os.listdir('data'):
				os.rmdir('data')

		# Create the package
		print 'creating package ' + self.hpkgName + ' ...'
		check_call([Configuration.getPackageCommand(), 'create', packageFile])

		# policy check
		self.policy.checkPackage(self, packageFile)

		# Clean up after ourselves
		os.chdir(self.workDir)
		shutil.rmtree(self.packagingDir)

	def createBuildPackage(self):
		"""Create the build package"""

		# create a package info for a build package
		buildPackageInfo = (self.buildPackageDir + '/' + self.revisionedName
							+ '-build.PackageInfo')
		self.generatePackageInfo(buildPackageInfo,
								 ['REQUIRES', 'BUILD_REQUIRES',
								  'BUILD_PREREQUIRES'], True)

		# create the build package
		buildPackage = (self.buildPackageDir + '/' + self.revisionedName
						+ '-build.hpkg')
		cmdlineArgs = [Configuration.getPackageCommand(), 'create', '-bi',
			buildPackageInfo, '-I', self.packagingDir, buildPackage]
		if getOption('quiet'):
			cmdlineArgs.insert(2, '-q')
		check_call(cmdlineArgs)
		self.buildPackage = buildPackage
		os.remove(buildPackageInfo)

	def activateBuildPackage(self):
		"""Activate the build package"""

		self.activeBuildPackage = buildPlatform.activateBuildPackage(
			self.workDir, self.buildPackage)

	def removeBuildPackage(self):
		"""Deactivate and remove the build package"""

		if self.activeBuildPackage:
			buildPlatform.deactivateBuildPackage(self.workDir,
				self.activeBuildPackage)
			self.activeBuildPackage = None
		if self.buildPackage and os.path.exists(self.buildPackage):
			os.remove(self.buildPackage)
			self.buildPackage = None

	def _generatePackageInfo(self, packageInfoPath, requiresToUse, quiet,
							 fakeEmptyProvides, architecture):
		"""Create a .PackageInfo file for inclusion in a package or for
		   dependency resolving"""

		if not architecture:
			architecture = self.architecture

		# If it exists, remove the file first. Otherwise we might write to the
		# wrong file, if it is a symlink.
		if os.path.exists(packageInfoPath):
			os.remove(packageInfoPath)

		with open(packageInfoPath, 'w') as infoFile:
			if fakeEmptyProvides:
				infoFile.write('name\t\t\tfaked_' + self.name + '\n')
			else:
				infoFile.write('name\t\t\t' + self.name + '\n')
			infoFile.write('version\t\t\t' + self.fullVersion + '\n')
			infoFile.write('architecture\t\t' + architecture + '\n')
			infoFile.write('summary\t\t\t"'
						   + escapeForPackageInfo(self.recipeKeys['SUMMARY'])
						   + '"\n')

			infoFile.write('description\t\t"')
			infoFile.write(
				escapeForPackageInfo('\n'.join(self.recipeKeys['DESCRIPTION'])))
			infoFile.write('"\n')

			infoFile.write('packager\t\t"' + Configuration.getPackager() + '"\n')
			infoFile.write('vendor\t\t\t"Haiku Project"\n')

			# These keys aren't mandatory so we need to check if they exist
			if self.recipeKeys['LICENSE']:
				infoFile.write('licenses {\n')
				for license in self.recipeKeys['LICENSE']:
					infoFile.write('\t"' + license + '"\n')
				infoFile.write('}\n')

			if self.recipeKeys['COPYRIGHT']:
				infoFile.write('copyrights {\n')
				for copyright in self.recipeKeys['COPYRIGHT']:
					infoFile.write('\t"' + copyright + '"\n')
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

			self._writePackageInfoListQuotePaths(infoFile,
				self.recipeKeys['GLOBAL_WRITABLE_FILES'],
				'global-writable-files')
			self._writePackageInfoListQuotePaths(infoFile,
				self.recipeKeys['USER_SETTINGS_FILES'], 'user-settings-files')
			self._writePackageInfoListByKey(infoFile, 'PACKAGE_USERS', 'users')
			self._writePackageInfoListByKey(infoFile, 'PACKAGE_GROUPS',
				'groups')
			self._writePackageInfoListQuotePaths(infoFile,
				self.recipeKeys['POST_INSTALL_SCRIPTS'], 'post-install-scripts')

			# Generate SourceURL lines for all ports, regardless of license.
			# Re-use the download URLs, as specified in the recipe.
			infoFile.write('source-urls {\n')
			for index in sorted(self.recipeKeys['SRC_URI'].keys(),
								cmp=naturalCompare):
				uricount = 1
				for uri in self.recipeKeys['SRC_URI'][index]:
					if 'file://' in uri:
						# skip local URIs
						continue

					if uricount < 2:
						infoFile.write('\t"Download <' + uri + '>"\n')
					else:
						infoFile.write('\t"Location ' + str(uricount) + ' <'
									   + uri + '>"\n')
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
			with open(packageInfoPath, 'r') as infoFile:
				print infoFile.read()

	def _writePackageInfoListByKey(self, infoFile, key, keyword):
		self._writePackageInfoList(infoFile, self.recipeKeys[key], keyword)

	def _writePackageInfoList(self, infoFile, list, keyword):
		if list:
			infoFile.write(keyword + ' {\n')
			for item in list:
				infoFile.write('\t' + item + '\n')
			infoFile.write('}\n')

	def _writePackageInfoListQuotePaths(self, infoFile, list, keyword):
		if list:
			infoFile.write(keyword + ' {\n')
			for item in list:
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


# -- A source package ---------------------------------------------------------

class SourcePackage(Package):
	def prepopulatePackagingDir(self, port):
		"""Prefill packaging directory with stuff from the outside"""

		print "Populating source package ..."

		super(SourcePackage, self).prepopulatePackagingDir(port)

		targetBaseDir = (self.packagingDir + '/develop/sources/'
						 + port.revisionedName)
		for source in port.sources:
			if source.index == '1':
				targetDir = targetBaseDir + '/source'
			else:
				targetDir = targetBaseDir + '/source-' + source.index

			if not os.path.exists(targetDir):
				os.makedirs(targetDir)

			# export unchanged sources
			source.exportPristineSources(targetDir)

		# copy patches, if there are any
		if os.path.exists(port.patchesDir):
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
		if os.path.exists(port.licensesDir):
			licensesTargetDir = targetBaseDir + '/licenses'
			if not os.path.exists(licensesTargetDir):
				os.mkdir(licensesTargetDir)
			for licenseFileName in os.listdir(port.licensesDir):
				licenseFilePath = port.licensesDir + '/' + licenseFileName
				shutil.copy(licenseFilePath, licensesTargetDir)

		# add ReadMe
		if os.path.exists(Configuration.getTreePath() + '/.git'):
			haikuportsRev \
				= check_output([ 'git', 'rev-parse', '--short', 'HEAD' ],
							   cwd=Configuration.getTreePath())
		else:
			haikuportsRev = '<unknown>'
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
