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
from HaikuPorter.Utils import (check_output, sysExit, systemDir, unpackArchive, 
							   warn)

import hashlib
import os
import re
import shutil
from subprocess import check_call, CalledProcessError
import traceback
import urllib2


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


# -- Scoped resource for one or more temporarily renamed files ----------------
class TemporarilyRenamedFiles:
	def __init__(self, dir, fileNames):
		self.dir = dir
		self.fileNames = fileNames
		self.subDir = None

	def __enter__(self):
		# rename the file
		self.subDir = self.dir + '/deactivated'
		if not os.path.exists(self.subDir):
			os.mkdir(self.subDir)
		for fileName in self.fileNames:
			os.rename(self.dir + '/' + fileName, self.subDir + '/' + fileName)
		return self
	
	def __exit__(self, type, value, traceback):
		# restore the original file
		if self.subDir:
			for fileName in self.fileNames:
				os.rename(self.subDir + '/' + fileName, 
						  self.dir + '/' + fileName)
			os.rmdir(self.subDir)


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
		
		self.archiveFile = None
		self.checkout = None

		self.patches = []

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
		self.sourceDir = self.sourceBaseDir = self.workDir + '/sources'
		self.packageInfoDir = self.workDir + '/package-infos'
		self.buildPackageDir = self.workDir + '/build-packages'
		self.packagingBaseDir = self.workDir + '/packaging'
		self.hpkgDir = self.workDir + '/hpkgs'

	def __enter__(self):
		return self
	
	def __exit__(self, type, value, traceback):
		pass

	def parseRecipeFile(self):
		"""Parse the recipe-file of the specified port"""
		
		self.recipeKeysByExtension = self.validateRecipeFile()
		self.recipeKeys = {}
		for entries in self.recipeKeysByExtension.values():
			self.recipeKeys.update(entries)

		# initialize variables that depend on the recipe revision
		self.revision = str(self.recipeKeys['REVISION'])
		self.fullVersion = self.version + '-' + self.revision
		self.revisionedName = self.name + '-' + self.fullVersion

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

		# If a SOURCE_DIR was specified, adjust the default
		if self.recipeKeys['SOURCE_DIR']:
			self.sourceDir = (self.sourceBaseDir + '/' + 
							  self.recipeKeys['SOURCE_DIR'])

		# set up the complete list of variables we'll inherit to the shell
		# when executing a recipe action
		self._updateShellVariablesFromRecipe()

	def validateRecipeFile(self):
		"""Validate the syntax and contents of the recipe file"""
		
		if not os.path.exists(self.recipeFilePath):
			sysExit(self.name + ' version ' + self.version + ' not found.')

		recipeConfig = ConfigParser(self.recipeFilePath, recipeAttributes, 
							  		self.shellVariables)
		extensions = recipeConfig.getExtensions()
		
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
					if len(entries[key]) > 70:
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
					else:
						warn('No %s found (in %s)' % (key, self.recipeFileName))

				if baseKey == 'COPYRIGHT':
					if key not in entries or not entries[key]:
						warn('No %s found (in %s)' % (key, self.recipeFileName))

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

		if not self.revision:
			self.parseRecipeFile()
			
		for package in self.packages:
			package.writePackageInfoIntoRepository(repositoryPath)
					
	def resolveBuildDependencies(self, repositoryPath, packagesPath):
		"""Resolve any other ports that need to be built before this one"""

		shadowedPackageInfoNames = [package.packageInfoName 
									for package in self.packages]
		with TemporarilyRenamedFiles(repositoryPath, shadowedPackageInfoNames):
			# For each package, generate a PackageInfo-file containing only the 
			# immediate  requirements for building the package:
			packageInfoFiles = []
			for package in self.packages:
				packageInfoFile = repositoryPath + '/' + package.packageInfoName
				package.generatePackageInfo(packageInfoFile, 
											['BUILD_REQUIRES'], True)
				packageInfoFiles.append(packageInfoFile)

			args = ([ '/bin/pkgman', 'resolve-dependencies' ]
					+ packageInfoFiles
					+ [ packagesPath, repositoryPath,
						systemDir['B_COMMON_PACKAGES_DIRECTORY'], 
						systemDir['B_SYSTEM_PACKAGES_DIRECTORY'] ])
			try:
				print ' '.join(args)
				output = check_output(args)
				return output.splitlines()
			except CalledProcessError:
				try:
					check_call(args)
				except:
					pass
				sysExit('unable to resolve dependencies for ' 
						+ self.versionedName)

	def cleanWorkDirectory(self):
		"""Clean the working directory"""

		if os.path.exists(self.workDir):
			print 'Cleaning work directory...'
			shutil.rmtree(self.workDir)
				
	def downloadSource(self):
		"""Fetch the source archive"""
		
		for src_uri in self.recipeKeys['SRC_URI']:
			# Examine the URI to determine if we need to perform a checkout
			# instead of download
			if re.match('^cvs.*$|^svn.*$|^hg.*$|^git.*$|^bzr.*$|^fossil.*$',
						src_uri):
				self.checkoutSource(src_uri)
				return

			try:
				# Need to make a request to get the actual uri in case it is an
				# http redirect
				uri_request = urllib2.urlopen(src_uri)
				src_uri = uri_request.geturl()

				self.downloadLocalFileName = src_uri[src_uri.rindex('/') + 1:]
				archiveFile = (self.downloadDir + '/' 
							   + self.downloadLocalFileName)
				if os.path.isfile(archiveFile):
					print 'Skipping download ...'
				else:
					# create download dir and cd into it
					if not os.path.exists(self.downloadDir):
						os.mkdir(self.downloadDir)

					os.chdir(self.downloadDir)

					print '\nDownloading: ' + src_uri
					check_call(['wget', '-c', '--tries=3', src_uri])
				
				# successfully downloaded source or it was already there
				self.archiveFile = archiveFile
				return
			except Exception:
				warn('Download error from %s, trying next location.'
					 % src_uri)

		# failed to fetch source
		sysExit('Failed to download source package from all locations.')

	def checkoutSource(self, uri):
		"""Parse the URI and execute the appropriate command to check out the
		   source."""

		# Attempt to parse a URI with a + in it. ex: hg+http://blah
		# If it doesn't find the 'type' it should extract 'real_uri' and 'rev'
		m = re.match('^((?P<type>\w*)\+)?(?P<real_uri>.+?)(#(?P<rev>.+))?$',
					 uri)
		if not m or not m.group('real_uri'):
			sysExit("Couldn't parse repository URI " + uri)

		type = m.group('type')
		real_uri = m.group('real_uri')
		rev = m.group('rev')

		# Attempt to parse a URI without a + in it. ex: svn://blah
		if not type:
			m = re.match("^(\w*).*$", real_uri)
			if m:
				type = m.group(1)

		if not type:
			sysExit("Couldn't parse repository type from URI " + real_uri)

		self.checkout = {
			'type': type,
			'uri': real_uri,
			'rev': rev,
		}

		if self.checkFlag('checkout') and not getOption('force'):
			print 'Source already checked out. Skipping ...'
			return

		# If the work dir exists we need to clean it out
		if os.path.exists(self.workDir):
			shutil.rmtree(self.workDir)

		print 'Source checkout: ' + uri

		# Set the name of the directory to check out sources into
		checkoutDir = self.name + '-' + self.version

		# Start building the command to perform the checkout
		if type == 'cvs':
			# Chop off the leading cvs:// part of the uri
			real_uri = real_uri[real_uri.index('cvs://') + 6:]

			# Extract the cvs module from the uri and remove it from real_uri
			module = real_uri[real_uri.rfind('/') + 1:]
			real_uri = real_uri[:real_uri.rfind('/')]
			checkoutCommand = 'cvs -d' + real_uri + ' co -P'
			if rev:
				# For CVS 'rev' specifies a date
				checkoutCommand += ' -D' + rev
			checkoutCommand += ' -d ' + checkoutDir + ' ' + module
		elif type == 'svn':
			checkoutCommand \
				= 'svn co --non-interactive --trust-server-cert'
			if rev:
				checkoutCommand += ' -r ' + rev
			checkoutCommand += ' ' + real_uri + ' ' + checkoutDir
		elif type == 'hg':
			checkoutCommand = 'hg clone'
			if rev:
				checkoutCommand += ' -r ' + rev
			checkoutCommand += ' ' + real_uri + ' ' + checkoutDir
		elif type == 'bzr':
			# http://doc.bazaar.canonical.com/bzr-0.10/bzr_man.htm#bzr-branch-from-location-to-location
			checkoutCommand = 'bzr checkout --lightweight'
			if rev:
				checkoutCommand += ' -r ' + rev
			checkoutCommand += ' ' + real_uri + ' ' + checkoutDir
		elif type == 'fossil':
			# http://fossil-scm.org/index.html/doc/trunk/www/quickstart.wiki
			if os.path.exists(checkoutDir + '.fossil'):
				shutil.rmtree(checkoutDir + '.fossil')
			checkoutCommand = 'fossil clone ' + real_uri
			checkoutCommand += ' ' + checkoutDir + '.fossil'
			checkoutCommand += ' && '
			checkoutCommand += 'mkdir -p ' + checkoutDir
			checkoutCommand += ' && '
			checkoutCommand += 'fossil open ' + checkoutDir + '.fossil'
			if rev:
				checkoutCommand += ' ' + rev
		else:	# assume git
			self.checkout['type'] = 'git'
			# TODO Skip the initial checkout if a rev is specified?
			checkoutCommand = 'git clone %s %s' % (real_uri, checkoutDir)
			if rev:
				checkoutCommand += (' && cd %s'
									' && git checkout %s' % (checkoutDir, rev))

		# create the source-base dir
		if not os.path.exists(self.sourceBaseDir):
			os.makedirs(self.sourceBaseDir)

		check_call(checkoutCommand, shell=True, cwd=self.sourceBaseDir)

		# Set the 'checkout' flag to signal that the checkout is complete
		# This also tells haikuporter not to attempt an unpack step
		self.setFlag('checkout')

	def checksumSource(self):
		"""Make sure that the MD5-checksum matches the expectations"""

		if self.recipeKeys['CHECKSUM_MD5']:
			print 'Checking MD5 checksum of download ...'
			h = hashlib.md5()
			f = open(self.downloadDir + '/' + self.downloadLocalFileName, 'rb')
			while True:
				d = f.read(16384)
				if not d:
					break
				h.update(d)
			f.close()
			if h.hexdigest() != self.recipeKeys['CHECKSUM_MD5']:
				sysExit('Expected: ' + self.recipeKeys['CHECKSUM_MD5'] + '\n'
						+ 'Found: ' + h.hexdigest())
		else:
			# The checkout flag only gets set when a source checkout is 
			# performed. If it exists we don't need to warn about the missing 
			# recipe field
			if not self.checkFlag('checkout'):
				warn('CHECKSUM_MD5 key not found in recipe file.')

	def unpackSource(self):
		"""Unpack the source archive (into the work directory)"""

		# If the source came from a vcs there is no unpack step
		if self.checkFlag('checkout'):
			return

		# create source-base dir
		if not os.path.exists(self.sourceBaseDir):
			os.makedirs(self.sourceBaseDir)

		# Check to see if the source archive was already unpacked.
		if self.checkFlag('unpack') and not getOption('force'):
			print 'Skipping unpack ...'
			return

		# unpack source archive
		print 'Unpacking ' + self.downloadLocalFileName
		unpackArchive(self.archiveFile, self.sourceBaseDir)

		# automatically try to rename archive folders containing '-':
		if not os.path.exists(self.sourceDir):
			maybeSourceDir = self.sourceDir.replace('_', '-')
			if os.path.exists(maybeSourceDir):
				os.rename(maybeSourceDir, self.sourceDir)

		self.setFlag('unpack')

	def patchSource(self):
		"""Apply the Haiku patches to the source directory"""

		patchFilePath = (self.patchesDir + '/' + self.name + '-' + self.version 
						 + '.patch')
		self.patches.append(patchFilePath)
		
		# Check to see if the source has already been patched.
		if self.checkFlag('patch') and not getOption('force'):
			return

		if os.path.exists(patchFilePath):
			print 'Patching ...'
			check_call(['patch', '-p0', '-i', patchFilePath], 
					   cwd=self.sourceBaseDir)
		else:
			print 'No patching required'
		self.setFlag('patch')

	def build(self, packagesPath, makePackages):
		"""Build the port and collect the resulting package"""

		# Delete and re-create a couple of directories
		for directory in [self.packageInfoDir, self.packagingBaseDir, 
						  self.buildPackageDir, self.hpkgDir]:
			if os.path.exists(directory):
				shutil.rmtree(directory, True)
			os.mkdir(directory)
		for package in self.packages:
			os.mkdir(package.packagingDir)
			package.prepopulatePackagingDir(self)
		
		packageInfoFiles = []
		for package in self.packages:
			packageInfoFile = (package.packageInfoDir + '/' 
							   + package.packageInfoName)
			package.generatePackageInfo(packageInfoFile, 
										['BUILD_REQUIRES', 'BUILD_PREREQUIRES'], 
										True, True)
			packageInfoFiles.append(packageInfoFile)

		requiredPackages = self._getPackagesRequiredForBuild(packageInfoFiles, 
															 packagesPath)

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
					print 'grabbing ' + package.hpkgName
					os.rename(packageFile,
							  packagesPath + '/' + package.hpkgName)

	def setFlag(self, name):
		open('%s/flag.%s' % (self.workDir, name), 'w').close()

	def unsetFlag(self, name):
		flagFile = '%s/flag.%s' % (self.workDir, name)
		if os.path.exists(flagFile):
			os.remove(flagFile)

	def checkFlag(self, name):
		return os.path.exists('%s/flag.%s' % (self.workDir, name))

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
			'sourceDir': self.sourceDir,
		})

		# force POSIX locale, as otherwise strange things may happen for some
		# build (e.g. gcc)
		self.shellVariables['LC_ALL'] = 'POSIX'

		prefix = systemDir['B_PACKAGE_LINKS_DIRECTORY'] + '/' \
			+ self.revisionedName + '/.self'
		configureDirs = {
			'prefix': prefix,
			'dataRootDir': prefix + '/data',
			'binDir': prefix + '/bin',
			'sbinDir': prefix + '/bin',
			'libDir': prefix + '/lib',
			'includeDir': prefix + '/develop/headers',
			'sysconfDir': prefix + '/settings',
			'docDir': prefix + '/documentation/packages/' + self.name,
			'infoDir': prefix + '/documentation/info',
			'manDir': prefix + '/documentation/man',
		}
		self.shellVariables.update(configureDirs)

		# add one more variable containing all the dir args for configure:
		self.shellVariables['configureDirArgs'] \
			= ' '.join(['--%s=%s' % (k.lower(), v) 
					   for k, v in configureDirs.iteritems()])

	def _getPackagesRequiredForBuild(self, packageInfoFiles, packagesPath):
		"""Determine the set of packages that must be linked into the 
		   build environment (chroot) for the build stage"""
		
		try:
			args = ([ '/bin/pkgman', 'resolve-dependencies' ]
					+ packageInfoFiles
					+ [ packagesPath,
						systemDir['B_COMMON_PACKAGES_DIRECTORY'], 
						systemDir['B_SYSTEM_PACKAGES_DIRECTORY'] ])
			output = check_output(args)
			packages = output.splitlines()
			return [ 
				package for package in packages 
				if not package.startswith(
					systemDir['B_SYSTEM_PACKAGES_DIRECTORY'])
			]
		except CalledProcessError:
			try:
				check_call(args)
			except:
				pass
			sysExit('unable to resolve dependencies for ' + self.versionedName)

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
				
		for package in self.allPackages:
			package.adjustToChroot()

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

		self._doInstallStage()
		
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
