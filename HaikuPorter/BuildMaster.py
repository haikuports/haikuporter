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
	def __init__(self, configFilePath, packagesPath, outputBaseDir):
		self._loadConfig(configFilePath)
		self.availablePackages = []
		self.packagesPath = packagesPath
		self.outputBaseDir = outputBaseDir

		self.logger = logging.getLogger('builders.' + self.name)
		self.logger.setLevel(logging.DEBUG)

		formatter = logging.Formatter('%(asctime)s: %(message)s')
		logHandler = logging.FileHandler(
			os.path.join(outputBaseDir, 'builders', self.name + '.log'))
		logHandler.setFormatter(formatter)
		self.logger.addHandler(logHandler)

		self.buildLogger = logging.getLogger('builders.' + self.name + '.build')
		self.buildLogger.setLevel(logging.DEBUG)

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

			self.logger.info('trying to connect to builder ' + self.name)
			self.sshClient.connect(hostname = self.config['ssh']['host'],
				port = int(self.config['ssh']['port']),
				username = self.config['ssh']['user'],
				key_filename = self.config['ssh']['privateKeyFile'],
				compress = True, allow_agent = False, look_for_keys = False,
				timeout = 10)

			self.sftpClient = self.sshClient.open_sftp()
			self._getAvailablePackages()

			self.logger.info('connected to builder ' + self.name)
			return True
		except Exception as exception:
			self.logger.info('failed to connect to builder ' + self.name + ': '
				+ str(exception))
			return False

	def syncPortsTree(self, revision):
		command = ('cd "' + self.config['portstree']['path']
			+ '" && git fetch && git checkout ' + revision)
		self.logger.info('running command: ' + command)
		(output, channel) = self._remoteCommand(command)
		return channel.recv_exit_status() == 0

	def build(self, scheduledBuild, buildNumber):
		logHandler = logging.FileHandler(os.path.join(self.outputBaseDir,
				'builds', str(buildNumber) + '.log'))
		logHandler.setFormatter(logging.Formatter('%(message)s'))
		self.buildLogger.addHandler(logHandler)
		buildSuccess = False

		try:
			for requiredPackage in scheduledBuild.requiredPackages:
				if requiredPackage in self.availablePackages:
					continue

				self.buildLogger.info('upload required package '
					+ requiredPackage + ' to builder')

				self._putFile(os.path.join(self.packagesPath, requiredPackage),
					self.config['portstree']['packagesPath'] + '/'
						+ requiredPackage)

				self.availablePackages.append(requiredPackage)

			self.buildLogger.info('building port '
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
				+ ' --no-system-packages --no-dependencies'
				+ ' --no-package-obsoletion '
				+ self.config['haikuporter']['args'] + ' '
				+ scheduledBuild.port.versionedName)

			self.buildLogger.info('running command: ' + command)
			self.buildLogger.propagate = False

			(output, channel) = self._remoteCommand(command)
			with output:
				while True:
					line = output.readline()
					if not line:
						break

					self.buildLogger.info(line[:-1])

			self.buildLogger.propagate = True
			exitStatus = channel.recv_exit_status()
			self.buildLogger.info('command exit status: ' + str(exitStatus))

			if exitStatus != 0:
				raise Exception('build failure')

			for package in scheduledBuild.port.packages:
				self.buildLogger.info('download package ' + package.hpkgName
					+ ' from builder')

				self._getFile(self.config['portstree']['packagesPath'] + '/'
						+ package.hpkgName,
					os.path.join(self.packagesPath, package.hpkgName))

				self.availablePackages.append(package.hpkgName)

			buildSuccess = True

		except Exception as exception:
			self.buildLogger.info('build failed: ' + str(exception))
		finally:
			self.buildLogger.removeHandler(logHandler)

		return buildSuccess

	def _remoteCommand(self, command):
		transport = self.sshClient.get_transport()
		channel = transport.open_session()
		channel.get_pty()
		output = channel.makefile()
		channel.exec_command(command)
		return (output, channel)

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
	def __init__(self, packagesPath, portsTreeHead):
		self.builders = []
		self.availableBuilders = []
		self.masterBaseDir = 'buildmaster'
		self.builderBaseDir = os.path.join(self.masterBaseDir, 'builders')
		self.buildOutputBaseDir = os.path.join(self.masterBaseDir, 'output')
		self.buildNumberFile = os.path.join(self.masterBaseDir, 'buildnumber')
		self.buildNumber = 0
		try:
			with open(self.buildNumberFile, 'r') as buildNumberFile:
				self.buildNumber = int(buildNumberFile.read())
		except Exception as exception:
			pass

		logHandler = logging.FileHandler(
			os.path.join(self.buildOutputBaseDir, 'master.log'))
		logHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))

		self.logger = logging.getLogger('buildMaster')
		self.logger.setLevel(logging.DEBUG)
		self.logger.addHandler(logHandler)

		self.portsTreeHead = portsTreeHead
		self.logger.info('portstree head is at ' + self.portsTreeHead)

		for fileName in os.listdir(self.builderBaseDir):
			configFilePath = os.path.join(self.builderBaseDir, fileName)
			if not os.path.isfile(configFilePath):
				continue

			builder = None
			try:
				builder = Builder(configFilePath, packagesPath,
					self.buildOutputBaseDir)
			except Exception as exception:
				self.logger.error('failed to add builder from config '
					+ configFilePath + ':' + str(exception))

			self.logger.info('connecting to builder ' + builder.name)
			if not builder.connect():
				self.logger.error('failed to connect to builder '
					+ builder.name)
				continue

			self.logger.info('syncing portstree on builder ' + builder.name)
			if not builder.syncPortsTree(self.portsTreeHead):
				self.logger.error('failed to sync portstree on builder '
					+ builder.name)
				continue

			self.builders.append(builder)

		if len(self.builders) == 0:
			sysExit('no builders available')

		self.availableBuilders += self.builders

		self.scheduledBuilds = []
		self.blockedBuilds = []
		self.buildableCondition = threading.Condition()
			# protectes the scheduled and blocked build lists
		self.builderCondition = threading.Condition()
			# protects the [available] builder lists

	def schedule(self, port, requiredPackageIDs, presentDependencyPackages):
		self.logger.info('scheduling build of ' + port.versionedName)
		scheduledBuild = ScheduledBuild(port, requiredPackageIDs,
			presentDependencyPackages)

		if scheduledBuild.buildable:
			self.scheduledBuilds.append(scheduledBuild)
		else:
			self.blockedBuilds.append(scheduledBuild)

	def runBuilds(self):
		while True:
			buildToRun = None
			with self.buildableCondition:
				if len(self.scheduledBuilds) > 0:
					buildToRun = self.scheduledBuilds.pop(0)
				elif len(self.blockedBuilds) > 0:
					self.logger.info('nothing buildable, waiting for packages')
					self.buildableCondition.wait()
					continue
				else:
					break

			self._runBuild(buildToRun)

	def _getBuildNumber(self):
		buildNumber = self.buildNumber
		self.buildNumber += 1
		self._persistBuildNumber()
		return buildNumber

	def _runBuild(self, scheduledBuild):
		while True:
			builder = None
			buildNumber = -1
			with self.builderCondition:
				if len(self.builders) == 0:
					sysExit('all builders lost')

				if len(self.availableBuilders) == 0:
					self.builderCondition.wait()
					continue

				builder = self.availableBuilders.pop(0)
				buildNumber = self._getBuildNumber()

			threading.Thread(None, self._buildThread,
				'build ' + str(buildNumber),
				(builder, scheduledBuild, buildNumber)).start()
			break

	def _persistBuildNumber(self):
		with open(self.buildNumberFile, 'w') as buildNumberFile:
			buildNumberFile.write(str(self.buildNumber))

	def _packagesCompleted(self, packages, available):
		completePackages = [] + packages
		with self.buildableCondition:
			notify = False

			while len(completePackages) > 0:
				package = completePackages.pop(0)
				self.logger.info('package ' + package.versionedName + ' '
					+ ('became available' if available else 'lost'))

				stillBlockedBuilds = []
				for blockedBuild in self.blockedBuilds:
					blockedBuild.packageCompleted(package, available)
					if blockedBuild.buildable or blockedBuild.lost:
						notify = True
						self.logger.info('scheduled build '
							+ blockedBuild.port.versionedName + ' '
							+ ('became buildable' if available else 'lost'))

						if blockedBuild.buildable:
							self.scheduledBuilds.append(blockedBuild)
						else:
							# the build was lost, propagate lost packages
							completePackages += blockedBuild.port.packages
					else:
						stillBlockedBuilds.append(blockedBuild)

				self.blockedBuilds = stillBlockedBuilds

			if notify:
				self.buildableCondition.notify()

	def _buildThread(self, builder, scheduledBuild, buildNumber):
		self.logger.info('starting build ' + str(buildNumber) + ', '
			+ scheduledBuild.port.versionedName + ' on builder '
			+ builder.name);

		buildSuccess = builder.build(scheduledBuild, buildNumber)

		self.logger.info('build ' + str(buildNumber) + ', '
			+ scheduledBuild.port.versionedName + ' '
			+ ('succeeded' if buildSuccess else 'failed'))

		if not buildSuccess and False:
			# TODO: return the build to the schedule if retryable
			with self.scheduledBuildsLock:
				self.scheduledBuilds.append(scheduledBuild)
			with self.buildableCondition:
				self.scheduledBuilds.append(scheduledBuild)
				self.buildableCondition.notify()
		else:
			self._packagesCompleted(scheduledBuild.port.packages, buildSuccess)

		with self.builderCondition:
			self.availableBuilders.append(builder)

			self.builderCondition.notify()
