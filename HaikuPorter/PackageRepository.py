# -*- coding: utf-8 -*-
#
# Copyright 2017 Michael Lotz
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import glob
import hashlib
import json
import os
import shutil
import subprocess

from .Configuration import Configuration
from .DependencyResolver import DependencyResolver
from .Options import getOption
from .PackageInfo import PackageInfo
from .Utils import info, prefixLines, sysExit, versionCompare, warn

# -- PackageRepository class --------------------------------------------------

class PackageRepository(object):

	def __init__(self, packagesPath, repository, quiet, verbose):
		self.packagesPath = packagesPath
		if not os.path.exists(self.packagesPath):
			os.mkdir(self.packagesPath)

		self.obsoleteDir = os.path.join(self.packagesPath, '.obsolete')
		if not os.path.exists(self.obsoleteDir):
			os.mkdir(self.obsoleteDir)

		self.architectures = [Configuration.getTargetArchitecture(),
			'any', 'source']

		self.repository = repository
		self.quiet = quiet
		self.verbose = verbose

		self._storageBackendInitialized = False
		self._storageBackend = None

	def prune(self):
		self.obsoletePackagesWithoutPort()
		self.obsoletePackagesNewerThanActiveVersion()
		self.obsoletePackagesWithNewerVersions()

	def packageName(self, packagePath):
		return os.path.basename(packagePath)

	def packagePath(self, packageName):
		return os.path.join(self.packagesPath, packageName)

	def hasPackage(self, packageName):
		return os.path.exists(self.packagePath(packageName))

	def isPackageLocal(self, packagePath):
		if not os.path.exists(packagePath):
			return False

		packageStat = os.stat(packagePath)
		return packageStat.st_size != 0

	@property
	def storageBackend(self):
		if not self._storageBackendInitialized:
			configFilePath = getOption('storageBackendConfig')
			if configFilePath:
				with open(configFilePath, 'r') as configFile:
					config = json.loads(configFile.read())

				backendType = config.get('backend_type')
				if backendType == 's3':
					from .StorageBackendS3 import StorageBackendS3
					self._storageBackend = StorageBackendS3(self.packagesPath,
						config)
				else:
					raise Exception(f'unknown backend type {backendType}')

			self._storageBackendInitialized = True

		return self._storageBackend

	def packageList(self, packageSpec=None):
		if packageSpec is None:
			packageSpec = ''
		else:
			packageSpec += '-'

		packageSpec += '*.hpkg'
		return glob.glob(os.path.join(self.packagesPath, packageSpec))

	def readPackage(self, packagePath, file):
		if self.isPackageLocal(packagePath):
			with open(packagePath, 'rb') as packageFile:
				shutil.copyfileobj(packageFile, file)
			return

		packageName = self.packageName(packagePath)
		if self.storageBackend is not None:
			self.storageBackend.readPackage(packageName, file)
			return

		raise Exception(f'package {packageName} unavailable')

	def writePackage(self, packageName, file):
		packagePath = self.packagePath(packageName)
		temporaryPath = packagePath + '.temp'
		with open(temporaryPath, 'wb') as packageFile:
			shutil.copyfileobj(file, packageFile)

		os.rename(temporaryPath, packagePath)

	def packageInfoList(self, packageSpec=None):
		result = []
		for package in self.packageList(packageSpec):
			try:
				packageInfo = PackageInfo(package)
			except Exception as exception:
				warn('failed to get info of {}: {}'.format(package, exception))
				continue

			if packageInfo.architecture not in self.architectures:
				continue

			result.append(packageInfo)

		return result

	def obsoletePackage(self, path, reason=None):
		packageFileName = self.packageName(path)
		if not self.quiet:
			print('\tobsoleting package {}: {}'.format(packageFileName, reason))

		os.rename(path, os.path.join(self.obsoleteDir, packageFileName))

	def obsoletePackagesForSpec(self, packageSpec, reason=None):
		"""remove all packages for the given packageSpec"""

		for package in self.packageList(packageSpec):
			self.obsoletePackage(package, reason)

	def obsoletePackagesWithoutPort(self):
		"""remove packages that have no corresponding port"""

		for package in self.packageInfoList():
			portName = self.repository.getPortNameForPackageName(package.name)
			activePort = self.repository.getActivePort(portName)
			if not activePort:
				self.obsoletePackage(package.path, 'no port for it exists')

	def obsoletePackagesNewerThanActiveVersion(self):
		"""remove packages newer than what their active port version produces"""

		for package in self.packageInfoList():
			portName = self.repository.getPortNameForPackageName(package.name)
			activePort = self.repository.getActivePort(portName)
			if not activePort:
				continue

			if versionCompare(package.version, activePort.fullVersion) > 0:
				self.obsoletePackage(package.path,
					'newer than active {}'.format(activePort.fullVersion))

	def obsoletePackagesWithNewerVersions(self):
		"""remove all packages where newer version packages are available"""

		newestPackages = dict()
		reason = 'newer version {} available'
		for package in self.packageInfoList():
			if package.name in newestPackages:
				newest = newestPackages[package.name]
				if versionCompare(newest.version, package.version) > 0:
					self.obsoletePackage(package.path,
						reason.format(newest.version))
					continue

				self.obsoletePackage(newest.path,
					reason.format(package.version))

			newestPackages[package.name] = package

	def createPackageRepository(self, outputPath):
		packageRepoCommand = Configuration.getPackageRepoCommand()
		if not packageRepoCommand:
			sysExit('package repo command must be configured or specified')

		repoFile = os.path.join(outputPath, 'repo')
		repoInfoFile = repoFile + '.info'
		if not os.path.exists(repoInfoFile):
			sysExit('repository info file expected at {}'.format(repoInfoFile))

		repoPackagesPath = os.path.join(outputPath, 'packages')
		if not os.path.exists(repoPackagesPath):
			os.mkdir(repoPackagesPath)
		else:
			for package in glob.glob(os.path.join(repoPackagesPath, '*.hpkg')):
				os.unlink(package)

		localPackages = []
		packageList = self.packageInfoList()
		for package in packageList:
			if not self.isPackageLocal(package.path):
				continue

			os.link(package.path,
				os.path.join(repoPackagesPath, self.packageName(package.path)))

			localPackages.append(package.path)

		packageListFile = os.path.join(outputPath, 'package.list')
		packageNameList \
			= [self.packageName(package.path) for package in packageList]
		with open(packageListFile, 'w') as outputFile:
			outputFile.write('\n'.join(packageNameList))

		if not os.path.exists(repoFile):
			if not packageList:
				sysExit('no repo file exists and no packages to create it')

			output = subprocess.check_output([packageRepoCommand, 'create',
					'-v', repoInfoFile, packageList[0].path],
				stderr=subprocess.STDOUT).decode('utf-8')
			info(output)

		if self.storageBackend is not None:
			self._populateStorageBackendPackages(localPackages)

		output = subprocess.check_output([packageRepoCommand, 'update', '-C',
				repoPackagesPath, '-v', '-t', repoFile, repoFile,
				packageListFile], stderr=subprocess.STDOUT).decode('utf-8')
		info(output)

		repoChecksumFile = repoFile + '.sha256'
		self._checksumPackageRepository(repoFile, repoChecksumFile)

		repoSignatureFile = repoFile + '.minisig'
		wasSigned = self._signPackageRepository(repoFile, repoSignatureFile)

		if self.storageBackend is not None:
			extraFiles = [repoInfoFile, repoFile, repoChecksumFile]
			if wasSigned:
				extraFiles.append(repoSignatureFile)

			extraFiles.append(packageListFile)

			self._stubLocalPackages(localPackages)
			self._populateStorageBackendFiles(extraFiles)
			self._pruneStorageBackend(packageNameList)

	def _checksumPackageRepository(self, repoFile, repoChecksumFile):
		"""Create a checksum of the package repository"""
		checksum = hashlib.sha256()
		with open(repoFile, 'rb') as inputFile:
			while True:
				data = inputFile.read(1 * 1024 * 1024)
				if not data:
					break
				checksum.update(data)

		with open(repoChecksumFile, 'w') as outputFile:
			outputFile.write(checksum.hexdigest())

	def _signPackageRepository(self, repoFile, repoSignatureFile):
		"""Sign the package repository if a private key was provided"""
		privateKeyFile = getOption('packageRepositorySignPrivateKeyFile')
		privateKeyPass = getOption('packageRepositorySignPrivateKeyPass')
		if not privateKeyFile and not privateKeyPass:
			info("Warning: unsigned package repository")
			return False

		if not os.path.exists(privateKeyFile):
			sysExit('specified package repo private key file missing!')

		if not os.path.exists(repoFile):
			sysExit('no repo file was found to sign!')

		minisignCommand = Configuration.getMinisignCommand()
		if not minisignCommand:
			sysExit('minisign command missing to sign repository!')

		# minisign -s /tmp/minisign.key -Sm ${ARTIFACT}
		info("signing repository")
		output = subprocess.check_output([minisignCommand,
			'-x', repoSignatureFile, '-s', privateKeyFile, "-Sm", repoFile],
			input=privateKeyPass.encode('utf-8'),
			stderr=subprocess.STDOUT).decode('utf-8')
		info(output)
		return True

	def checkPackageRepositoryConsistency(self):
		"""Check consistency of package repository by dependency solving all
			all packages."""

		repositories = [self.packagesPath]
		systemPackagesDirectory = getOption('systemPackagesDirectory')
		if systemPackagesDirectory:
			repositories.append(systemPackagesDirectory)

		resolver = DependencyResolver(None, ['REQUIRES'], repositories,
			quiet=True)

		for package in self.packageInfoList():
			if self.verbose:
				print('checking package {}'.format(package.path))

			try:
				resolver.determineRequiredPackagesFor([package.path])
			except LookupError as error:
				print('{}:\n{}\n'.format(os.path.relpath(package.path,
						self.packagesPath), prefixLines('\t', str(error))))

	def _populateStorageBackendPackages(self, localPackages):
		for packagePath in localPackages:
			packageName = self.packageName(packagePath)
			info(f'uploading package {packageName} to storage backend')

			with open(packagePath, 'rb') as packageFile:
				self.storageBackend.writePackage(packageName, packageFile)

	def _populateStorageBackendFiles(self, files):
		for filePath in files:
			fileName = os.path.basename(filePath)
			info(f'uploading {fileName} to storage backend')

			with open(filePath, 'rb') as inputFile:
				self.storageBackend.writeFile(fileName, inputFile)

	def _stubLocalPackages(self, localPackages):
		for packagePath in localPackages:
			os.truncate(packagePath, 0)

	def _pruneStorageBackend(self, packageNameList):
		for remotePackage in self.storageBackend.listPackages():
			if remotePackage in packageNameList:
				continue

			info(f'delete package {remotePackage} from storage backend')
			self.storageBackend.deletePackage(remotePackage)
