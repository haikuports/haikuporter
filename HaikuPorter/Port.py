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
from HaikuPorter.GlobalConfig import globalConfiguration
from HaikuPorter.Options import getOption
from HaikuPorter.Package import (PackageType, packageFactory)
from HaikuPorter.RecipeAttributes import recipeAttributes
from HaikuPorter.RecipeTypes import Extendable, Phase, Status
from HaikuPorter.RequiresUpdater import RequiresUpdater
from HaikuPorter.ShellScriptlets import (cleanupChrootScript,
										 getShellVariableSetters,
										 recipeActionScript,
										 setupChrootScript)
from HaikuPorter.Source import Source
from HaikuPorter.Utils import (check_output, filteredEnvironment,
							   naturalCompare, symlinkFiles, symlinkGlob,
							   sysExit, touchFile, warn)

import os
import shutil
import signal
from subprocess import check_call, CalledProcessError
import traceback


# -- Modules preloaded for chroot ---------------------------------------------
# These modules need to be preloaded in order to avoid problems with python
# trying to dynamically load them inside a chroot environment
from encodings import string_escape


# -- Scoped resource for chroot environments ----------------------------------
class ChrootSetup(object):
	def __init__(self, chrootPath, envVars):
		self.path = chrootPath
		self.buildOk = False
		self.envVars = envVars

	def __enter__(self):
		# execute the chroot setup scriptlet via the shell ...
		os.chdir(self.path)
		shellEnv = filteredEnvironment()
		shellEnv.update(self.envVars)
		check_call(['/bin/bash', '-c', setupChrootScript], env=shellEnv)
		return self
	
	def __exit__(self, type, value, traceback):
		# execute the chroot cleanup scriptlet via the shell ...
		os.chdir(self.path)
		shellEnv = filteredEnvironment()
		shellEnv.update(self.envVars)
		if self.buildOk:
			shellEnv['buildOk'] = '1'
		check_call(['/bin/bash', '-c', cleanupChrootScript], env=shellEnv)


# -- A single port with its recipe, allows to execute actions -----------------
class Port(object):
	def __init__(self, name, version, category, baseDir, globalShellVariables,
				 policy):
		self.name = name
		self.version = version
		self.versionedName = name + '-' + version
		self.category = category			
		self.baseDir = baseDir

		self.recipeFilePath \
			= self.baseDir + '/' + self.name + '-' + self.version + '.recipe'
		
		self.packageInfoName = self.versionedName + '.PackageInfo'
		
		self.revision = None
		self.fullVersion = None
		self.revisionedName = None
		
		self.definedPhases = []

		# build dictionary of variables to inherit to shell
		self.shellVariables = {
			'portName': self.name,
			'portVersion': self.version,
			'portVersionedName': self.versionedName,
			'portBaseDir': self.baseDir,
		}
		self.shellVariables.update(globalShellVariables)
		self._updateShellVariables(True)
		
		self.buildArchitecture = self.shellVariables['buildArchitecture']
		self.targetArchitecture = self.shellVariables['targetArchitecture']
		if (globalConfiguration['IS_CROSSBUILD_REPOSITORY']
			and '_cross_' in name):
			# the cross-tools (binutils and gcc) need to run on the build 
			# architecture, not the target architecture
			self.hostArchitecture = self.shellVariables['buildArchitecture']
		else:
			self.hostArchitecture = self.shellVariables['targetArchitecture']

		# Each port creates at least two packages: the base package (which will 
		# share its name with the port), and a source package.
		# Additional packages can be declared in the recipe, too. All packages
		# that are considered stable on the current architecture will be 
		# collected in self.packages.
		self.allPackages = []
		self.packages = []

		# create full paths for the directories
		self.downloadDir = self.baseDir + '/download'
		self.patchesDir = self.baseDir + '/patches'
		self.workDir = self.baseDir + '/work-' + self.version
		self.sourceBaseDir = self.workDir + '/sources'
		self.packageInfoDir = self.workDir + '/package-infos'
		self.buildPackageDir = self.workDir + '/build-packages'
		self.packagingBaseDir = self.workDir + '/packaging'
		self.hpkgDir = self.workDir + '/hpkgs'

		self.preparedRecipeFile = self.workDir + '/port.recipe'

		self.policy = policy

	def __enter__(self):
		return self
	
	def __exit__(self, type, value, traceback):
		pass

	def parseRecipeFile(self, showWarnings):
		"""Parse the recipe-file of the specified port"""

		# If a patch file named like the port exists, use that as a default
		# for "PATCHES" (check this for up to 9 sources). Support a second 
		# patchset which is specific to target-architecture, too.
		for s in range(1, 9):
			if s == 1:
				patchSetFileName = self.name + '-' + self.version + '.patchset'
				archPatchSetFileName = (self.name + '-' + self.version + '-'
										+ self.targetArchitecture 
										+ '.patchset')
				patchFileName = self.name + '-' + self.version + '.patch'
				diffFileName = self.name + '-' + self.version + '.diff'
				patchesKeyName = 'PATCHES'
			else:
				patchSetFileName = (self.name + '-' + self.version + '-source' 
									+ str(s) + '.patchset')
				archPatchSetFileName = (self.name + '-' + self.version + '-'
										+ self.targetArchitecture + '-source'
										+ str(s) + '.patchset')
				patchFileName = (self.name + '-' + self.version + '-source' 
								 + str(s) + '.patch')
				diffFileName = (self.name + '-' + self.version + '-source' 
								+ str(s) + '.diff')
				patchesKeyName = 'PATCHES_' + str(s)
			patchSetFilePath = self.patchesDir + '/' + patchSetFileName
			archPatchSetFilePath = self.patchesDir + '/' + archPatchSetFileName
			patchFilePath = self.patchesDir + '/' + patchFileName
			diffFilePath = self.patchesDir + '/' + diffFileName

			# prefer patchsets over patch
			patchsets = []
			if os.path.exists(patchSetFilePath):
				patchsets.append(patchSetFileName)
			if os.path.exists(archPatchSetFilePath):
				patchsets.append(archPatchSetFileName)
			if not patchsets and os.path.exists(patchFilePath):
				patchsets.append(patchFileName)
			if not patchsets and os.path.exists(diffFilePath):
				patchsets.append(diffFileName)
			self.shellVariables[patchesKeyName] = '\n'.join(patchsets)
		
		self.recipeKeysByExtension = self.validateRecipeFile(showWarnings)
		self.recipeKeys = {}
		for entries in self.recipeKeysByExtension.values():
			self.recipeKeys.update(entries)

		# initialize variables that depend on the recipe revision
		self.revision = str(self.recipeKeys['REVISION'])
		self.fullVersion = self.version + '-' + self.revision
		self.revisionedName = self.name + '-' + self.fullVersion

		# create sources
		self.sources = []
		keys = self.recipeKeys
		for index in sorted(keys['SRC_URI'].keys(), cmp=naturalCompare):
			source = Source(self, index, keys['SRC_URI'][index], 
							keys['SRC_FILENAME'].get(index, None),
							keys['CHECKSUM_MD5'].get(index, None),
							keys['SOURCE_DIR'].get(index, None),
							keys['PATCHES'].get(index, []))
			self.sources.append(source)

		# create packages
		self.allPackages = []
		self.packages = []
		haveSourcePackage = False
		for extension in sorted(self.recipeKeysByExtension.keys()):
			keys = self.recipeKeysByExtension[extension]
			if extension:
				name = self.name + '_' + extension
			else:
				name = self.name
			packageType = PackageType.byName(extension)
			package = packageFactory(packageType, name, self, keys, self.policy)
			self.allPackages.append(package)
			
			if packageType == PackageType.SOURCE:
				haveSourcePackage = True
			
			status = package.getStatusOnArchitecture(self.targetArchitecture)
			if (status == Status.STABLE 
				or (status == Status.UNTESTED 
					and globalConfiguration['ALLOW_UNTESTED'])):
				self.packages.append(package)

		# create source package if it hasn't been specified or disabled:
		if (not haveSourcePackage and not keys['DISABLE_SOURCE_PACKAGE']
			and getOption('sourcePackageByDefault')):
			# copy all recipe attributes from base package, but set defaults
			# for everything that's package-specific:
			sourceKeys = {}
			baseKeys = self.recipeKeysByExtension['']
			for key in baseKeys.keys():
				if recipeAttributes[key]['extendable'] != Extendable.NO:
					sourceKeys[key] = recipeAttributes[key]['default']
				else:
					sourceKeys[key] = baseKeys[key]
					
			# a source package shares some attributes with the base package,
			# just provides itself and has no requires:
			name = self.name + '_source'
			sourceSuffix \
				= recipeAttributes['SUMMARY']['suffix'][PackageType.SOURCE]
			sourceKeys.update({
				'ARCHITECTURES': baseKeys['ARCHITECTURES'],
				'COPYRIGHT': baseKeys['COPYRIGHT'],
				'DESCRIPTION': baseKeys['DESCRIPTION'],
				'HOMEPAGE': baseKeys['HOMEPAGE'],
				'LICENSE': baseKeys['LICENSE'],
				'PROVIDES': [ name + ' = ' + self.version ],
				'SUMMARY': (baseKeys['SUMMARY'] + sourceSuffix),
			})
			package = packageFactory(PackageType.SOURCE, name, self, sourceKeys, 
									 self.policy)
			self.allPackages.append(package)
			self.packages.append(package)

		self.sourceDir = self.sources[0].sourceDir

		# set up the complete list of variables we'll inherit to the shell
		# when executing a recipe action
		self._updateShellVariablesFromRecipe()

	def validateRecipeFile(self, showWarnings = False):
		"""Validate the syntax and contents of the recipe file"""
		
		if not os.path.exists(self.recipeFilePath):
			sysExit(self.name + ' version ' + self.version + ' not found.')

		# copy the recipe file and prepare it for use
		if not os.path.exists(os.path.dirname(self.preparedRecipeFile)):
			os.mkdir(os.path.dirname(self.preparedRecipeFile))

		prepareRecipeCommand = [ '/bin/bash', '-c',
			'sed \'s,^\\(REVISION="[^"]*"\\),\\1; updateRevisionVariables ,\' '
				+ self.recipeFilePath + ' > ' + self.preparedRecipeFile]
		check_call(prepareRecipeCommand)

		# parse the recipe file
		recipeConfig = ConfigParser(self.preparedRecipeFile, recipeAttributes, 
							  		self.shellVariables)
		extensions = recipeConfig.getExtensions()
		self.definedPhases = recipeConfig.getDefinedPhases()
		
		if '' not in extensions:
			sysExit('No base package defined in (in %s)' % self.recipeFilePath)

		recipeKeysByExtension = {}
		
		# do some checks for each extension (i.e. package), starting with the
		# base entries (extension '')
		baseEntries = recipeConfig.getEntriesForExtension('')
		for extension in sorted(extensions):
			entries = recipeConfig.getEntriesForExtension(extension)
			recipeKeys = {}
			
			# check whether all required values are present
			for baseKey in recipeAttributes.keys():
				if extension:
					key = baseKey + '_' + extension
					# inherit any missing attribute from the respective base 
					# value or set the default
					if key not in entries:
						attributes = recipeAttributes[baseKey]
						if attributes['extendable'] == Extendable.DEFAULT:
							recipeKeys[baseKey] = attributes['default']
						else:
							if ('suffix' in attributes
								and extension in attributes['suffix']):
								recipeKeys[baseKey] = (
									baseEntries[baseKey] 
									+ attributes['suffix'][extension])
							else:
								recipeKeys[baseKey] = baseEntries[baseKey]
							continue
								# inherited values don't need to be checked
				else:
					key = baseKey

				if key not in entries:
					# complain about missing required values
					if recipeAttributes[baseKey]['required']:
						sysExit("Required value '%s' not present (in %s)" 
								% (key, self.recipeFilePath))
					
					# set default value, as no other value has been provided
					entries[key] = recipeAttributes[baseKey]['default']
				
				# The summary must be a single line of text, preferably not 
				# exceeding 70 characters in length
				if baseKey == 'SUMMARY':
					if '\n' in entries[key]:
						sysExit('%s must be a single line of text (%s).' 
							% (key, self.recipeFilePath))
					if len(entries[key]) > 70 and showWarnings:
						warn('%s exceeds 70 chars (in %s)' 
							 % (key, self.recipeFilePath))

				# Check for a valid license file
				if baseKey == 'LICENSE':
					if key in entries and entries[key]:
						fileList = []
						recipeLicense = entries['LICENSE']
						for item in recipeLicense:
							haikuLicenseList = fileList = os.listdir(
								buildPlatform.getLicensesDirectory())
							if item not in fileList:
								fileList = []
								dirname = (os.path.dirname(self.recipeFilePath) 
										   + '/licenses')
								if os.path.exists(dirname):
									for filename in os.listdir(dirname):
										fileList.append(filename)
							if item not in fileList:
								haikuLicenseList.sort()
								sysExit('No match found for license ' + item 
										+ '\nValid license filenames included '
										+ 'with Haiku are:\n' 
										+ '\n'.join(haikuLicenseList))
					elif showWarnings:
						warn('No %s found (in %s)' % (key, self.recipeFilePath))

				if baseKey == 'COPYRIGHT':
					if key not in entries or not entries[key]:
						if showWarnings:
							warn('No %s found (in %s)' 
								 % (key, self.recipeFilePath))

				# store extension-specific value under base key						
				recipeKeys[baseKey] = entries[key]
				
			recipeKeysByExtension[extension] = recipeKeys

		return recipeKeysByExtension

	def printDescription(self):
		"""Show port description"""
		
		print '*' * 80
		print 'VERSION: %s' % self.versionedName
		print 'REVISION: %s' % self.revision
		print 'HOMEPAGE: %s' % self.recipeKeys['HOMEPAGE']
		for package in self.allPackages:
			print '-' * 80
			print 'PACKAGE: %s' % package.versionedName
			print 'SUMMARY: %s' % package.recipeKeys['SUMMARY']
			print('STATUS: %s' 
				  % package.getStatusOnArchitecture(self.targetArchitecture))
			print 'ARCHITECTURE: %s' % package.architecture
		print '*' * 80

	def getStatusOnTargetArchitecture(self):
		"""Return the status of this port on the target architecture"""

		try:
			if not hasattr(self, 'recipeKeys'):
				self.parseRecipeFile(False)

			return self.allPackages[0].getStatusOnArchitecture(
				self.targetArchitecture)
		except:
			return Status.UNSUPPORTED
	
	def writePackageInfosIntoRepository(self, repositoryPath):
		"""Write one PackageInfo-file per stable package into the repository"""

		for package in self.packages:
			package.writePackageInfoIntoRepository(repositoryPath)
					
	def removePackageInfosFromRepository(self, repositoryPath):
		"""Remove all PackageInfo-files for this port from the repository"""

		for package in self.packages:
			package.removePackageInfoFromRepository(repositoryPath)
					
	def obsoletePackages(self, packagesPath):
		"""Moves all package-files into the 'obsolete' sub-directory"""

		for package in self.packages:
			package.obsoletePackage(packagesPath)
					
	def resolveBuildDependencies(self, repositoryPath, packagesPath):
		"""Resolve any other ports that need to be built before this one.
		
		   In order to do so, we first determine the prerequired packages for
		   the build, for which packages from outside the haikuports-tree may 
		   be considered. A temporary folder is then populated with only these
		   prerequired packages and then all the build requirements of this
		   port are determined with only the haikuports repository, the already
		   built packages and the repository of prerequired packages active.
		   This ensures that any build requirements a port may have that can not 
		   be fulfilled from within the haikuports tree will be raised as an 
		   error here.
		"""

		workRepositoryPath = self.workDir + '/repository'
		prereqRepositoryPath = self.workDir + '/prereq-repository'
		packageInfoFiles = self._prepareRepositories(workRepositoryPath, 
													 prereqRepositoryPath,
													 repositoryPath, 
													 packagesPath)
		
		# Determine the build requirements, this time only allowing system
		# packages.from the build machine.
		repositories = [ packagesPath, workRepositoryPath, prereqRepositoryPath,
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY') ]
		packages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'required ports')

		shutil.rmtree(workRepositoryPath)
		shutil.rmtree(prereqRepositoryPath)

		# Filter out system packages, as they are irrelevant.
		return [ 
			package for package in packages 
			if not package.startswith(
				buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))
		], workRepositoryPath

	def whyIsPortRequired(self, repositoryPath, packagesPath, requiredPort):
		"""Find out which package is pulling the given port in as a dependency
		   of this port."""

		workRepositoryPath = self.workDir + '/repository'
		prereqRepositoryPath = self.workDir + '/prereq-repository'
		packageInfoFiles = self._prepareRepositories(workRepositoryPath, 
													 prereqRepositoryPath,
													 repositoryPath, 
													 packagesPath)

		# drop package-infos for the required port, such that pkgman will
		# fail with an appropriate message
		requiredPort.removePackageInfosFromRepository(workRepositoryPath)
		requiredPort.removePackageInfosFromRepository(prereqRepositoryPath)

		# Ask pkgman to determine the build requirements, which should fail
		# on the required port, with an error message that gives a hint
		# about who requires it.
		repositories = [ workRepositoryPath, prereqRepositoryPath,
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY') ]
		self._resolveDependenciesViaPkgman(packageInfoFiles, repositories, 
										   'why is port required')
		warn("port %s doesn't seem to be required by %s"
			 % (requiredPort.versionedName, self.versionedName))

	def cleanWorkDirectory(self):
		"""Clean the working directory"""

		if os.path.exists(self.workDir):
			print 'Cleaning work directory...'
			shutil.rmtree(self.workDir)
				
	def downloadSource(self):
		"""Fetch the source archives and validate their checksum"""

		for source in self.sources:
			source.fetch(self)
			source.validateChecksum(self)

	def unpackSource(self):
		"""Unpack the source archive(s)"""

		for source in self.sources:
			source.unpack(self)

	def patchSource(self):
		"""Apply the Haiku patches to the source(s)"""

		patched = False
		for source in self.sources:
			if source.patch(self):
				patched = True

		# Run PATCH() function in recipe, if defined.
		if Phase.PATCH in self.definedPhases:
			if getOption('patchFilesOnly'):
				print 'Skipping patch function ...'
				return
			
			# Check to see if the patching phase  has already been executed.
			if self.checkFlag('patch') and not getOption('force'):
				return

			try:			
				print 'Running patch function ...'
				self._doRecipeAction(Phase.PATCH, self.sourceDir)
				for source in self.sources:
					source.commitPatchPhase()
				self.setFlag('patch')
			except:
				# Don't leave behind half-patched sources.
				if patched:
					for source in self.sources:
						source.reset()
				raise

	def extractPatchset(self):
		"""Extract patchsets from all sources"""

		s = 1
		for source in self.sources:
			if s == 1:
				patchSetFileName = self.name + '-' + self.version + '.patchset'
				archPatchSetFileName = (self.name + '-' + self.version + '-'
										+ self.targetArchitecture 
										+ '.patchset')
			else:
				patchSetFileName = (self.name + '-' + self.version + '-source' 
									+ str(s) + '.patchset')
				archPatchSetFileName = (self.name + '-' + self.version + '-'
										+ self.targetArchitecture + '-source'
										+ str(s) + '.patchset')
			patchSetFilePath = self.patchesDir + '/' + patchSetFileName
			archPatchSetFilePath = self.patchesDir + '/' + archPatchSetFileName
			source.extractPatchset(patchSetFilePath, archPatchSetFilePath)
			s += 1
				
	def build(self, packagesPath, makePackages, hpkgStoragePath):
		"""Build the port and collect the resulting package"""

		# reset build flag if recipe is newer (unless that's prohibited)
		if (not getOption('preserveFlags') and self.checkFlag('build')
			and (os.path.getmtime(self.recipeFilePath)
				 > os.path.getmtime(self.workDir + '/flag.build'))):
			print 'unsetting build flag, as recipe is newer'
			self.unsetFlag('build')

		# Delete and re-create a couple of directories
		directoriesToCreate = [	
			self.packageInfoDir, self.packagingBaseDir, 
			self.buildPackageDir, self.hpkgDir 
		]
		directoriesToRemove = [ 
			directory for directory in directoriesToCreate 
			if os.path.exists(directory)
		]
		if directoriesToRemove:
			print 'Cleaning up remains of last build ...'
			for directory in directoriesToRemove:
				shutil.rmtree(directory, True)
		for directory in directoriesToCreate:
			os.mkdir(directory)
		for package in self.packages:
			os.mkdir(package.packagingDir)
			package.prepopulatePackagingDir(self)

		requiredPackages = self._getPackagesRequiredForBuild(packagesPath)

		self.policy.setPort(self, requiredPackages)

		self.requiresUpdater = RequiresUpdater(self.packages, requiredPackages,
			not globalConfiguration['IS_CROSSBUILD_REPOSITORY'])

		if buildPlatform.usesChroot():
			# setup chroot and keep it while executing the actions
			chrootEnvVars = {
				'packages': '\n'.join(requiredPackages), 
				'recipeFile': self.preparedRecipeFile,
				'targetArchitecture': self.targetArchitecture,
			}
			if globalConfiguration['IS_CROSSBUILD_REPOSITORY']:
				chrootEnvVars['crossSysrootDir'] \
					= self.workDir + self.shellVariables['crossSysrootDir']
			with ChrootSetup(self.workDir, chrootEnvVars) as chrootSetup:
				if not getOption('quiet'):
					print 'chroot has these packages active:'
					for package in sorted(requiredPackages):
						print '\t' + package
						
				pid = os.fork()
				if pid == 0:
					# child, enter chroot and execute the build
					try:
						os.chroot(self.workDir)
						self._adjustToChroot()
						if getOption('enterChroot'):
							self._openShell()
						else:
							self._executeBuild(makePackages)
					except:
						if not getOption('enterChroot'):
							traceback.print_exc()
							os._exit(1)
					os._exit(0)

				# parent, wait on child
				try:
					childStatus = os.waitpid(pid, 0)[1]
					if not getOption('enterChroot'):
						if childStatus != 0:
							self.unsetFlag('build')
							sysExit('Build has failed - stopping.')
							
						# tell the shell scriptlets that the build has succeeded
						chrootSetup.buildOk = True
				except KeyboardInterrupt:
					if pid > 0:
						print '*** interrupted - stopping child process'
						try: 
							os.kill(pid, signal.SIGINT)
							os.waitpid(pid, 0)
						except:
							pass
						print '*** child stopped'
						
		else:
			self._executeBuild(makePackages)

		if makePackages and not getOption('enterChroot'):
			# move all created packages into packages folder
			for package in self.packages:
				packageFile = self.hpkgDir + '/' + package.hpkgName
				if os.path.exists(packageFile):
					if not buildPlatform.usesChroot():
						warn('not grabbing ' + package.hpkgName
							 + ', as it has not been built in a chroot.')
						continue
					print('grabbing ' + package.hpkgName 
						  + ' and putting it into ' + hpkgStoragePath)
					os.rename(packageFile,
							  hpkgStoragePath + '/' + package.hpkgName)

		if os.path.exists(self.hpkgDir):
			os.rmdir(self.hpkgDir)
			
	def setFlag(self, name, index = '1'):
		if index == '1':
			touchFile('%s/flag.%s' % (self.workDir, name))
		else:
			touchFile('%s/flag.%s-%s' % (self.workDir, name, index))

	def unsetFlag(self, name, index = '1'):
		if index == '1':
			flagFile = '%s/flag.%s' % (self.workDir, name)
		else:
			flagFile = '%s/flag.%s-%s' % (self.workDir, name, index)
			
		if os.path.exists(flagFile):
			os.remove(flagFile)

	def checkFlag(self, name, index = '1'):
		if index == '1':
			return os.path.exists('%s/flag.%s' % (self.workDir, name))

		return os.path.exists('%s/flag.%s-%s' % (self.workDir, name, index))

	def test(self):
		"""Test the port"""
		
		# TODO!

	def _updateShellVariablesFromRecipe(self):
		"""Fill dictionary with variables that will be inherited to the shell
		   when executing recipe actions
		"""
		self._updateShellVariables(False)

	def _updateShellVariables(self, forParsing):
		"""Fill dictionary with variables that will be inherited to the shell
		   when executing recipe actions repectively for parsing the recipe.
		   If forParsing is True, only a subset of variables is set and some
		   others need reevaluation in the shell script after the revision is
		   known.
		"""
		if forParsing:
			revision = '$REVISION'
			fullVersion = self.version + '-' + revision
			revisionedName = self.name + '-' + fullVersion
		else:
			revision = self.revision
			fullVersion = self.fullVersion
			revisionedName = self.revisionedName

		self.shellVariables.update({
			'portRevision': revision,
			'portFullVersion': fullVersion,
			'portRevisionedName': revisionedName,
			'portDir': '/port',
		})

		if not forParsing:
			for source in self.sources:
				if source.index == '1':
					sourceDirKey = 'sourceDir'
				else:
					sourceDirKey = 'sourceDir' + source.index
				self.shellVariables[sourceDirKey] = source.sourceDir

		relativeConfigureDirs = {
			'dataDir':			'data',
			'dataRootDir':		'data',
			'binDir':			'bin',
			'sbinDir':			'bin',
			'libDir':			'lib',
			'includeDir':		'develop/headers',
			'oldIncludeDir':	'develop/headers',
			'docDir':			'documentation/packages/' + self.name,
			'infoDir':			'documentation/info',
			'manDir':			'documentation/man',
			'libExecDir':		'lib',
			'sharedStateDir':	'var',
			'localStateDir':	'var',
			# sysconfdir is only defined in configDirs below, since it is not
			# necessarily below prefix
		}

		# Note: Newer build systems also support the following options. Their
		# default values are OK for us for now:
		# --localedir=DIR         locale-dependent data [DATAROOTDIR/locale]
		# --htmldir=DIR           html documentation [DOCDIR]
		# --dvidir=DIR            dvi documentation [DOCDIR]
		# --pdfdir=DIR            pdf documentation [DOCDIR]
		# --psdir=DIR             ps documentation [DOCDIR]

		portPackageLinksDir = (buildPlatform.findDirectory(
				'B_PACKAGE_LINKS_DIRECTORY')
			+ '/' + revisionedName)
		self.shellVariables['portPackageLinksDir'] = portPackageLinksDir

		prefix = portPackageLinksDir + '/.self'

		configureDirs = {
			'prefix':		prefix,
			'sysconfDir':	portPackageLinksDir + '/.settings',
		}

		for name, value in relativeConfigureDirs.iteritems():
			relativeName = 'relative' + name[0].upper() + name[1:]
			self.shellVariables[relativeName] = value
			configureDirs[name] = prefix + '/' + value

		self.shellVariables.update(configureDirs)

		# add one more variable containing all the dir args for configure:
		self.shellVariables['configureDirArgs'] \
			= ' '.join('--%s=%s' % (k.lower(), v)
					   for k, v in configureDirs.iteritems())

		# add another one with the list of possible variables
		self.shellVariables['configureDirVariables'] \
			= ' '.join(configureDirs.iterkeys())

		# Add variables for other standard directories. Consequently, we should
		# use finddir to get them (also for the configure variables above), but
		# we want relative paths here.
		relativeOtherDirs = {
			'addOnsDir':		'add-ons',
			'appsDir':			'apps',
			'debugInfoDir':		'develop/debug',
			'developDir':		'develop',
			'developDocDir':	'develop/documentation/'  + self.name,
			'developLibDir':	'develop/lib',
			'documentationDir':	'documentation',
			'fontsDir':			'data/fonts',
			'postInstallDir':	'boot/post-install',
			'preferencesDir':	'preferences',
			'settingsDir':		'settings',
		}

		for name, value in relativeOtherDirs.iteritems():
			relativeName = 'relative' + name[0].upper() + name[1:]
			self.shellVariables[relativeName] = value
			self.shellVariables[name] = prefix + '/' + value

	def _prepareRepositories(self, workRepositoryPath, prereqRepositoryPath, 
							 repositoryPath, packagesPath):
		"""Resolve any other ports that need to be built before this one.
		
		   In order to do so, we first determine the prerequired packages for
		   the build, for which packages from outside the haikuports-tree may 
		   be considered. A temporary folder is then populated with only these
		   prerequired packages and then all the build requirements of this
		   port are determined with only the haikuports repository, the already
		   built packages and the repository of prerequired packages active.
		   This ensures that any build requirements a port may have that can not 
		   be fulfilled from within the haikuports tree will be raised as an 
		   error here.
		   
		   If requiredPort has been given, remove the package-infos for that
		   port in order to find out which package is pulling in that port as a 
		   dependency of this port."""

		# First create a work-repository by symlinking all package-infos from
		# the haikuports-repository - we need to overwrite the package-infos
		# for this port, so we do that in a private directory.
		symlinkGlob(repositoryPath + '/*.PackageInfo', workRepositoryPath)
		
		# For each package, generate a PackageInfo-file containing only the 
		# prerequirements for building the package and no own provides (if a
		# port prerequires itself, we want to pull in the real package from the
		# build machine)
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = workRepositoryPath + '/' + package.packageInfoName
			package.generatePackageInfoWithoutProvides(packageInfoFile, 					
													   [ 'BUILD_PREREQUIRES' ], 
													   self.buildArchitecture)
			packageInfoFiles.append(packageInfoFile)
		
		# determine the prerequired packages, allowing build machine packages, 
		# but leave out system packages, as those are irrelevant.
		repositories = [ packagesPath, workRepositoryPath,
			buildPlatform.findDirectory('B_COMMON_PACKAGES_DIRECTORY'),
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY') ]
		prereqPackages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'prerequired ports')
		prereqPackages = [ 
			package for package in prereqPackages 
			if not package.startswith(
				buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))
		]

		# Populate a directory with those prerequired packages.
		symlinkFiles(prereqPackages, prereqRepositoryPath)

		# For each package, generate a PackageInfo-file containing only the 
		# immediate  requirements for building the package:
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = workRepositoryPath + '/' + package.packageInfoName
			package.generatePackageInfoWithoutProvides(packageInfoFile, 
				[ 'BUILD_REQUIRES' ], self.buildArchitecture)
			packageInfoFiles.append(packageInfoFile)

		return packageInfoFiles

	def _getPackagesRequiredForBuild(self, packagesPath):
		"""Determine the set of packages that must be linked into the 
		   build environment (chroot) for the build stage"""
		
		# For each package, generate a PackageInfo-file containing only the 
		# prerequirements for building the package and no own provides (if a
		# port prerequires itself, we want to pull in the real package from the
		# build machine)
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = (package.packageInfoDir + '/' 
							   + package.packageInfoName)
			package.generatePackageInfoWithoutProvides(
				packageInfoFile, 
				[ 'BUILD_PREREQUIRES', 'SCRIPTLET_PREREQUIRES' ],
				self.buildArchitecture)
			packageInfoFiles.append(packageInfoFile)
		
		# Determine the prerequired packages, allowing build machine packages, 
		# but leave out system packages, as they will be linked into the chroot
		# anyway.
		repositories = [ packagesPath,
			buildPlatform.findDirectory('B_COMMON_PACKAGES_DIRECTORY'),
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY') ]
		prereqPackages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'prerequired packages for build')
		prereqPackages = [ 
			package for package in prereqPackages
			if not package.startswith(
				buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))
		]

		# Populate a directory with those prerequired packages.
		prereqRepositoryPath = self.workDir + '/prereq-repository'
		symlinkFiles(prereqPackages, prereqRepositoryPath)

		# For each package, create a package-info that contains both the
		# prerequired and required packages for the build:
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = (package.packageInfoDir + '/' 
							   + package.packageInfoName)
			package.generatePackageInfoWithoutProvides(
				packageInfoFile, 
				[ 'BUILD_REQUIRES', 'BUILD_PREREQUIRES', 
				  'SCRIPTLET_PREREQUIRES' ], self.buildArchitecture)
			packageInfoFiles.append(packageInfoFile)

		# Determine the build requirements.
		repositories = [ packagesPath, prereqRepositoryPath, 
			buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY') ]
		packages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'required packages for build')

		# Filter out system packages, they will be linked into the chroot
		# anyway.
		return [ 
			package for package in packages 
			if not package.startswith(
				buildPlatform.findDirectory('B_SYSTEM_PACKAGES_DIRECTORY'))
		]

	def _executeBuild(self, makePackages):
		"""Executes the build stage and creates all declared packages"""

		# create all build packages (but don't activate them yet)
		for package in self.packages:
			package.createBuildPackage()

		self._doBuildStage()

		if makePackages:
			self._makePackages()
		for package in self.packages:
			package.removeBuildPackage()

	def _adjustToChroot(self):
		"""Adjust directories to chroot()-ed environment"""
		
		for source in self.sources:
			source.adjustToChroot(self)

		for package in self.allPackages:
			package.adjustToChroot()

		# unset directories which can't be reached from inside the chroot
		self.baseDir = None
		self.downloadDir = None
		
		# the recipe file has a fixed same name in the chroot
		self.preparedRecipeFile = '/port.recipe'
		self.recipeFilePath = '/port.recipe'

		# adjust all relevant directories
		pathLengthToCut = len(self.workDir)
		self.sourceDir = self.sourceDir[pathLengthToCut:]
		self.sourceBaseDir = self.sourceBaseDir[pathLengthToCut:]
		self.buildPackageDir = self.buildPackageDir[pathLengthToCut:]
		self.packagingBaseDir = self.packagingBaseDir[pathLengthToCut:]
		self.hpkgDir = self.hpkgDir[pathLengthToCut:]
		self.workDir = ''
		self.patchesDir = '/patches'

		# update shell variables, too
		self._updateShellVariablesFromRecipe()
				

	def _doBuildStage(self):
		"""Run the actual build"""
		# activate build package if required at this stage
		if self.recipeKeys['BUILD_PACKAGE_ACTIVATION_PHASE'] == Phase.BUILD:
			for package in self.packages:
				package.activateBuildPackage()
			
		# Check to see if a previous build was already done.
		if self.checkFlag('build') and not getOption('force'):
			print 'Skipping build ...'
			return

		print 'Building ...'
		self._doRecipeAction(Phase.BUILD, self.sourceDir)
		self.setFlag('build')

	def _makePackages(self):
		"""Create all packages suitable for distribution"""

		# Create the settings directory in the packaging directory, if needed.
		# We need to do that, since the .settings link would otherwise point
		# to a non-existing entry and the directory couldn't be made either.
		for package in self.packages:
			settingsDir = package.packagingDir + '/settings'
			if not os.path.exists(settingsDir):
				os.mkdir(settingsDir)

		self._doInstallStage()

		# If the settings directory is still empty, remove it.
		for package in self.packages:
			settingsDir = package.packagingDir + '/settings'
			if not os.listdir(settingsDir):
				os.rmdir(settingsDir)
		
		# For the main package remove certain empty directories. Typically
		# contents is moved from the main package installation directory tree to
		# the packaging directories of sibling packages, which may leave empty
		# directories behind.
		for dirName in [ 'add-ons', 'apps', 'bin', 'data', 'develop',
				'documentation', 'lib', 'preferences' ]:
			dir = self.packagingBaseDir + '/' + self.name + '/' + dirName
			if os.path.exists(dir) and not os.listdir(dir):
				os.rmdir(dir)

		# create hpkg-directory if needed
		if not os.path.exists(self.hpkgDir):
			os.mkdir(self.hpkgDir)

		# make each package
		for package in self.packages:
			package.makeHpkg(self.requiresUpdater)

		# Clean up after ourselves
		shutil.rmtree(self.packagingBaseDir)

	def _doInstallStage(self):
		"""Install the files resulting from the build into the packaging 
		   folder"""

		# activate build package if required at this stage
		if self.recipeKeys['BUILD_PACKAGE_ACTIVATION_PHASE'] == Phase.INSTALL:
			for package in self.packages:
				package.activateBuildPackage()
			
		print 'Collecting files to be packaged ...'
		self._doRecipeAction(Phase.INSTALL, self.sourceDir)

	def _doTestStage(self):
		"""Test the build results"""

		# activate build package if required at this stage
		if self.recipeKeys['BUILD_PACKAGE_ACTIVATION_PHASE'] == Phase.TEST:
			for package in self.packages:
				package.activateBuildPackage()
			
		print 'Testing ...'
		self._doRecipeAction(Phase.TEST, self.sourceDir)

	def _doRecipeAction(self, action, dir):
		"""Run the specified action, as defined in the recipe file"""

		# execute the requested action via a shell ...
		shellVariables = self.shellVariables.copy()
		shellVariables['fileToParse'] = self.preparedRecipeFile
		shellVariables['recipeAction'] = action
		wrapperScript = (getShellVariableSetters(shellVariables)
			+ recipeActionScript)
		self._openShell(['-c', wrapperScript], dir)

	def _openShell(self, params = [], dir = '/'):
		"""Sets up environment and runs a shell with the given parameters"""
		
		# set up the shell environment -- we want it to inherit some of our
		# variables
		shellEnv = filteredEnvironment()
		if globalConfiguration['IS_CROSSBUILD_REPOSITORY']:
			# include cross development tools in path automatically
			shellEnv['PATH'] \
				= '/boot/common/develop/tools/bin:' + shellEnv['PATH']

		# force POSIX locale, as otherwise strange things may happen for some
		# build (e.g. gcc)
		shellEnv['LC_ALL'] = 'POSIX'

		# execute the requested action via a shell ...
		args = [ '/bin/bash' ]
		args += params
		check_call(args, cwd=dir, env=shellEnv)
			
	def _resolveDependenciesViaPkgman(self, packageInfoFiles, repositories,
									  description):
		"""Invoke pkgman to resolve dependencies of one or more package-infos"""

		args = ([ '/bin/pkgman', 'resolve-dependencies' ]
				+ packageInfoFiles + repositories)
		try:
			with open(os.devnull, "w") as devnull:
				output = check_output(args, stderr=devnull)
			return output.splitlines()
		except CalledProcessError:
			try:
				check_call(args)
			except:
				pass
			sysExit(('unable to resolve %s for %s\n'
					 + '\tpackage-infos:\n\t\t%s\n'
					 + '\trepositories:\n\t\t%s\n')
					% (description, self.versionedName, 
					   '\n\t\t'.join(packageInfoFiles),
					   '\n\t\t'.join(repositories)))
