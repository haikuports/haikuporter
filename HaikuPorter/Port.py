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
from HaikuPorter.Options import getOption
from HaikuPorter.Package import (PackageType, packageFactory)
from HaikuPorter.RecipeAttributes import recipeAttributes
from HaikuPorter.RecipeTypes import Phase, Status
from HaikuPorter.ShellScriptlets import (setupChrootScript, 
										 cleanupChrootScript,
										 recipeActionScript)
from HaikuPorter.Source import Source
from HaikuPorter.Utils import (check_output, naturalCompare, symlinkFiles, 
							   symlinkGlob, sysExit, systemDir, touchFile, warn)

import os
import shutil
from subprocess import check_call, CalledProcessError
import traceback


# -- Modules preloaded for chroot ---------------------------------------------
# These modules need to be preloaded in order to avoid problems with python
# trying to dynamically load them inside a chroot environment
from encodings import string_escape


# -- Scoped resource for chroot environments ----------------------------------
class ChrootSetup:
	def __init__(self, chrootPath, packagesToBeActivated, recipeFilePath):
		self.path = chrootPath
		self.packages = packagesToBeActivated
		self.recipeFile = recipeFilePath
		self.buildOk = False

	def __enter__(self):
		# execute the chroot setup scriptlet via the shell ...
		os.chdir(self.path)
		shellEnv = { 
			'packages': '\n'.join(self.packages), 
			'recipeFile': self.recipeFile, 
		}
		check_call(['/bin/bash', '-c', setupChrootScript], env=shellEnv)
		return self
	
	def __exit__(self, type, value, traceback):
		# execute the chroot cleanup scriptlet via the shell ...
		os.chdir(self.path)
		shellEnv = {}
		if self.buildOk:
			shellEnv['buildOk'] = '1'
		check_call(['/bin/bash', '-c', cleanupChrootScript], env=shellEnv)


# -- A single port with its recipe, allows to execute actions -----------------
class Port:
	def __init__(self, name, version, category, baseDir, globalShellVariables):
		self.name = name
		self.version = version
		self.versionedName = name + '-' + version
		self.category = category			
		self.baseDir = baseDir
		self.currentArchitecture = globalShellVariables['architecture']
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
		}
		self.shellVariables.update(globalShellVariables)
		
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

	def __enter__(self):
		return self
	
	def __exit__(self, type, value, traceback):
		pass

	def parseRecipeFile(self, showWarnings):
		"""Parse the recipe-file of the specified port"""

		# If a patch file named like the port exists, use that as a default
		# for "PATCHES".
		patchFileName = self.name + '-' + self.version + '.patch'
		patchFilePath = self.patchesDir + '/' + patchFileName
		if os.path.exists(patchFilePath):
			self.shellVariables['PATCHES'] = patchFileName
		
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
		for extension in sorted(self.recipeKeysByExtension.keys()):
			keys = self.recipeKeysByExtension[extension]
			if 'NAME_EXTENSION' in keys and keys['NAME_EXTENSION']:
				name = keys['NAME_EXTENSION']
			else:
				if extension:
					name = self.name + '_' + extension
				else:
					name = self.name
			packageType = PackageType.byName(extension)
			package = packageFactory(packageType, name, self, keys)
			self.allPackages.append(package)
			
			status = package.getStatusOnArchitecture(self.currentArchitecture)
			if status == Status.STABLE:
				self.packages.append(package)

		self.sourceDir = self.sources[0].sourceDir

		# set up the complete list of variables we'll inherit to the shell
		# when executing a recipe action
		self._updateShellVariablesFromRecipe()

	def validateRecipeFile(self, showWarnings = False):
		"""Validate the syntax and contents of the recipe file"""
		
		if not os.path.exists(self.recipeFilePath):
			sysExit(self.name + ' version ' + self.version + ' not found.')

		recipeConfig = ConfigParser(self.recipeFilePath, recipeAttributes, 
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
					# value
					if key not in entries:
						attributes = recipeAttributes[baseKey]
						if ('suffix' in attributes
							and extension in attributes['suffix']):
							recipeKeys[baseKey] = (
								baseEntries[baseKey] 
								+ attributes['suffix'][extension])
						else:
							recipeKeys[baseKey] = baseEntries[baseKey]
						continue	# inherited values don't need to be checked
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
							dirname = (systemDir['B_SYSTEM_DIRECTORY'] 
									   + '/data/licenses')
							haikuLicenseList = fileList = os.listdir(dirname)
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
				  % package.getStatusOnArchitecture(self.currentArchitecture))
			print 'ARCHITECTURE: %s' % package.architecture
		print '*' * 80

	def getStatusOnCurrentArchitecture(self):
		"""Return the status of this port on the current architecture"""
		
		if self.allPackages:
			return self.allPackages[0].getStatusOnArchitecture(
				self.currentArchitecture)
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

		# First create a work-repository by symlinking all package-infos from
		# the haikuports-repository - we need to overwrite the package-infos
		# for this port, so we do that in a private directory.
		workRepositoryPath = self.workDir + '/repository'
		symlinkGlob(repositoryPath + '/*.PackageInfo', workRepositoryPath)
		
		# For each package, generate a PackageInfo-file containing only the 
		# prerequirements for building the package and no own provides (if a
		# port prerequires itself, we want to pull in the "host" package)
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = workRepositoryPath + '/' + package.packageInfoName
			package.generatePackageInfoWithoutProvides(packageInfoFile, 
													   ['BUILD_PREREQUIRES'])
			packageInfoFiles.append(packageInfoFile)
		
		# determine the prerequired packages, allowing "host" packages, but
		# filter our system packages, as those are irrelevant.
		repositories = [ packagesPath, workRepositoryPath,
						 systemDir['B_COMMON_PACKAGES_DIRECTORY'], 
						 systemDir['B_SYSTEM_PACKAGES_DIRECTORY'] ]
		prereqPackages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'build prerequirements')
		prereqPackages = [ 
			package for package in prereqPackages 
			if not package.startswith(systemDir['B_SYSTEM_PACKAGES_DIRECTORY'])
		]

		# Populate a directory with those prerequired packages.
		prereqRepositoryPath = self.workDir + '/prereq-repository'
		symlinkFiles(prereqPackages, prereqRepositoryPath)

		# For each package, generate a PackageInfo-file containing only the 
		# immediate  requirements for building the package:
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = workRepositoryPath + '/' + package.packageInfoName
			package.generatePackageInfo(packageInfoFile, 
										['BUILD_REQUIRES'], True)
			packageInfoFiles.append(packageInfoFile)

		# Determine the build requirements, this time only allowing system
		# packages.from the host.
		repositories = [ packagesPath, workRepositoryPath, prereqRepositoryPath,
						 systemDir['B_SYSTEM_PACKAGES_DIRECTORY'] ]
		packages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'build requirements')

		shutil.rmtree(workRepositoryPath)
		shutil.rmtree(prereqRepositoryPath)

		# Filter out system packages, as they are irrelevant.
		return [ 
			package for package in packages 
			if not package.startswith(systemDir['B_SYSTEM_PACKAGES_DIRECTORY'])
		], workRepositoryPath

	def cleanWorkDirectory(self):
		"""Clean the working directory"""

		if os.path.exists(self.workDir):
			print 'Cleaning work directory...'
			shutil.rmtree(self.workDir)
				
	def downloadSource(self):
		"""Fetch the source archives and validate their checksum"""

		for source in self.sources:
			source.download(self)
			source.validateChecksum(self)

	def unpackSource(self):
		"""Unpack the source archive(s)"""

		for source in self.sources:
			source.unpackSource(self)

	def patchSource(self):
		"""Apply the Haiku patches to the source(s)"""

		patched = False
		for source in self.sources:
			if source.patch(self):
				patched = True

		# Run PATCH() function in recipe, if defined.
		if Phase.PATCH in self.definedPhases:
			if getOption('patchFilesOnly'):
				print 'Skipping patching ...'
				# Make sure the half-patched sources aren't considered
				# valid.
				if patched:
					for source in self.sources:
						self.unsetFlag('unpack', source.index)
						self.unsetFlag('checkout', source.index)
				return
			
			# Check to see if the patching phase  has already been executed.
			if self.checkFlag('patch') and not getOption('force'):
				return
			
			print 'Patching ...'
			self._doRecipeAction(Phase.PATCH, self.sourceDir)
			self.setFlag('patch')

	def build(self, packagesPath, makePackages, hpkgStoragePath):
		"""Build the port and collect the resulting package"""

		# reset build flag if recipe is newer (unless that's prohibited)
		if (not getOption('preserveFlags') and self.checkFlag('build')
			and (os.path.getmtime(self.recipeFilePath)
				 > os.path.getmtime(self.workDir + '/flag.build'))):
			print 'unsetting build flag, as recipe is newer'
			self.unsetFlag('build')

		# Delete and re-create a couple of directories
		for directory in [self.packageInfoDir, self.packagingBaseDir, 
						  self.buildPackageDir, self.hpkgDir]:
			if os.path.exists(directory):
				shutil.rmtree(directory, True)
			os.mkdir(directory)
		for package in self.packages:
			os.mkdir(package.packagingDir)
			package.prepopulatePackagingDir(self)

		requiredPackages = self._getPackagesRequiredForBuild(packagesPath)

		if getOption('chroot'):
			# setup chroot and keep it while executing the actions
			with ChrootSetup(self.workDir, requiredPackages, 
							 self.recipeFilePath) as chrootSetup:
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
						self._executeBuild(makePackages)
					except:
						traceback.print_exc()
						os._exit(1)
					os._exit(0)

				# parent, wait on child
				if os.waitpid(pid, 0)[1] != 0:
					self.unsetFlag('build')
					sysExit('Build has failed - stopping.')

				# tell the shell scriptlets that the build has succeeded
				chrootSetup.buildOk = True
		else:
			self._executeBuild(makePackages)

		if makePackages:
			# move all created packages into packages folder
			for package in self.packages:
				packageFile = self.hpkgDir + '/' + package.hpkgName
				if os.path.exists(packageFile):
					if not getOption('chroot'):
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
		self.shellVariables.update({
			'portRevision': self.revision,
			'portFullVersion': self.fullVersion,
			'portRevisionedName': self.revisionedName,
			'portDir': '/port',
		})
		
		for source in self.sources:
			if source.index == '1':
				sourceDirKey = 'sourceDir'
			else:
				sourceDirKey = 'sourceDir' + source.index
			self.shellVariables[sourceDirKey] = source.sourceDir

		# force POSIX locale, as otherwise strange things may happen for some
		# build (e.g. gcc)
		self.shellVariables['LC_ALL'] = 'POSIX'

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

		portPackageLinksDir = (systemDir['B_PACKAGE_LINKS_DIRECTORY'] + '/'
			+ self.revisionedName)
		prefix = portPackageLinksDir + '/.self'

		configureDirs = {
			'prefix':		prefix,
			'sysconfDir':	portPackageLinksDir + '/.settings',
		}
		for name, value in relativeConfigureDirs.iteritems():
			configureDirs[name] = prefix + '/' + value
			relativeName = 'relative' + name[0].upper() + name[1:]
			self.shellVariables[relativeName] = value

		self.shellVariables.update(configureDirs)

		# add one more variable containing all the dir args for configure:
		self.shellVariables['configureDirArgs'] \
			= ' '.join(['--%s=%s' % (k.lower(), v) 
					   for k, v in configureDirs.iteritems()])

		# add another one with the list of possible variable
		self.shellVariables['configureDirVariables'] \
			= ' '.join(configureDirs.iterkeys())

		# Add variables for other standard directories. Consequently, we should
		# use finddir to get them (also for the configure variables above), but
		# we want relative paths here.
		relativeOtherDirs = {
			'addOnsDir':		'add-ons',
			'appsDir':			'apps',
			'developDir':		'develop',
			'developDocDir':	'develop/documentation/'  + self.name,
			'developLibDir':	'develop/lib',
			'documentationDir':	'documentation',
			'fontsDir':			'data/fonts',
			'preferencesDir':	'preferences',
			'settingsDir':		'settings',
		}

		for name, value in relativeOtherDirs.iteritems():
			self.shellVariables[name] = prefix + '/' + value
			relativeName = 'relative' + name[0].upper() + name[1:]
			self.shellVariables[relativeName] = value

		self.shellVariables['portPackageLinksDir'] = portPackageLinksDir

	def _getPackagesRequiredForBuild(self, packagesPath):
		"""Determine the set of packages that must be linked into the 
		   build environment (chroot) for the build stage"""
		
		# For each package, generate a PackageInfo-file containing only the 
		# prerequirements for building the package and no own provides (if a
		# port prerequires itself, we want to pull in the "host" package)
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = (package.packageInfoDir + '/' 
							   + package.packageInfoName)
			package.generatePackageInfoWithoutProvides(packageInfoFile, 
													   ['BUILD_PREREQUIRES'])
			packageInfoFiles.append(packageInfoFile)
		
		# Determine the prerequired packages, allowing "host" packages, but
		# filter out system packages, as they will be linked into the chroot
		# anyway.
		repositories = [ packagesPath,
						 systemDir['B_COMMON_PACKAGES_DIRECTORY'], 
						 systemDir['B_SYSTEM_PACKAGES_DIRECTORY'] ]
		prereqPackages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'build prerequirements')
		prereqPackages = [ 
			package for package in prereqPackages 
			if not package.startswith(systemDir['B_SYSTEM_PACKAGES_DIRECTORY'])
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
			package.generatePackageInfoWithoutProvides(packageInfoFile, 
													   [ 'BUILD_REQUIRES', 
													     'BUILD_PREREQUIRES' ])
			packageInfoFiles.append(packageInfoFile)

		# Determine the build requirements.
		repositories = [ packagesPath, prereqRepositoryPath, 
						 systemDir['B_SYSTEM_PACKAGES_DIRECTORY'] ]
		packages = self._resolveDependenciesViaPkgman(
			packageInfoFiles, repositories, 'build requirements')

		# Filter out system packages, they will be linked into the chroot
		# anyway.
		return [ 
			package for package in packages 
			if not package.startswith(systemDir['B_SYSTEM_PACKAGES_DIRECTORY'])
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
		
		# create hpkg-directory if needed
		if not os.path.exists(self.hpkgDir):
			os.mkdir(self.hpkgDir)

		# make each package
		for package in self.packages:
			package.makeHpkg()

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

		# set up the shell environment -- we want it to inherit some of our
		# variables
		shellEnv = os.environ
		shellEnv.update(self.shellVariables)

		# execute the requested action via a shell ....
		wrapperScript = recipeActionScript % (self.recipeFilePath, action)
		check_call(['/bin/bash', '-c', wrapperScript], cwd=dir, env=shellEnv)

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
