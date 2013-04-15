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
from HaikuPorter.Package import Package
from HaikuPorter.RecipeAttributes import recipeAttributes
from HaikuPorter.RecipeTypes import Status
from HaikuPorter.ShellScriptlets import (setupChrootScript, 
										 cleanupChrootScript,
										 recipeActionScript)
from HaikuPorter.Utils import check_output, sysExit, systemDir, warn

import hashlib
import os
import re
import shutil
from subprocess import check_call, Popen, CalledProcessError
import tarfile
import time
import traceback
import urllib2
import zipfile


# -- Modules preloaded for chroot ---------------------------------------------
# These modules need to be preloaded in order to avoid problems with python
# trying to dynamically load them inside a chroot environment
from encodings import string_escape


# -- Scoped resource for chroot environments ---------------------------------
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


# -- Scoped resource for a temporarily renamed file --------------------------
class TemporarilyRenamedFile:
	def __init__(self, file):
		self.file = file
		self.fileName = os.path.basename(file)
		self.subDir = None

	def __enter__(self):
		# rename the file
		self.subDir = os.path.dirname(self.file) + '/deactivated'
		if not os.path.exists(self.subDir):
			os.mkdir(self.subDir)
		os.rename(self.file, self.subDir + '/' + self.fileName)
		return self
	
	def __exit__(self, type, value, traceback):
		# restore the original file
		if self.subDir:
			os.rename(self.subDir + '/' + self.fileName, self.file)
			os.rmdir(self.subDir)


# -- A single port with its recipe, allows to execute actions ----------------
class Port:
	def __init__(self, name, version, category, baseDir, globalShellVariables):
		self.name = name
		self.version = version
		self.versionedName = name + '-' + version
		self.category = category			
		self.baseDir = baseDir
		self.architecture = globalShellVariables['architecture']
		self.recipeFilePath \
			= self.baseDir + '/' + self.name + '-' + self.version + '.recipe'
		
		self.packageInfoName = self.versionedName + '.PackageInfo'
		
		self.forceOverride = False
		self.beQuiet = False
		self.avoidChroot = False

		self.revision = None
		self.fullVersion = None
		self.revisionedName = None
		self.buildPackage = None
		self.activeBuildPackage = None

		# build dictionary of variables to inherit to shell
		self.shellVariables = {
			'portName': self.name,
			'portVersion': self.version,
			'portVersionedName': self.versionedName,
		}
		self.shellVariables.update(globalShellVariables)
		
		# Each port creates at least two packages: the main package, which will 
		# share its name with the port), and a source package.
		# If additional packages are declared in the recipe, they will be 
		# added here, later.
		self.packages = {}

		# create full paths for the directories
		self.downloadDir = self.baseDir + '/download'
		self.patchesDir = self.baseDir + '/patches'
		self.workDir = self.baseDir + '/work-' + self.version
		self.sourceDir = self.sourceBaseDir = self.workDir + '/sources'
		self.packagingDir = self.workDir + '/packaging'
		self.hpkgDir = self.workDir + '/hpkg'

	def __enter__(self):
		return self
	
	def __exit__(self, type, value, traceback):
		pass

	def parseRecipeFile(self):
		"""Parse the recipe-file of the specified port"""
		self.validateRecipeFile()

		# set default values when not provided
		for key in recipeAttributes.keys():
			if key not in self.recipeKeys:
				self.recipeKeys[key] = recipeAttributes[key]['default']
				
		# initialize variables that depend on the recipe revision
		self.revision = str(self.recipeKeys['REVISION'])
		self.fullVersion = self.version + '-' + self.revision
		self.revisionedName = self.name + '-' + self.fullVersion

		self.packages[''] = Package(self.name, 
									self.revisionedName + '-' 
									+ self.architecture + '.hpkg')
		#self.packages['source'] = Package(self.name, 
		#								  self.revisionedName + '-source.hpkg')

		# If a SOURCE_DIR was specified, adjust the default
		if self.recipeKeys['SOURCE_DIR']:
			self.sourceDir = (self.sourceBaseDir + '/' + 
							  self.recipeKeys['SOURCE_DIR'])

		# set up the complete list of variables we'll inherit to the shell
		# when executing a recipe action
		self._updateShellVariablesFromRecipe()

		# for key in self.recipeKeys:
		#	 print key + " = " + str(self.recipeKeys[key])

	def validateRecipeFile(self):
		"""Validate the syntax and contents of the recipe file"""
		
		if not os.path.exists(self.recipeFilePath):
			sysExit(self.name + ' version ' + self.version + ' not found.')

		recipeConfig = ConfigParser(self.recipeFilePath, recipeAttributes, 
							  		self.shellVariables)
		self.recipeKeys = recipeConfig.getEntries()

		# check whether all required values are present
		for key in recipeAttributes.keys():
			if key not in self.recipeKeys and recipeAttributes[key]['required']:
				sysExit("Required value '" + key + "' not present (in %s)" 
						% self.recipeFilePath)

		# The summary must be a single line of text, preferably not exceeding
		# 70 characters in length
		if '\n' in self.recipeKeys['SUMMARY']:
			sysExit('SUMMARY must be a single line of text (%s).' 
					% self.recipeFilePath)
		if len(self.recipeKeys['SUMMARY']) > 70:
			warn('SUMMARY exceeds 70 chars (in %s)' % self.recipeFilePath)

		# Check for a valid license file
		if 'LICENSE' in self.recipeKeys:
			fileList = []
			recipeLicense = self.recipeKeys['LICENSE']
			for item in recipeLicense:
				dirname = systemDir['B_SYSTEM_DIRECTORY'] + '/data/licenses'
				haikuLicenseList = fileList = os.listdir(dirname)
				if item not in fileList:
					fileList = []
					dirname \
						= os.path.dirname(self.recipeFilePath) + '/licenses'
					if os.path.exists(dirname):
						for filename in os.listdir(dirname):
							fileList.append(filename)
				if item not in fileList:
					haikuLicenseList.sort()
					sysExit(('No match found for License %s \n' % item) + '\n'
							+ 'Valid license filenames included with Haiku '
							+ 'are:\n\n' + '\n'.join(haikuLicenseList))

		if 'LICENSE' not in self.recipeKeys or not self.recipeKeys['LICENSE']:
			warn('No LICENSE found (in %s)' % self.recipeFileName)

		if ('COPYRIGHT' not in self.recipeKeys 
			or not self.recipeKeys['COPYRIGHT']):
			warn('No COPYRIGHT found (in %s)' % self.recipeFileName)

	def printDescription(self):
		"""Show port description"""
		print '*' * 80
		print 'SUMMARY: %s' % self.recipeKeys['SUMMARY']
		print 'DESCRIPTION: %s' % self.recipeKeys['DESCRIPTION']
		print 'HOMEPAGE: %s' % self.recipeKeys['HOMEPAGE']
		print '*' * 80

	def getStatusOnCurrentArchitecture(self):
		"""Return the status of this port on the current architecture"""
		if self.architecture in self.recipeKeys['ARCHITECTURES']:
			return self.recipeKeys['ARCHITECTURES'][self.architecture]
		return Status.UNSUPPORTED
	
	def resolveBuildDependencies(self, repositoryPath, packagesPath):
		"""Resolve any other ports that need to be built before this one"""

		# create work dir if needed
		if not os.path.exists(self.workDir):
			os.makedirs(self.workDir)

		shadowedPackageInfo = repositoryPath + '/' + self.packageInfoName
		with TemporarilyRenamedFile(shadowedPackageInfo):
			# Generate a PackageInfo-file containing only the immediate 
			# requirements for building this port:
			packageInfoFile = self.workDir + '/.PackageInfo'
			self._generatePackageInfo(packageInfoFile, 
									  [ 'BUILD_REQUIRES' ], 
									  True)

			try:
				output = check_output([
					'/bin/pkgman', 'resolve-dependencies', 
					packageInfoFile, packagesPath, repositoryPath,
					systemDir['B_COMMON_PACKAGES_DIRECTORY'], 
					systemDir['B_SYSTEM_PACKAGES_DIRECTORY']])
				return output.splitlines()
			except CalledProcessError:
				sysExit('unable to resolve dependencies for ' 
						+ self.versionedName)

	def writePackageInfoIntoRepository(self, repositoryPath):
		"""Write the PackageInfo-file into the repository"""

		if not self.revision:
			self.parseRecipeFile()
			
		packageInfoFile = repositoryPath + '/' + self.packageInfoName
		self._generatePackageInfo(packageInfoFile, 
								  [ 'BUILD_REQUIRES', 'REQUIRES' ], True)
					
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

				self.src_local = src_uri[src_uri.rindex('/') + 1:]
				fp = self.downloadDir + '/' + self.src_local
				if os.path.isfile(fp):
					print 'Skipping download ...'
					return
				else:
					# create download dir and cd into it
					if not os.path.exists(self.downloadDir):
						os.mkdir(self.downloadDir)

					os.chdir(self.downloadDir)

					print '\nDownloading: ' + src_uri
					check_call(['wget', '-c', '--tries=3', src_uri])

					# succesfully downloaded source archive
					return
			except Exception:
				warn('Download error, trying next location.')

		# failed to fetch source
		sysExit('Failed to download source package from all locations.')

	def checkoutSource(self, uri):
		"""Parse the URI and execute the appropriate command to check out the
		   source.
		"""
		if self.checkFlag('checkout') and not self.forceOverride:
			print 'Source already checked out. Skipping ...'
			return

		# If the work dir exists we need to clean it out
		if os.path.exists(self.workDir):
			shutil.rmtree(self.workDir)

		print 'Source checkout: ' + uri

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
		# TODO improve the regex above to fallback to this pattern
		if not type:
			m = re.match("^(\w*).*$", real_uri)
			if m:
				type = m.group(1)

		if not type:
			sysExit("Couldn't parse repository type from URI " + real_uri)

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
		else:
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
		if self.recipeKeys['CHECKSUM_MD5']:
			print 'Checking MD5 checksum of download ...'
			h = hashlib.md5()
			f = open(self.downloadDir + '/' + self.src_local, 'rb')
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
		if self.checkFlag('unpack') and not self.forceOverride:
			print 'Skipping unpack ...'
			return

		# unpack source archive
		print 'Unpacking ' + self.src_local
		archiveFullPath = self.downloadDir + '/' + self.src_local
		if tarfile.is_tarfile(archiveFullPath):
			tf = tarfile.open(self.downloadDir + '/' + self.src_local, 'r')
			tf.extractall(self.sourceBaseDir)
			tf.close()
		elif zipfile.is_zipfile(archiveFullPath):
			zf = zipfile.ZipFile(self.downloadDir + '/' + self.src_local, 'r')
			zf.extractall(self.sourceBaseDir)
			zf.close()
		elif archiveFullPath.split('/')[-1].split('.')[-1] == 'xz':
			Popen(['xz', '-d', '-k', archiveFullPath]).wait()
			tar = archiveFullPath[:-3]
			if tarfile.is_tarfile(tar):
				tf = tarfile.open(tar, 'r')
				tf.extractall(self.sourceBaseDir)
				tf.close()
		else:
			sysExit('Unrecognized archive type in file ' + self.src_local)

		self.setFlag('unpack')

	def patchSource(self):
		"""Apply the Haiku patches to the source directory"""
		# Check to see if the patch was already applied to the source.
		if self.checkFlag('patch') and not self.forceOverride:
			return

		patchFilePath = self.patchesDir + '/' + self.name + '-'\
			 + self.version + '.patch'
		if os.path.exists(patchFilePath):
			print 'Patching ...'
			check_call(['patch', '-p0', '-i ', patchFilePath], 
					   cwd=self.sourceBaseDir)
		else:
			print 'No patching required'
		self.setFlag('patch')

	def build(self, packagesPath, makePackages):
		"""Build the port and collect the resulting package"""

		packageInfoFile = self.workDir + '/.PackageInfo'
		self._generatePackageInfo(packageInfoFile, 
								  [ 'BUILD_REQUIRES', 'BUILD_PREREQUIRES' ], 
								  True, True)

		requiredPackages = self._getPackagesRequiredForBuild(packageInfoFile, 
															 packagesPath)

		if self.avoidChroot:
			self._executeBuild(makePackages)
		else:
			# setup chroot and keep it while executing the actions
			with ChrootSetup(self.workDir, requiredPackages, 
							 self.recipeFilePath) as chrootSetup:
				if not self.beQuiet:
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

		if makePackages:
			# move all created packages into packages folder
			for key in sorted(self.packages.keys()):
				package = self.packages[key]
				packageFile = self.hpkgDir + '/' + package.fileName
				if os.path.exists(packageFile):
					if self.avoidChroot:
						warn('not grabbing ' + package.fileName
							 + ', as it has not been built in a chroot.')
						continue
					print 'grabbing ' + package.fileName
					os.rename(packageFile,
							  packagesPath + '/' + package.fileName)

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

	def _getPackagesRequiredForBuild(self, packageInfoFile, packagesPath):
		"""Determine the set of packages that must be linked into the 
		   build environment (chroot) for the build stage"""
		
		try:
			args = ['/bin/pkgman', 'resolve-dependencies', 
					packageInfoFile, packagesPath,
					systemDir['B_COMMON_PACKAGES_DIRECTORY'], 
					systemDir['B_SYSTEM_PACKAGES_DIRECTORY']]
			output = check_output(args)
			packages = output.splitlines()
			return [ 
				package for package in packages 
				if not package.startswith(
					systemDir['B_SYSTEM_PACKAGES_DIRECTORY'])
			]
		except CalledProcessError:
			try:
				output = check_call(args)
			except:
				pass
			sysExit('unable to resolve dependencies for ' + self.versionedName)

	def _executeBuild(self, makePackages):
		"""Executes the build stage and creates all declared packages"""
		self._createBuildPackage()
		self._doBuildStage()
		if makePackages:
			for (unusedKey, package) in self.packages.iteritems():
				self._makePackage(package)
		if self.activeBuildPackage and os.path.exists(self.activeBuildPackage):
			os.remove(self.activeBuildPackage)
		if self.buildPackage and os.path.exists(self.buildPackage):
			os.remove(self.buildPackage)

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
		self.packagingDir = self.packagingDir[pathLengthToCut:]
		self.hpkgDir = self.hpkgDir[pathLengthToCut:]
		self.workDir = ''
		self.patchesDir = '/patches'

		# update shell variables, too
		self._updateShellVariablesFromRecipe()
				
	def _doBuildStage(self):
		"""Run the actual build"""
		# activate build package if required at this stage
		if self.recipeKeys['BUILD_PACKAGE_ACTIVATION_PHASE'] == 'BUILD':
			self._activateBuildPackage()
			
		# Check to see if a previous build was already done.
		if self.checkFlag('build') and not self.forceOverride:
			print 'Skipping build ...'
			return

		# Delete and re-create the packaging dir -- the port's build may need
		# to use it.
		if os.path.exists(self.packagingDir):
			shutil.rmtree(self.packagingDir, True)
		os.mkdir(self.packagingDir)

		print 'Building ...'
		self._doRecipeAction('BUILD', self.sourceDir)
		self.setFlag('build')

	def _makePackage(self, package):
		"""Create a package suitable for distribution"""
		print 'Creating distribution package ' + package.fileName + ' ...'

		# recreate empty packaging directory
		shutil.rmtree(self.packagingDir, True)
		os.mkdir(self.packagingDir)
		
		# create hpkg-directory if needed
		if not os.path.exists(self.hpkgDir):
			os.mkdir(self.hpkgDir)

		if os.path.exists('/licenses'):
			shutil.copytree('/licenses', self.packagingDir + '/data/licenses')

		self._doInstallStage()
		
		self._generatePackageInfo(self.packagingDir + '/.PackageInfo', 
								  ['REQUIRES'], self.beQuiet)

		packageFile = self.hpkgDir + '/' + package.fileName
		if os.path.exists(packageFile):
			os.remove(packageFile)
		
		# Create the package
		print 'creating package ' + package.fileName + ' ...'
		os.chdir(self.packagingDir)
		check_call(['package', 'create', packageFile])

		# Clean up after ourselves
		shutil.rmtree(self.packagingDir)

	def _doInstallStage(self):
		"""Install the files resulting from the build into the packaging 
		   folder"""
		# activate build package if required at this stage
		if self.recipeKeys['BUILD_PACKAGE_ACTIVATION_PHASE'] == 'INSTALL':
			self._activateBuildPackage()
			
		print 'Collecting files to be packaged ...'
		self._doRecipeAction('INSTALL', self.sourceDir)

	def _doTestStage(self):
		"""Test the build results"""
		print 'Testing ...'
		self._doRecipeAction('TEST', self.sourceDir)

	def _doRecipeAction(self, action, dir):
		"""Run the specified action, as defined in the recipe file"""
		# set up the shell environment -- we want it to inherit some of our
		# variables
		shellEnv = os.environ
		shellEnv.update(self.shellVariables)

		# execute the requested action via a shell ....
		wrapperScript = recipeActionScript % (self.recipeFilePath, action)
		check_call(['/bin/bash', '-c', wrapperScript], cwd=dir, env=shellEnv)

	def _createBuildPackage(self):
		"""Create and activate the build package"""
		# create a package info for a build package
		buildPackageInfo \
			= self.workDir + '/' + self.revisionedName + '-build-package-info'
		self._generatePackageInfo(
			buildPackageInfo, 
			['REQUIRES', 'BUILD_REQUIRES', 'BUILD_PREREQUIRES'], True)

		# create the build package
		buildPackage \
			= self.workDir + '/' + self.revisionedName + '-build.hpkg'
		cmdlineArgs = ['package', 'create', '-bi', buildPackageInfo, '-I',
					   self.packagingDir, buildPackage]
		if self.beQuiet:
			cmdlineArgs.insert(2, '-q')
		check_call(cmdlineArgs)
		self.buildPackage = buildPackage
		os.remove(buildPackageInfo)

	def _activateBuildPackage(self):
		"""Activate the build package"""
		# activate the build package
		packagesDir = systemDir['B_COMMON_PACKAGES_DIRECTORY']
		activeBuildPackage \
			= packagesDir + '/' + os.path.basename(self.buildPackage)
		if os.path.exists(activeBuildPackage):
			os.remove(activeBuildPackage)
			
		if self.avoidChroot:
			# may have to cross devices, so better use a symlink
			os.symlink(self.buildPackage, activeBuildPackage)
		else:
			# symlinking a package won't work in chroot, but in this
			# case we are sure that the move won't cross devices
			os.rename(self.buildPackage, activeBuildPackage)
		self.activeBuildPackage = activeBuildPackage

	def _generatePackageInfo(self, packageInfoPath, requiresToUse, quiet,
							 fakeEmptyProvides=False):
		"""Create a .PackageInfo file for inclusion in a package"""
		
		with open(packageInfoPath, 'w') as infoFile:
			if fakeEmptyProvides:
				infoFile.write('name\t\t\tfaked_' + self.name + '\n')
			else:
				infoFile.write('name\t\t\t' + self.name + '\n')
			infoFile.write('version\t\t\t' + self.fullVersion + '\n')
			infoFile.write('architecture\t\t' + self.architecture + '\n')
			infoFile.write('summary\t\t\t"' + self.recipeKeys['SUMMARY'] 
						   + '"\n')
	
			infoFile.write('description\t\t"')
			infoFile.write('\n'.join(self.recipeKeys['DESCRIPTION']))
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
				requires += self.recipeKeys[requiresKey]
	
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
	
			# Generate SourceURL lines for all ports, regardless of license.
			# Re-use the download URLs, as specified in the recipe.
			infoFile.write('source-urls {\n')
			uricount = 1
			for src_uri in self.recipeKeys['SRC_URI']:
				if uricount < 2:
					infoFile.write('\t"Download <' + src_uri + '>"\n')
				else:
					infoFile.write('\t"Location ' + str(uricount) + ' <' 
								   + src_uri + '>"\n')
				uricount += 1
	
			# Point directly to the file in subversion.
			recipeurl_base = ('http://ports.haiku-files.org/'
							  + 'svn/haikuports/trunk/' + self.category + '/' 
							  + self.name)
	
			recipeurl = (recipeurl_base + '/' + self.name+ '-' + self.version 
						 + '.recipe')
	
			infoFile.write('\t"Port-file <' + recipeurl + '>"\n')
			patchFilePath = (self.patchesDir + '/' + self.name + '-' 
							 + self.version + '.patch')
			if os.path.exists(patchFilePath):
				patchurl = (recipeurl_base + '/patches/' + self.name + '-'
							+ self.version + '.patch')
				infoFile.write('\t"Patches <' + patchurl + '>"\n')
	
			infoFile.write('}\n')
		
		if not quiet:
			with open(packageInfoPath, 'r') as infoFile:
				infoFileDisplay = infoFile.read()
				print infoFileDisplay

	def _writePackageInfoListByKey(self, infoFile, key, keyword):
		self._writePackageInfoList(infoFile, self.recipeKeys[key], keyword)

	def _writePackageInfoList(self, infoFile, list, keyword):
		if list:
			infoFile.write(keyword + ' {\n')
			for item in list:
				infoFile.write('\t' + item + '\n')
			infoFile.write('}\n')


