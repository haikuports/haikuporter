from .Utils import sysExit

import json
import logging
import os
import paramiko
import threading
import time


class ScheduledBuild:
	def __init__(self, port, requiredPackageIDs, presentDependencyPackages):
		self.port = port
		self.requiredPackages = presentDependencyPackages
		self.missingPackageIDs = set(requiredPackageIDs)
		self.started = False
		self.lost = False

	@property
	def buildable(self):
		return len(self.missingPackageIDs) == 0

	def packageCompleted(self, package, available):
		packageID = package.versionedName
		if packageID in self.missingPackageIDs:
			if available:
				self.missingPackageIDs.remove(packageID)
				self.requiredPackages.append(package.hpkgName)
			else:
				self.lost = True


class Builder:
	def __init__(self, configFilePath, packagesPath):
		self._loadConfig(configFilePath)
		self.availablePackages = []
		self.packagesPath = packagesPath

		self.logger = logging.getLogger('builders.' + self.name)
		self.logger.setLevel(logging.DEBUG)
		self.formatter = logging.Formatter('%(asctime)s builder '
			+ self.name + ': %(message)s')

	def _loadConfig(self, configFilePath):
		with open(configFilePath, 'r') as configFile:
			self.config = json.loads(configFile.read())

		if not 'name' in self.config:
			raise Exception('missing name in ' + configFilePath)

		self.name = self.config['name']

		if not 'ssh' in self.config:
			raise Exception('missing ssh config for builder ' + self.name)
		if not 'port' in self.config['ssh']:
			self.config['ssh']['port'] = 22
		if not 'user' in self.config['ssh']:
			raise Exception('missing ssh user config for builder ' + self.name)
		if not 'host' in self.config['ssh']:
			raise Exception('missing ssh host config for builder ' + self.name)
		if not 'privateKeyFile' in self.config['ssh']:
			raise Exception('missing ssh privateKeyFile config for builder '
				+ self.name)
		if not os.path.isabs(self.config['ssh']['privateKeyFile']):
			self.config['ssh']['privateKeyFile'] = os.path.join(
				os.path.dirname(configFilePath),
				self.config['ssh']['privateKeyFile'])

		if not 'hostKeyFile' in self.config['ssh']:
			raise Exception('missing ssh hostKeyFile config for builder '
				+ self.name)
		if not os.path.isabs(self.config['ssh']['hostKeyFile']):
			self.config['ssh']['hostKeyFile'] = os.path.join(
				os.path.dirname(configFilePath),
				self.config['ssh']['hostKeyFile'])

		if not 'portstree' in self.config:
			raise Exception('missing portstree config for builder ' + self.name)
		if not 'path' in self.config['portstree']:
			raise Exception('missing portstree path config for builder '
				+ self.name)
		if not 'packagesPath' in self.config['portstree']:
			self.config['portstree']['packagesPath'] \
				= self.config['portstree']['path'] + '/packages'

		if not 'haikuporter' in self.config:
			self.config['haikuporter'] = {}
		if not 'path' in self.config['haikuporter']:
			self.config['haikuporter']['path'] = 'haikuporter'
		if not 'args' in self.config['haikuporter']:
			self.config['haikuporter']['args'] = ''

	def connect(self):
		try:
			self.sshClient = paramiko.SSHClient()
			self.sshClient.load_host_keys(self.config['ssh']['hostKeyFile'])

			print('trying to connect to builder ' + self.name)
			self.sshClient.connect(hostname = self.config['ssh']['host'],
				port = int(self.config['ssh']['port']),
				username = self.config['ssh']['user'],
				key_filename = self.config['ssh']['privateKeyFile'],
				compress = True, allow_agent = False, look_for_keys = False,
				timeout = 10)

			self.sftpClient = self.sshClient.open_sftp()
			self._getAvailablePackages()

			print('connected to builder ' + self.name)
			return True
		except Exception as exception:
			print('failed to connect to builder ' + self.name + ': '
				+ str(exception))
			return False

	def build(self, scheduledBuild, logFile):
		logHandler = logging.FileHandler(logFile)
		logHandler.setFormatter(self.formatter)
		self.logger.addHandler(logHandler)
		buildSuccess = False

		try:
			for requiredPackage in scheduledBuild.requiredPackages:
				if requiredPackage in self.availablePackages:
					continue

				self.logger.info('upload required package ' + requiredPackage
					+ ' to builder')

				self._putFile(os.path.join(self.packagesPath, requiredPackage),
					self.config['portstree']['packagesPath'] + '/'
						+ requiredPackage)

				self.availablePackages.append(requiredPackage)

			self.logger.info('building port '
				+ scheduledBuild.port.versionedName)

			# TODO: We don't actually want to source the build host environment
			# but the one from within the provided Haiku package. This does
			# clash with the manipulation of PATH that is done by haikuporter
			# to support secondary architectures and cross builds. Ideally the
			# shell scriptlet to set up the chroot environment would take over
			# these tasks and would initially source the environment from within
			# the chroot and then do any necessary manipulation.
			command = ('source /boot/system/boot/SetupEnvironment'
				+ ' && cd "' + self.config['portstree']['path']
				+ '" && "' + self.config['haikuporter']['path']
				+ '" --config=haikuports.conf'
				+ ' --no-system-packages --no-dependencies '
				+ self.config['haikuporter']['args'] + ' '
				+ scheduledBuild.port.versionedName)

			self.logger.info('running command: ' + command)

			with self._remoteCommand(command) as output:
				while True:
					line = output.readline()
					if not line:
						break

					self.logger.info(line[:-1])

			for package in scheduledBuild.port.packages:
				self.logger.info('download package ' + package.hpkgName
					+ ' from builder')

				self._getFile(self.config['portstree']['packagesPath'] + '/'
						+ package.hpkgName,
					os.path.join(self.packagesPath, package.hpkgName))

				self.availablePackages.append(package.hpkgName)

			buildSuccess = True

		except Exception as exception:
			self.logger.error('build failed: ' + str(exception))
		finally:
			self.logger.removeHandler(logHandler)

		return buildSuccess

	def _remoteCommand(self, command):
		transport = self.sshClient.get_transport()
		channel = transport.open_session()
		channel.get_pty()
		output = channel.makefile()
		channel.exec_command(command)
		return output

	def _getFile(self, localPath, remotePath):
		self.sftpClient.get(localPath, remotePath)

	def _putFile(self, remotePath, localPath):
		self.sftpClient.put(remotePath, localPath)

	def _listDir(self, remotePath):
		return self.sftpClient.listdir(remotePath)

	def _getAvailablePackages(self):
		for entry in self._listDir(self.config['portstree']['packagesPath']):
			if entry.endswith('.hpkg'):
				self.availablePackages.append(entry)


class BuildMaster:
	def __init__(self, packagesPath):
		self.builders = []
		self.buildThreads = []
		self.builderConfigBaseDir = 'builders'
		self.buildOutputBaseDir = os.path.join('buildmaster', 'output')
		self.buildNumber = 0

		logHandler = logging.FileHandler(
			os.path.join(self.buildOutputBaseDir, 'master.log'))
		logHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))

		self.logger = logging.getLogger('buildMaster')
		self.logger.setLevel(logging.DEBUG)
		self.logger.addHandler(logHandler)

		for fileName in os.listdir(self.builderConfigBaseDir):
			configFilePath = os.path.join(self.builderConfigBaseDir, fileName)
			if not os.path.isfile(configFilePath):
				continue

			builder = None
			try:
				builder = Builder(configFilePath, packagesPath)
			except Exception as exception:
				self.logger.error('failed to add builder from config '
					+ configFilePath + ':' + str(exception))

			if not builder.connect():
				continue

			self.builders.append(builder)
			self.buildThreads.append(None)

		if len(self.builders) == 0:
			sysExit('no builders available')

		self.builderLock = threading.Lock()
		self.semaphore = threading.BoundedSemaphore(value = len(self.builders))
		self.scheduledBuilds = {}
		self.scheduledBuildsLock = threading.Lock()
		self.buildableCondition = threading.Condition()

	def schedule(self, port, requiredPackageIDs, presentDependencyPackages):
		if port.versionedName in self.scheduledBuilds:
			sysExit('scheduling duplicate: ' + port.versionedName)

		self.logger.info('scheduling build of ' + port.versionedName)
		self.scheduledBuilds[port.versionedName] = ScheduledBuild(port,
			requiredPackageIDs, presentDependencyPackages)

	def runBuilds(self):
		while True:
			with self.scheduledBuildsLock:
				done = True
				restart = False
				for scheduledBuildID in self.scheduledBuilds:
					scheduledBuild = self.scheduledBuilds[scheduledBuildID]
					if scheduledBuild.started or scheduledBuild.lost:
						continue

					done = False
					if not scheduledBuild.buildable:
						continue

					scheduledBuild.started = True
					self.scheduledBuildsLock.release()
					self._runBuild(scheduledBuild)
					self.scheduledBuildsLock.acquire()
					restart = True
					break

				if restart:
					continue

				if done:
					break

				self.logger.info('nothing else buildable, waiting for packages')
				with self.buildableCondition:
					self.scheduledBuildsLock.release()
					self.buildableCondition.wait()
					self.scheduledBuildsLock.acquire()

		# wait for all builds to finish
		for i in range(0, len(self.builders)):
			self.semaphore.acquire()

	def _runBuild(self, scheduledBuild):
		self.semaphore.acquire()
		with self.builderLock:
			for i in range(0, len(self.builders)):
				if not self.buildThreads[i]:
					self.buildThreads[i] = threading.Thread(None,
						self._buildThread,
						'build ' + str(self.buildNumber),
						(i, scheduledBuild, self.buildNumber))

					self.buildNumber += 1
					self.buildThreads[i].start()
					break

	def _packagesCompleted(self, packages, available):
		notify = False

		completePackages = [] + packages
		with self.scheduledBuildsLock:
			while len(completePackages) > 0:
				package = completePackages.pop(0)
				self.logger.info('package ' + package.versionedName + ' '
					+ ('became available' if available else 'lost'))

				for scheduledBuildID in self.scheduledBuilds:
					scheduledBuild = self.scheduledBuilds[scheduledBuildID]
					if not scheduledBuild.buildable and not scheduledBuild.lost:
						scheduledBuild.packageCompleted(package, available)
						if scheduledBuild.buildable or scheduledBuild.lost:
							notify = True
							self.logger.info('scheduled build '
								+ scheduledBuildID + ' '
								+ ('became buildable' if available else 'lost'))

							if scheduledBuild.lost:
								completePackages += scheduledBuild.port.packages

		if notify:
			with self.buildableCondition:
				self.buildableCondition.notify()

	def _buildThread(self, builderIndex, scheduledBuild, buildNumber):
		builder = self.builders[builderIndex]

		logFile = os.path.join(self.buildOutputBaseDir,
			'build_' + str(buildNumber) + '.log')

		self.logger.info('starting build ' + str(buildNumber) + ', '
			+ scheduledBuild.port.versionedName + ' on builder '
			+ builder.name);

		buildSuccess = builder.build(scheduledBuild, logFile)

		self.logger.info('build ' + str(buildNumber) + ', '
			+ scheduledBuild.port.versionedName + ' '
			+ ('succeeded' if buildSuccess else 'failed'))

		if not buildSuccess and False:
			# TODO: return the build to the unstarted state if retryable
			with self.scheduledBuildsLock:
				scheduledBuild.started = False
			with self.buildableCondition:
				self.buildableCondition.notify()
		else:
			self._packagesCompleted(scheduledBuild.port.packages, buildSuccess)

		with self.builderLock:
			self.buildThreads[builderIndex] = None

		self.semaphore.release()
