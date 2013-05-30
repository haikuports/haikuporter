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

from HaikuPorter.ConfigParser import ConfigParser
from HaikuPorter.GlobalConfig import globalConfiguration
from HaikuPorter.Options import getOption
from HaikuPorter.RecipeTypes import Architectures, Status
from HaikuPorter.ShellScriptlets import getScriptletPrerequirements
from HaikuPorter.Utils import (escapeForPackageInfo, naturalCompare, sysExit, 
							   systemDir, unpackArchive)

import os
import shutil
from subprocess import check_call


# -- The supported package types ----------------------------------------------

class PackageType(str):
	DEBUG = 'debug'
	DEVELOPMENT = 'development'
	DOCUMENTATION = 'documentation'
	GENERAL = 'general'
	SOURCE = 'source'

	@staticmethod	
	def byName(name):
		"""Lookup the type by name"""
		
		if name == PackageType.DEBUG:
			return PackageType.DEBUG
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
	def __init__(self, type, name, port, recipeKeys, policy):
		self.type = type
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

		if type == PackageType.SOURCE:
			# TODO: switch to SOURCE, when support for that has been implemented
			#       in the solver
			self.architecture = Architectures.ANY
		elif port.currentArchitecture in self.recipeKeys['ARCHITECTURES']:
			self.architecture = port.currentArchitecture
		elif Architectures.ANY in self.recipeKeys['ARCHITECTURES']:
			self.architecture = Architectures.ANY
		else:
			sysExit('package %s can not be built on architecture %s'
					% (self.versionedName, port.currentArchitecture))

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
		self._generatePackageInfo(packageInfoFile, 
								  [ 'BUILD_REQUIRES', 'REQUIRES' ], True, False)
					
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

		self._generatePackageInfo(packageInfoPath, requiresToUse, True, True)
		
	def generatePackageInfo(self, packageInfoPath, requiresToUse, quiet):
		"""Create a .PackageInfo file for inclusion in a package or for
		   dependency resolving"""

		self._generatePackageInfo(packageInfoPath, requiresToUse, quiet, False)

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

	def makeHpkg(self):
		"""Create a package suitable for distribution"""

		self.generatePackageInfo(self.packagingDir + '/.PackageInfo', 
								 ['REQUIRES'], getOption('quiet'))

		packageFile = self.hpkgDir + '/' + self.hpkgName
		if os.path.exists(packageFile):
			os.remove(packageFile)

		# mimeset the files that shall go into the package
		print 'mimesetting files for package ' + self.hpkgName + ' ...'
		mimeDBDir = 'data/mime_db'
		os.chdir(self.packagingDir)
		check_call(['mimeset', '--all', '--mimedb', mimeDBDir,
			'--mimedb', '/boot/system/data/mime_db', '.'])

		# If data/mime_db is empty, remove it.
		if not os.listdir(mimeDBDir):
			os.rmdir(mimeDBDir)
			if not os.listdir('data'):
				os.rmdir('data')

		# Create the package
		print 'creating package ' + self.hpkgName + ' ...'
		check_call(['package', 'create', packageFile])

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
		cmdlineArgs = ['package', 'create', '-bi', buildPackageInfo, '-I',
					   self.packagingDir, buildPackage]
		if getOption('quiet'):
			cmdlineArgs.insert(2, '-q')
		check_call(cmdlineArgs)
		self.buildPackage = buildPackage
		os.remove(buildPackageInfo)

	def activateBuildPackage(self):
		"""Activate the build package"""
		
		# activate the build package
		packagesDir = systemDir['B_COMMON_PACKAGES_DIRECTORY']
		activeBuildPackage \
			= packagesDir + '/' + os.path.basename(self.buildPackage)
		if os.path.exists(activeBuildPackage):
			os.remove(activeBuildPackage)
			
		if not getOption('chroot'):
			# may have to cross devices, so better use a symlink
			os.symlink(self.buildPackage, activeBuildPackage)
		else:
			# symlinking a package won't work in chroot, but in this
			# case we are sure that the move won't cross devices
			os.rename(self.buildPackage, activeBuildPackage)
		self.activeBuildPackage = activeBuildPackage

	def removeBuildPackage(self):
		"""Deactivate and remove the build package"""
		
		if self.activeBuildPackage and os.path.exists(self.activeBuildPackage):
			os.remove(self.activeBuildPackage)
			self.activeBuildPackage = None
		if self.buildPackage and os.path.exists(self.buildPackage):
			os.remove(self.buildPackage)
			self.buildPackage = None

	def _generatePackageInfo(self, packageInfoPath, requiresToUse, quiet,
							 fakeEmptyProvides):
		"""Create a .PackageInfo file for inclusion in a package or for
		   dependency resolving"""
		
		with open(packageInfoPath, 'w') as infoFile:
			if fakeEmptyProvides:
				infoFile.write('name\t\t\tfaked_' + self.name + '\n')
			else:
				infoFile.write('name\t\t\t' + self.name + '\n')
			infoFile.write('version\t\t\t' + self.fullVersion + '\n')
			infoFile.write('architecture\t\t' + self.architecture + '\n')
			infoFile.write('summary\t\t\t"' 
						   + escapeForPackageInfo(self.recipeKeys['SUMMARY']) 
						   + '"\n')
	
			infoFile.write('description\t\t"')
			infoFile.write(
				escapeForPackageInfo('\n'.join(self.recipeKeys['DESCRIPTION'])))
			infoFile.write('"\n')
	
			infoFile.write('packager\t\t"' + globalConfiguration['PACKAGER'] 
						   + '"\n')
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
					# as those are running in the context of the host machine.
					# TODO: fix relying on the names of the ports!
					targetMachineTripleAsName = self.targetMachineTripleAsName
					if ('gcc_cross_' in self.name 
						or 'binutils_cross' in self.name):
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
	
			infoFile.write('urls\t\t\t"' + self.recipeKeys['HOMEPAGE'] + '"\n')

			self._writePackageInfoListQuotePaths(infoFile,
				self.recipeKeys['GLOBAL_SETTINGS_FILES'],
				'global-settings-files')
			self._writePackageInfoListQuotePaths(infoFile,
				self.recipeKeys['USER_SETTINGS_FILES'], 'user-settings-files')
			self._writePackageInfoListByKey(infoFile, 'PACKAGE_USERS', 'users')
			self._writePackageInfoListByKey(infoFile, 'PACKAGE_GROUPS',
				'groups')
	
			# Generate SourceURL lines for all ports, regardless of license.
			# Re-use the download URLs, as specified in the recipe.
			infoFile.write('source-urls {\n')
			for index in sorted(self.recipeKeys['SRC_URI'].keys(), 
								cmp=naturalCompare):
				uricount = 1
				for uri in self.recipeKeys['SRC_URI'][index]:
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

		targetBaseDir = (self.packagingDir + '/develop/sources/' 
						 + port.revisionedName)
		for source in port.sources:
			if source.index == '1':
				targetDir = targetBaseDir + '/source'
			else:
				targetDir = targetBaseDir + '/source-' + source.index
				
			if not os.path.exists(targetDir):
				os.makedirs(targetDir)
	
			if source.localFile:
				# unpack the archive into source package's directory
				unpackArchive(source.localFile, targetDir)
			elif source.checkout:
				# Start building the command to perform the checkout
				type = source.checkout['type']
				rev = source.checkout['rev']
				os.chdir(source.sourceDir)
				if type == 'svn':
					command = 'svn export -r %s . "%s"' % (rev, targetDir)
				elif type == 'hg':
					command \
						= 'hg archive -r %s -t files "%s"' % (rev, targetDir)
				elif type == 'git':
					command \
						= 'git archive %s | tar -x -C "%s"' % (rev, targetDir)
				else:
					sysExit('Exporting sources from checkout has not been '
						    + ' implemented yet for vcs-type ' + type)
				check_call(command, shell=True)
	
			if source.patches:
				# copy and apply patches
				patchesDir = targetBaseDir + '/patches'
				os.mkdir(patchesDir)
				for patch in source.patches:
					shutil.copy(patch, patchesDir)
					check_call(['patch', '-p0', '-i', patch], cwd=targetDir)
				with open(patchesDir + '/ReadMe', 'w') as readmeFile:
					readmeFile.write('The patches in this folder have already '
									 + 'been applied to the sources.\n')

		# copy recipe file
		shutil.copy(port.recipeFilePath, targetBaseDir)

# -- package factory function -------------------------------------------------

def packageFactory(type, name, port, recipeKeys, policy):
	"""Creates a package matching the given type"""
	
	if type == PackageType.SOURCE:
		return SourcePackage(type, name, port, recipeKeys, policy)
	else:
		return Package(type, name, port, recipeKeys, policy)
