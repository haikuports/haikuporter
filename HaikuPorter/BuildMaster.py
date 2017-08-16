# -*- coding: utf-8 -*-
#
# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from .ConfigParser import ConfigParser
from .Configuration import Configuration
from .Options import getOption
from .Utils import ensureCommandIsAvailable, info, sysExit, warn

import errno
import json
import logging
import os
import socket
import stat
import subprocess
import threading
import time

try:
	import paramiko
except ImportError:
	paramiko = None

class ThreadFilter:
	def __init__(self):
		self.ident = threading.current_thread().ident
		self.build = None

	def reset(self):
		self.ident = threading.current_thread().ident
	def setBuild(self, build):
		self.build = build

	def filter(self, record):
		ours = threading.current_thread().ident == self.ident
		if ours and self.build:
			self.build['lines'] += 1
		return ours


class ScheduledBuild:
	def __init__(self, port, portsTreePath, requiredPackageIDs, packagesPath,
		presentDependencyPackages):
		self.port = port
		self.recipeFilePath \
			= os.path.relpath(port.recipeFilePath, portsTreePath)
		self.resultingPackages \
			= [ package.hpkgName for package in self.port.packages ]
		self.packagesPath = packagesPath
		self.requiredPackages = presentDependencyPackages
		self.requiredPackageIDs = [
			os.path.basename(path) for path in presentDependencyPackages]
		self.missingPackageIDs = set(requiredPackageIDs)
		self.buildNumbers = []
		self.lost = False

	@property
	def buildable(self):
		return len(self.missingPackageIDs) == 0

	def packageCompleted(self, package, available):
		packageID = package.versionedName
		if packageID in self.missingPackageIDs:
			if available:
				self.missingPackageIDs.remove(packageID)
				self.requiredPackageIDs.append(package.hpkgName)
				self.requiredPackages.append(
					os.path.join(self.packagesPath, package.hpkgName))
			else:
				self.lost = True

	@property
	def status(self):
		return {
			'port': {
				'name': self.port.name,
				'version': self.port.version,
				'revision': self.port.revision,
				'revisionedName': self.port.revisionedName,
				'recipeFilePath': self.recipeFilePath
			},
			'resultingPackages': self.resultingPackages,
			'requiredPackages': sorted(list(self.requiredPackageIDs)),
			'missingPackageIDs': sorted(list(self.missingPackageIDs)),
			'buildable': self.buildable,
			'buildNumbers': self.buildNumbers,
			'lost': self.lost
		}


class BuildRecord:
	def __init__(self, scheduledBuild, startTime, buildSuccess, builderId):
		self.port = scheduledBuild.port
		self.buildNumbers = scheduledBuild.buildNumbers
		self.startTime = startTime
		self.duration = time.time() - startTime
		self.buildSuccess = buildSuccess
		self.builderId = builderId

	@property
	def status(self):
		return {
			'port': {
				'name': self.port.name,
				'version': self.port.version,
				'revision': self.port.revision,
				'revisionedName': self.port.revisionedName
			},
			'buildNumbers': self.buildNumbers,
			'startTime': self.startTime,
			'duration': self.duration,
			'buildSuccess': self.buildSuccess,
			'builderId': self.builderId
		}


class _BuilderState:
	AVAILABLE = 'Available'
	LOST = 'Lost'
	NOT_AVAILABLE = 'Not Available'
	RECONNECT = 'Reconnecting'


class RemoteBuilder:
	def __init__(self, configFilePath, packagesPath, outputBaseDir,
			portsTreeOriginURL, portsTreeHead):
		self._loadConfig(configFilePath)
		self.availablePackages = []
		self.visiblePackages = []
		self.portsTreeOriginURL = portsTreeOriginURL
		self.portsTreeHead = portsTreeHead
		self.packagesPath = packagesPath

		self.builderOutputDir = os.path.join(outputBaseDir, 'builders')
		if not os.path.isdir(self.builderOutputDir):
			os.makedirs(self.builderOutputDir)

		self.buildOutputDir = os.path.join(outputBaseDir, 'builds')
		if not os.path.isdir(self.buildOutputDir):
			os.makedirs(self.buildOutputDir)

		self.state = _BuilderState.NOT_AVAILABLE
		self.connectionErrors = 0
		self.maxConnectionErrors = 100

		self.currentBuild = None

		self.logger = logging.getLogger('builders.' + self.name)
		self.logger.setLevel(logging.DEBUG)

		formatter = logging.Formatter('%(asctime)s: %(message)s')
		logHandler = logging.FileHandler(
			os.path.join(self.builderOutputDir, self.name + '.log'))
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
		if not 'packagesCachePath' in self.config['portstree']:
			self.config['portstree']['packagesCachePath'] \
				= self.config['portstree']['packagesPath'] + '/.cache'
		if not 'builderConfig' in self.config['portstree']:
			self.config['portstree']['builderConfig'] \
				= self.config['portstree']['path'] + '/builder.conf'

		if not 'haikuporter' in self.config:
			self.config['haikuporter'] = {}
		if not 'path' in self.config['haikuporter']:
			self.config['haikuporter']['path'] = 'haikuporter'
		if not 'args' in self.config['haikuporter']:
			self.config['haikuporter']['args'] = ''

	def _connect(self):
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

			self.sshClient.get_transport().set_keepalive(15)
			self.sftpClient = self.sshClient.open_sftp()

			self.logger.info('connected to builder')
			self.connectionErrors = 0
		except Exception as exception:
			self.logger.error('failed to connect to builder: '
				+ str(exception))

			self.connectionErrors += 1
			self.state = _BuilderState.RECONNECT

			if self.connectionErrors >= self.maxConnectionErrors:
				self.logger.error('giving up on builder after '
					+ str(self.connectionErrors)
					+ ' consecutive connection errors')
				self.state = _BuilderState.LOST

			# avoid DoSing the remote host, increasing delay as retries increase.
			time.sleep(5 + (1.2 * self.connectionErrors))
			raise

	def _validatePortsTree(self):
		try:
			command = ('if [ ! -d "' + self.config['portstree']['path'] + '" ]; '
				+ 'then git clone "' + self.portsTreeOriginURL + '" '
				+ self.config['portstree']['path'] + '; fi')
			self.logger.info('running command: ' + command)
			(output, channel) = self._remoteCommand(command)
			return channel.recv_exit_status() == 0
		except Exception as exception:
			self.logger.error('failed to validate ports tree: '
				+ str(exception))
			raise

	def _syncPortsTree(self):
		try:
			command = ('cd "' + self.config['portstree']['path']
				+ '" && git fetch && git checkout ' + self.portsTreeHead)
			self.logger.info('running command: ' + command)
			(output, channel) = self._remoteCommand(command)
			if channel.recv_exit_status() != 0:
				raise Exception('sync command failed')
		except Exception as exception:
			self.logger.error('failed to sync ports tree: '
				+ str(exception))
			raise

	def _writeBuilderConfig(self):
		try:
			config = {
				'TREE_PATH': self.config['portstree']['path'],
				'PACKAGES_PATH': self.config['portstree']['packagesPath'],
				'PACKAGER': 'Builder ' + self.name \
					+ ' <hpkg-builder@haiku-os.org>',
				'TARGET_ARCHITECTURE': Configuration.getTargetArchitecture(),
				'SECONDARY_TARGET_ARCHITECTURES': \
					Configuration.getSecondaryTargetArchitectures(),
				'ALLOW_UNTESTED': Configuration.shallAllowUntested(),
				'ALLOW_UNSAFE_SOURCES': Configuration.shallAllowUnsafeSources()
			}

			with self._openRemoteFile(self.config['portstree']['builderConfig'],
					'w') as remoteFile:
				remoteFile.write(
					ConfigParser.configurationStringFromDict(config))
		except Exception as exception:
			self.logger.error('failed to write builder config: '
				+ str(exception))
			raise

	def _createNeededDirs(self):
		try:
			self._ensureDirExists(self.config['portstree']['packagesPath'])
			self._ensureDirExists(self.config['portstree']['packagesCachePath'])
		except Exception as exception:
			self.logger.error('failed to create needed dirs: '
				+ str(exception))
			raise

	def _getAvailablePackages(self):
		try:
			self._clearVisiblePackages()

			for entry in self._listDir(
					self.config['portstree']['packagesCachePath']):
				if not entry.endswith('.hpkg'):
					continue

				if not entry in self.availablePackages:
					self.availablePackages.append(entry)
		except Exception as exception:
			self.logger.error('failed to get available packages: '
				+ str(exception))
			raise

	def _setupForBuilding(self):
		if self.state == _BuilderState.AVAILABLE:
			return True
		if self.state  == _BuilderState.LOST:
			return False

		self._connect()
		self._validatePortsTree()
		self._syncPortsTree()
		self._writeBuilderConfig()
		self._createNeededDirs()
		self._getAvailablePackages()

		self.state = _BuilderState.AVAILABLE
		return True

	def setBuild(self, scheduledBuild, buildNumber):
		logHandler = logging.FileHandler(os.path.join(self.buildOutputDir,
				str(buildNumber) + '.log'))
		logHandler.setFormatter(logging.Formatter('%(message)s'))
		self.buildLogger.addHandler(logHandler)

		self.currentBuild = {
			'build': scheduledBuild,
			'status': scheduledBuild.status,
			'number': buildNumber,
			'logHandler': logHandler
		}

	def unsetBuild(self):
		self.buildLogger.removeHandler(self.currentBuild['logHandler'])
		self.currentBuild = None

	def runBuild(self):
		scheduledBuild = self.currentBuild['build']
		buildSuccess = False
		reschedule = True

		try:
			if not self._setupForBuilding():
				return (False, True)

			self._cleanPort(scheduledBuild)
			self._clearVisiblePackages()
			for requiredPackage in scheduledBuild.requiredPackages:
				self._makePackageAvailable(requiredPackage)
				self._makePackageVisible(requiredPackage)

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
				+ '" --config="' + self.config['portstree']['builderConfig']
				+ '" --no-system-packages --no-package-obsoletion '
				+ self.config['haikuporter']['args'] + ' "'
				+ scheduledBuild.port.versionedName + '"')

			self.buildLogger.info('running command: ' + command)
			self.buildLogger.propagate = False

			(output, channel) = self._remoteCommand(command)
			self._appendOutputToLog(output)

			self.buildLogger.propagate = True
			exitStatus = channel.recv_exit_status()
			self.buildLogger.info('command exit status: ' + str(exitStatus))

			if exitStatus < 0 and not channel.get_transport().is_active():
				self.state = _BuilderState.NOT_AVAILABLE
				raise Exception('builder disconnected')

			if exitStatus != 0:
				reschedule = False
				raise Exception('build failure')

			for package in scheduledBuild.port.packages:
				self.buildLogger.info('download package ' + package.hpkgName
					+ ' from builder')

				self._getFile(self.config['portstree']['packagesPath'] + '/'
						+ package.hpkgName,
					os.path.join(self.packagesPath, package.hpkgName))

			self._cleanPort(scheduledBuild)
			self._clearVisiblePackages()
			self.buildLogger.info('build completed successfully')
			buildSuccess = True

		except socket.error as exception:
			self.buildLogger.error('connection failed: ' + str(exception))
			self.state = _BuilderState.NOT_AVAILABLE

		except (IOError, paramiko.ssh_exception.SSHException) as exception:
			self.buildLogger.error('builder failed: ' + str(exception))
			self.state = _BuilderState.LOST

		except Exception as exception:
			self.buildLogger.info('build failed: ' + str(exception))

		return (buildSuccess, reschedule)

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

	def _symlink(self, sourcePath, destPath):
		self.sftpClient.symlink(sourcePath, destPath)

	def _openRemoteFile(self, path, mode):
		return self.sftpClient.open(path, mode)

	def _ensureDirExists(self, path):
		try:
			attributes = self.sftpClient.stat(path)
			if not stat.S_ISDIR(attributes.st_mode):
				raise IOError(errno.EEXISTS, 'file exists')
		except IOError as exception:
			if exception.errno != errno.ENOENT:
				raise

			self.sftpClient.mkdir(path)

	def _listDir(self, remotePath):
		return self.sftpClient.listdir(remotePath)

	def _cleanPort(self, scheduledBuild):
		command = ('cd "' + self.config['portstree']['path']
			+ '" && "' + self.config['haikuporter']['path']
			+ '" --config="' + self.config['portstree']['builderConfig']
			+ '" --no-package-obsoletion --clean "'
			+ scheduledBuild.port.versionedName + '"')

		info('cleaning port with command: ' + command)
		(output, channel) = self._remoteCommand(command)
		self._appendOutputToLog(output)

	def _appendOutputToLog(self, output):
		with output:
			while True:
				line = output.readline()
				if not line:
					return

				self.buildLogger.info(line[:-1])

	def _makePackageAvailable(self, packagePath):
		packageName = os.path.basename(packagePath)
		if packageName in self.availablePackages:
			return

		self.logger.info('upload package ' + packageName + ' to builder')
		self._putFile(packagePath,
			self.config['portstree']['packagesCachePath'] + '/' + packageName)

		self.availablePackages.append(packageName)

	def _clearVisiblePackages(self):
		basePath = self.config['portstree']['packagesPath']
		cachePath = self.config['portstree']['packagesCachePath']
		for entry in self._listDir(basePath):
			if not entry.endswith('.hpkg'):
				continue

			entryPath = basePath + '/' + entry
			attributes = self.sftpClient.lstat(entryPath)
			if stat.S_ISLNK(attributes.st_mode):
				self.logger.debug('removing symlink to package ' + entry)
				self.sftpClient.remove(entryPath)
			else:
				# Unfortunately we can't use SFTPClient.rename as that uses the
				# rename command (vs. posix-rename) which uses hardlinks which
				# fail on BFS
				self.logger.info('moving package ' + entry + ' to cache')
				cacheEntryPath = cachePath + '/' + entry
				(output, channel) = self._remoteCommand('mv "'
					+ entryPath + '" "' + cacheEntryPath + '"')
				if channel.recv_exit_status() != 0:
					raise IOError('failed to move file to cache')

				self.availablePackages.append(entry)

		self.visiblePackages = []

	def _makePackageVisible(self, packagePath):
		packageName = os.path.basename(packagePath)
		if packageName in self.visiblePackages:
			return

		self.logger.debug('making package ' + packageName + ' visible')
		self._symlink(
			self.config['portstree']['packagesCachePath'] + '/' + packageName,
			self.config['portstree']['packagesPath'] + '/' + packageName)

		self.visiblePackages.append(packageName)

	@property
	def status(self):
		return {
			'name': self.name,
			'state': self.state,
			'availablePackages': self.availablePackages,
			'connectionErrors': self.connectionErrors,
			'maxConnectionErrors': self.maxConnectionErrors,
			'currentBuild': {
				'build': self.currentBuild['status'],
				'number': self.currentBuild['number']
			} if self.currentBuild else None
		}


class MockBuilder:
	def __init__(self, name, buildFailInterval, builderFailInterval, lostAfter):
		self.name = name
		self.buildCount = 0
		self.failedBuilds = 0
		self.buildFailInterval = buildFailInterval
		self.builderFailInterval = builderFailInterval
		self.lostAfter = lostAfter
		self.lost = False
		self.currentBuild = None

	def setBuild(self, scheduledBuild, buildNumber):
		self.currentBuild = {
			'build': scheduledBuild.status,
			'number': buildNumber
		}

	def unsetBuild(self):
		self.currentBuild = None

	def runBuild(self):
		buildSuccess = False
		reschedule = True

		try:
			self.buildCount += 1
			if self.buildCount >= self.lostAfter:
				self.lost = True
				time.sleep(1)
				raise Exception('lost')

			buildSuccess = self.buildCount % self.buildFailInterval != 0
			if not buildSuccess:
				time.sleep(1)
				self.failedBuilds += 1
				reschedule = self.failedBuilds % self.builderFailInterval == 0
				raise Exception('failed')

			time.sleep(1)
		except Exception as exception:
			pass

		return (buildSuccess, reschedule)

	@property
	def status(self):
		return {
			'name': self.name,
			'lost': self.lost,
			'currentBuild': self.currentBuild
		}


class LocalBuilder:
	def __init__(self, name, packagesPath, outputBaseDir, options):
		self.options = options
		self.name = name
		self.buildCount = 0
		self.failedBuilds = 0
		self.packagesPath = packagesPath
		self.state = _BuilderState.AVAILABLE
		self.currentBuild = None

		self.buildOutputDir = os.path.join(outputBaseDir, 'builds')
		if not os.path.isdir(self.buildOutputDir):
			os.makedirs(self.buildOutputDir)

		self.buildLogger = logging.getLogger('builders.' + self.name + '.build')
		self.buildLogger.setLevel(logging.DEBUG)


	def setBuild(self, scheduledBuild, buildNumber):
		logHandler = logging.FileHandler(os.path.join(self.buildOutputDir,
				str(buildNumber) + '.log'))
		logHandler.setFormatter(logging.Formatter('%(message)s'))
		self.buildLogger.addHandler(logHandler)
		filter = ThreadFilter()
		logHandler.addFilter(filter)
		logging.getLogger("buildLogger").setLevel(logging.DEBUG)
		logging.getLogger("buildLogger").addHandler(logHandler)

		self.currentBuild = {
			'build': scheduledBuild,
			'status': scheduledBuild.status,
			'number': buildNumber,
			'logHandler': logHandler,
			'logFilter': filter,
			'startTime': None,
			'phase': 'setup',
			'lines' : 0
		}
		filter.setBuild(self.currentBuild)


	def unsetBuild(self):
		self.buildLogger.removeHandler(self.currentBuild['logHandler'])
		logging.getLogger("buildLogger").removeHandler(self.currentBuild['logHandler'])
		self.currentBuild = None

	def runBuild(self):
		scheduledBuild = self.currentBuild['build']
		buildSuccess = False
		reschedule = True
		port = scheduledBuild.port
		self.currentBuild['startTime'] = time.time()
		self.currentBuild['phase'] = 'start'

		try:
			self.buildCount += 1

			self.buildLogger.info('building port ' + port.versionedName)

			port.setLogger(self.buildLogger)
			port.setFilter(self.currentBuild['logFilter'])

			if not port.isMetaPort:
				self.currentBuild['phase'] = 'download'
				port.downloadSource()
				self.currentBuild['phase'] = 'unpack'
				port.unpackSource()
				port.populateAdditionalFiles()
				self.currentBuild['phase'] = 'patch'
				port.patchSource()

				self.currentBuild['phase'] = 'build'
				port.build(self.packagesPath, self.options.package, self.packagesPath)

				self.currentBuild['phase'] = 'done'
				buildSuccess = True


		except Exception as exception:
			if isinstance(exception, subprocess.CalledProcessError):
				self.buildLogger.info(exception.output)
			self.buildLogger.error(exception, exc_info=True)
			self.currentBuild['phase'] = 'failed'
			reschedule = False
		except SystemExit as exception:
			self.buildLogger.error(exception, exc_info=True)
			self.currentBuild['phase'] = 'failed'
			reschedule = False

		port.unsetLogger()

		return (buildSuccess, reschedule)

	@property
	def status(self):
		return {
			'name': self.name,
			'state': self.state,
			'currentBuild': {
				'build': self.currentBuild['status'],
				'number': self.currentBuild['number'],
				'phase': self.currentBuild['phase'],
				'duration': ((time.time() - self.currentBuild['startTime'])
					if self.currentBuild['startTime'] else None),
				'lines': self.currentBuild['lines']
			} if self.currentBuild else None
		}


class BuildMaster:
	def __init__(self, portsTreePath, packagesPath, options):
		self.portsTreePath = portsTreePath
		self._fillPortsTreeInfo()

		self.activeBuilders = []
		self.reconnectingBuilders = []
		self.idleBuilders = []
		self.lostBuilders = []
		self.availableBuilders = []
		self.packagesPath = packagesPath
		self.masterBaseDir = os.path.realpath('buildmaster')
		self.builderBaseDir = os.path.join(self.masterBaseDir, 'builders')
		self.buildOutputBaseDir = getOption('buildMasterOutputDir')
		if self.buildOutputBaseDir:
			self.buildOutputBaseDir = os.path.realpath(self.buildOutputBaseDir)
		else:
			self.buildOutputBaseDir = os.path.join(self.masterBaseDir, 'output')

		if not os.path.isdir(self.buildOutputBaseDir):
			os.makedirs(self.buildOutputBaseDir)

		self.buildRecordsDir = os.path.join(self.buildOutputBaseDir, 'records')
		if not os.path.isdir(self.buildRecordsDir):
			os.makedirs(self.buildRecordsDir)

		self.buildStatus = None
		self.buildNumberFile = os.path.join(self.masterBaseDir, 'buildnumber')
		self.buildNumber = 0
		try:
			with open(self.buildNumberFile, 'r') as buildNumberFile:
				self.buildNumber = int(buildNumberFile.read())
		except Exception as exception:
			pass

		self.localBuilders = getOption('localBuilders')
		self.remoteAvailable = False
		if paramiko:
			self.remoteAvailable = True
		else:
			print 'Remote mode unavailable'
			if self.localBuilders == 0:
				self.localBuilders = 1

		print 'Local builders count: ' + str(self.localBuilders)

		logHandler = logging.FileHandler(
			os.path.join(self.buildOutputBaseDir, 'master.log'))
		logHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))

		self.logger = logging.getLogger('buildMaster')
		self.logger.setLevel(logging.DEBUG)
		self.logger.addHandler(logHandler)

		self.logger.info('portstree head is at ' + self.portsTreeHead)

		self.statusOutputPath = os.path.join(self.buildOutputBaseDir,
			'status.json')

		if self.localBuilders == 0:
			for fileName in os.listdir(self.builderBaseDir):
				configFilePath = os.path.join(self.builderBaseDir, fileName)
				if not os.path.isfile(configFilePath):
					continue

				builder = None
				try:
					builder = RemoteBuilder(configFilePath, packagesPath,
						self.buildOutputBaseDir, self.portsTreeOriginURL,
						self.portsTreeHead)
				except Exception as exception:
					self.logger.error('failed to add builder from config '
						+ configFilePath + ':' + str(exception))
					continue

				self.activeBuilders.append(builder)
		else:
			logger = logging.getLogger("buildLogger")
			for h in logger.handlers:
				logger.removeHandler(h)
			for i in range(0, self.localBuilders):
				configFilePath = os.path.join(self.builderBaseDir, str(i))

				builder = None
				try:
					builder = LocalBuilder(str(i), packagesPath,
						self.buildOutputBaseDir, options)
				except Exception as exception:
					self.logger.error('failed to add builder from config '
						+ configFilePath + ':' + str(exception))
					continue

				self.activeBuilders.append(builder)

		if len(self.activeBuilders) == 0:
			sysExit(u'no builders available')

		self.availableBuilders += self.activeBuilders

		self.scheduledBuilds = []
		self.activeBuilds = []
		self.blockedBuilds = []
		self.completeBuilds = []
		self.failedBuilds = []
		self.lostBuilds = []
		self.buildHistory = []
		self.totalBuildCount = 0
		self.startTime = None
		self.endTime = None
		self.impulseData = [None] * 500
		self.impulseIndex = -1
		self.display = None

		self.buildableCondition = threading.Condition()
			# protectes the scheduled builds lists
		self.builderCondition = threading.Condition()
			# protects the builders lists
		self.statusLock = threading.Lock()

		self._setBuildStatus('preparing')

	def schedule(self, port, requiredPackageIDs, presentDependencyPackages):
		self.logger.info('scheduling build of ' + port.versionedName)
		scheduledBuild = ScheduledBuild(port, self.portsTreePath,
			requiredPackageIDs, self.packagesPath, presentDependencyPackages)

		if scheduledBuild.buildable:
			self.scheduledBuilds.append(scheduledBuild)
		else:
			self.blockedBuilds.append(scheduledBuild)

		self._setBuildStatus('scheduling')

	def runBuilds(self, stdscr=None):
		try:
			if stdscr:
				from .Display import Display
				self.display = Display(stdscr, len(self.activeBuilders))

			self._ensureConsistentSchedule()
			self.totalBuildCount = len(self.scheduledBuilds) + len(self.blockedBuilds)
			self.startTime = time.time()
			self._setBuildStatus('starting builds')
			if self.display:
				self.display.updateSummary(self.summary)
			while True:
				self._runBuilds()
				self._waitForBuildsToComplete()
				if len(self.scheduledBuilds) == 0:
					break

			exitStatus = 'complete'
		except KeyboardInterrupt:
			exitStatus = 'aborted'
		except Exception as exception:
			self.logger.error(str(exception))
			exitStatus = 'failed: ' + str(exception)

		self.logger.info('finished with status: ' + exitStatus)
		self.endTime = time.time();
		self._setBuildStatus(exitStatus)

	def _fillPortsTreeInfo(self):
		try:
			ensureCommandIsAvailable('git')
			origin = subprocess.check_output(['git', 'remote', 'get-url',
					'origin'], cwd = self.portsTreePath,
				stderr=subprocess.STDOUT)
			head = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
				cwd = self.portsTreePath, stderr=subprocess.STDOUT)
		except:
			warn(u'unable to determine origin and revision of haikuports tree')
			origin = '<unknown> '
			head = '<unknown> '

		self.portsTreeOriginURL = origin[:-1]
		self.portsTreeHead = head[:-1]

	def _runBuilds(self):
		while True:
			buildToRun = None
			with self.buildableCondition:
				if len(self.scheduledBuilds) > 0:
					buildToRun = self.scheduledBuilds.pop(0)
					self.activeBuilds.append(buildToRun)
				elif len(self.blockedBuilds) > 0:
					if self.buildStatus != 'waiting for packages':
						self.logger.info('nothing buildable, waiting for packages')
					self._setBuildStatus('waiting for packages')
					if self.display:
						self.display.updateSummary(self.summary)
						self.display.updateBuilders(self.status)
					self.buildableCondition.wait(1)
					continue
				else:
					break

			self._runBuild(buildToRun)

	def _waitForBuildsToComplete(self):
		while True:
			with self.builderCondition:
				for builder in self.availableBuilders:
					self.activeBuilders.remove(builder)

				self.idleBuilders += self.availableBuilders
				self.availableBuilders = []

				if len(self.activeBuilders) == 0:
					break

				if self.display:
					self.display.updateSummary(self.summary)
					self.display.updateBuilders(self.status)

				self._setBuildStatus('waiting for all builds to complete')
				self.builderCondition.wait(1)

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
				if len(self.activeBuilders) == 0:
					self._setBuildStatus('all builders lost')
					sysExit(u'all builders lost')

				if len(self.availableBuilders) == 0:
					self._setBuildStatus('waiting for available builders')
					if self.display:
						self.display.updateSummary(self.summary)
						self.display.updateBuilders(self.status)
					self.builderCondition.wait(1)
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
							self.lostBuilds.append(blockedBuild)
							completePackages += blockedBuild.port.packages
					else:
						stillBlockedBuilds.append(blockedBuild)

				self.blockedBuilds = stillBlockedBuilds

			if notify:
				self.buildableCondition.notify()

	def _buildComplete(self, scheduledBuild, buildSuccess, listToUse):
		with self.buildableCondition:
			if scheduledBuild in self.activeBuilds:
				self.activeBuilds.remove(scheduledBuild)
			listToUse.append(scheduledBuild)

		self._packagesCompleted(scheduledBuild.port.packages, buildSuccess)

	def _buildThread(self, builder, scheduledBuild, buildNumber):
		self.logger.info('starting build ' + str(buildNumber) + ', '
			+ scheduledBuild.port.versionedName + ' on builder '
			+ builder.name)

		scheduledBuild.buildNumbers.append(buildNumber)

		builder.setBuild(scheduledBuild, buildNumber)
		self._dumpStatus()
		startTime = time.time()

		(buildSuccess, reschedule) = builder.runBuild()

		builder.unsetBuild()

		self.logger.info('build ' + str(buildNumber) + ', '
			+ scheduledBuild.port.versionedName + ' '
			+ ('succeeded' if buildSuccess else 'failed'))

		if not buildSuccess and reschedule:
			self.logger.info('transient error, rescheduling build')
			with self.buildableCondition:
				self.activeBuilds.remove(scheduledBuild)
				self.scheduledBuilds.append(scheduledBuild)
				self.buildableCondition.notify()
		else:
			record = BuildRecord(scheduledBuild, startTime, buildSuccess,
				builder.name)

			with open(os.path.join(self.buildRecordsDir,
					str(buildNumber) + '.json'), 'w') as outputFile:
				outputFile.write(json.dumps(record.status))

			self.buildHistory.append(record)
			if self.display:
				self.display.updateHistory(self.buildHistory)

			self._buildComplete(scheduledBuild, buildSuccess,
				self.completeBuilds if buildSuccess else self.failedBuilds)

		with self.builderCondition:
			if builder.state == _BuilderState.LOST:
				self.logger.error('builder ' + builder.name + ' lost')
				self.activeBuilders.remove(builder)
				self.lostBuilders.append(builder)
			elif builder.state == _BuilderState.RECONNECT:
				self.logger.error(
					'builder ' + builder.name + ' is reconnecting')
				self.activeBuilders.remove(builder)
				self.reconnectingBuilders.append(builder)
			else:
				self.availableBuilders.append(builder)

			self.builderCondition.notify()

		self._dumpStatus()

	def _ensureConsistentSchedule(self):
		buildingPackagesIDs = []
		for scheduledBuild in self.scheduledBuilds + self.blockedBuilds:
			for package in scheduledBuild.port.packages:
				if not package.versionedName in buildingPackagesIDs:
					buildingPackagesIDs.append(package.versionedName)

		brokenBuilds = []
		for blockedBuild in self.blockedBuilds:
			for missingPackageID in blockedBuild.missingPackageIDs:
				if not missingPackageID in buildingPackagesIDs:
					brokenBuilds.append(blockedBuild)
					break

		for brokenBuild in brokenBuilds:
			self.logger.error('missing package ' + missingPackageID
				+ ' of blocked build ' + blockedBuild.port.versionedName
				+ ' is not scheduled')
			self._buildComplete(brokenBuild, False, self.lostBuilds)

		for lostBuild in self.lostBuilds:
			if lostBuild in self.blockedBuilds:
				self.blockedBuilds.remove(lostBuild)

	@property
	def status(self):
		return {
			'builds': {
				'active': [ build.status for build in self.activeBuilds ],
				'scheduled': [ build.status for build in self.scheduledBuilds ],
				'blocked': [ build.status for build in self.blockedBuilds ],
				'complete': [ build.status for build in self.completeBuilds ],
				'failed': [ build.status for build in self.failedBuilds ],
				'lost': [ build.status for build in self.lostBuilds ]
			},
			'builders': {
				'active': [ builder.status for builder in self.activeBuilders ],
				'reconnecting':
					[builder.status for builder in self.reconnectingBuilders],
				'idle': [ builder.status for builder in self.idleBuilders ],
				'lost': [ builder.status for builder in self.lostBuilders ]
			},
			'nextBuildNumber': self.buildNumber,
			'portsTreeOriginURL': self.portsTreeOriginURL,
			'portsTreeHead': self.portsTreeHead,
			'buildStatus': self.buildStatus,
			'startTime': self.startTime,
			'endTime': self.endTime
		}

	@property
	def summary(self):
		self.impulseIndex += 1
		if self.impulseIndex >= len(self.impulseData):
			self.impulseIndex = 0
		impulseTime = (self.impulseData[self.impulseIndex]['time']
			) if self.impulseData[self.impulseIndex] else None
		impulsePkgCount = (self.impulseData[self.impulseIndex]['pkgCount']
			) if self.impulseData[self.impulseIndex] else None
		now = time.time()
		pkgCount = len(self.completeBuilds) + len(self.failedBuilds)
		self.impulseData[self.impulseIndex] = {
			'time': now,
			'pkgCount': pkgCount
		}
		return {
			'builds': {
				'active': len(self.activeBuilds),
				'scheduled': len(self.scheduledBuilds),
				'blocked': len(self.blockedBuilds),
				'complete': len(self.completeBuilds),
				'failed': len(self.failedBuilds),
				'lost': len(self.lostBuilds),
				'total': self.totalBuildCount
			},
			'builders': {
				'active': len(self.activeBuilders),
				'lost': len(self.lostBuilders),
				'total': len(self.activeBuilders) + len(self.lostBuilders)
			},
			'duration': (now - self.startTime) if self.startTime else None,
			'pkg_hour': int(pkgCount * 3600
				/ (now - self.startTime)) if self.startTime else None,
			'impulse': int((pkgCount - impulsePkgCount) * 3600
				/ (now - impulseTime)) if impulsePkgCount else None
		}

	def _setBuildStatus(self, buildStatus):
		self.buildStatus = buildStatus
		self._dumpStatus()

	def _dumpStatus(self):
		with self.statusLock:
			tempFile = self.statusOutputPath + '.temp'
			with open(tempFile, 'w') as outputFile:
				outputFile.write(json.dumps(self.status))
			os.rename(tempFile, self.statusOutputPath)
