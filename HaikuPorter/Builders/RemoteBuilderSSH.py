# -*- coding: utf-8 -*-
#
# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.

import base64
import errno
import json
import logging
import os
import socket
import stat
import time
import io

from io import StringIO

# These usages kinda need refactored
from ..ConfigParser import ConfigParser
from ..Configuration import Configuration
from ..Options import getOption
from .Builder import BuilderState

try:
	import paramiko
except ImportError:
	paramiko = None

class RemoteBuilderSSH(object):
	def __init__(self, configFilePath, packageRepository, outputBaseDir,
			portsTreeOriginURL, portsTreeHead):
		self._loadConfig(configFilePath)
		self.type = "RemoteBuilderSSH"
		self.availablePackages = []
		self.visiblePackages = []
		self.portsTreeOriginURL = portsTreeOriginURL
		self.portsTreeHead = portsTreeHead
		self.packageRepository = packageRepository

		self.sshClient = None
		self.jumpClient = None

		if not paramiko:
			raise Exception('paramiko unavailable')

		self.builderOutputDir = os.path.join(outputBaseDir, 'builders')
		if not os.path.isdir(self.builderOutputDir):
			os.makedirs(self.builderOutputDir)

		self.buildOutputDir = os.path.join(outputBaseDir, 'builds')
		if not os.path.isdir(self.buildOutputDir):
			os.makedirs(self.buildOutputDir)

		self.state = BuilderState.NOT_AVAILABLE
		self.connectionErrors = 0
		self.maxConnectionErrors = 100

		self.currentBuild = None

		self.logger = logging.getLogger('builders.' + self.name)
		self.logger.setLevel(logging.DEBUG)

		formatter = logging.Formatter('%(asctime)s: %(message)s')
		logHandler = logging.FileHandler(
			os.path.join(self.builderOutputDir, self.name + '.log'),
			encoding='utf-8')
		logHandler.setFormatter(formatter)
		self.logger.addHandler(logHandler)

		self.buildLogger = logging.getLogger('builders.' + self.name + '.build')
		self.buildLogger.setLevel(logging.DEBUG)

	def _loadConfig(self, configFilePath):
		with open(configFilePath, 'r') as configFile:
			self.config = json.loads(configFile.read())

		if 'name' not in self.config:
			raise Exception('missing name in ' + configFilePath)
		self.name = self.config['name']

		# Validate required SSH configuration for builder
		if 'ssh' not in self.config:
			raise Exception('missing ssh config for builder ' + self.name)
		for x in ['host', 'user', 'privateKey']:
			if x not in self.config['ssh']:
				raise Exception('missing ssh ' + x + ' for builder ' + self.name)
		if 'port' not in self.config['ssh']:
			self.config['ssh']['port'] = 22

		# Set path to our trusted known hosts
		self.config['ssh']['knownHostsFile'] = os.path.join(os.path.dirname(configFilePath),
			'known_hosts')

		if not os.path.exists(self.config['ssh']['knownHostsFile']):
			raise Exception('known hosts file missing from ' + self.config['ssh']['knownHostsFile'])

		# If we were provided a jump host, validate it and decode private key
		if 'jump' in self.config['ssh']:
			for x in ['host', 'user', 'privateKey']:
				if x not in self.config['ssh']['jump']:
					raise Exception('missing ' + x + 'config for jump host ' + self.name)
			if 'port' not in self.config['ssh']['jump']:
			    self.config['ssh']['jump']['port'] = 22

		if 'portstree' not in self.config:
			raise Exception('missing portstree config for builder ' + self.name)
		if 'path' not in self.config['portstree']:
			raise Exception('missing portstree path config for builder '
				+ self.name)
		if 'packagesPath' not in self.config['portstree']:
			self.config['portstree']['packagesPath'] \
				= self.config['portstree']['path'] + '/packages'
		if 'packagesCachePath' not in self.config['portstree']:
			self.config['portstree']['packagesCachePath'] \
				= self.config['portstree']['packagesPath'] + '/.cache'
		if 'builderConfig' not in self.config['portstree']:
			self.config['portstree']['builderConfig'] \
				= self.config['portstree']['path'] + '/builder.conf'

		if 'haikuporter' not in self.config:
			self.config['haikuporter'] = {}
		if 'path' not in self.config['haikuporter']:
			self.config['haikuporter']['path'] = 'haikuporter'
		if 'args' not in self.config['haikuporter']:
			self.config['haikuporter']['args'] = ''

	def _connect(self):
		try:
			if 'jump' in self.config['ssh']:
				self.jumpClient = paramiko.SSHClient()
				self.jumpClient.load_host_keys(self.config['ssh']['knownHostsFile'])
				jPrivateKeyIO = StringIO(base64.b64decode(self.config['ssh']['jump']['privateKey']).decode("ascii"))
				jPrivateKey = paramiko.ed25519key.Ed25519Key.from_private_key(jPrivateKeyIO)
				self.logger.info('trying to connect to jumphost for builder ' + self.name)
				self.jumpClient.connect(self.config['ssh']['jump']['host'],
					port=int(self.config['ssh']['jump']['port']),
					username=self.config['ssh']['jump']['user'],
					pkey=jPrivateKey,
					compress=True, allow_agent=False, look_for_keys=False,
					timeout=10)

			self.logger.info('trying to connect to builder ' + self.name)
			self.sshClient = paramiko.SSHClient()
			self.sshClient.load_host_keys(self.config['ssh']['knownHostsFile'])
			privateKeyIO = StringIO(base64.b64decode(self.config['ssh']['privateKey']).decode("ascii"))
			privateKey = paramiko.ed25519key.Ed25519Key.from_private_key(privateKeyIO)

			if self.jumpClient != None:
				transport=self.jumpClient.get_transport().open_channel(
					'direct-tcpip', (self.config['ssh']['host'],
						int(self.config['ssh']['port'])), ('', 0))
				self.sshClient.connect(hostname=self.config['ssh']['host'],
					port=int(self.config['ssh']['port']),
					username=self.config['ssh']['user'],
					pkey=privateKey,
					compress=True, allow_agent=False, look_for_keys=False,
					timeout=10, sock=transport)
			else:
				self.sshClient.connect(hostname=self.config['ssh']['host'],
					port=int(self.config['ssh']['port']),
					username=self.config['ssh']['user'],
					pkey=privateKey,
					compress=True, allow_agent=False, look_for_keys=False,
					timeout=10)

			self.sshClient.get_transport().set_keepalive(15)
			self.logger.info('connected to builder')
			self.connectionErrors = 0
		except Exception as exception:
			self.logger.error('failed to connect to builder: '
				+ str(exception))

			self.connectionErrors += 1
			self.state = BuilderState.RECONNECT

			if self.connectionErrors >= self.maxConnectionErrors:
				self.logger.error('giving up on builder after '
					+ str(self.connectionErrors)
					+ ' consecutive connection errors')
				self.state = BuilderState.LOST
				raise

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
				'ALLOW_UNSAFE_SOURCES': Configuration.shallAllowUnsafeSources(),
				'CREATE_SOURCE_PACKAGES': Configuration.shallCreateSourcePackages()
			}
			sftp = self._sftpClient()
			with sftp.open(self.config['portstree']['builderConfig'],
					'w') as remoteFile:
				remoteFile.write(
					ConfigParser.configurationStringFromDict(config))
			sftp.close()
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
			sftp = self._sftpClient()
			for entry in sftp.listdir(
					self.config['portstree']['packagesCachePath']):
				if not entry.endswith('.hpkg'):
					continue

				if entry not in self.availablePackages:
					self.availablePackages.append(entry)
			sftp.close()
		except Exception as exception:
			self.logger.error('failed to get available packages: '
				+ str(exception))
			raise

	def _removeObsoletePackages(self):
		cachePath = self.config['portstree']['packagesCachePath']
		systemPackagesDirectory = getOption('systemPackagesDirectory')

		for entry in list(self.availablePackages):
			if self.packageRepository.hasPackage(entry):
				continue

			if os.path.exists(os.path.join(systemPackagesDirectory, entry)):
				continue

			self.logger.info(
				'removing obsolete package {} from cache'.format(entry))
			entryPath = cachePath + '/' + entry
			sftp = self._sftpClient()
			sftp.remove(entryPath)
			sftp.close()
			self.availablePackages.remove(entry)

	def _setupForBuilding(self):
		if self.state == BuilderState.AVAILABLE:
			return True
		if self.state == BuilderState.LOST:
			return False

		self._connect()
		self._validatePortsTree()
		self._syncPortsTree()
		self._writeBuilderConfig()
		self._createNeededDirs()
		self._getAvailablePackages()
		self._removeObsoletePackages()

		self.state = BuilderState.AVAILABLE
		return True

	def setBuild(self, scheduledBuild, buildNumber):
		logHandler = logging.FileHandler(os.path.join(self.buildOutputDir,
				str(buildNumber) + '.log'), encoding='utf-8')
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

			self._purgePort(scheduledBuild)
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
				+ '" --no-system-packages --no-package-obsoletion'
				+ ' --ignore-messages '
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
				self.state = BuilderState.NOT_AVAILABLE
				raise Exception('builder disconnected')

			if exitStatus != 0:
				reschedule = False
				self._purgePort(scheduledBuild)
				self._clearVisiblePackages()
				raise Exception('build failure')

			sftp = self._sftpClient()
			for package in scheduledBuild.port.packages:
				self.buildLogger.info('download package ' + package.hpkgName
					+ ' from builder')

				remotePath = self.config['portstree']['packagesPath'] + '/' \
					+ package.hpkgName
				with sftp.file(remotePath, 'r') as remoteFile:
					self.packageRepository.writePackage(package.hpkgName,
						remoteFile)
			sftp.close()
			self._purgePort(scheduledBuild)
			self._clearVisiblePackages()
			self.buildLogger.info('build completed successfully')
			buildSuccess = True

		except socket.error as exception:
			self.buildLogger.error('connection failed: ' + str(exception))
			if self.state == BuilderState.AVAILABLE:
				self.state = BuilderState.RECONNECT

		except (IOError, paramiko.ssh_exception.SSHException) as exception:
			self.buildLogger.error('builder failed: ' + str(exception))
			self.state = BuilderState.LOST

		except Exception as exception:
			self.buildLogger.info('build failed: ' + str(exception))

		if buildSuccess == False and reschedule:
			# If we are going to try again, close out any open ssh connections
			if self.sshClient != None:
				self.sshClient.close()
			if self.jumpClient != None:
				self.jumpClient.close()

		return (buildSuccess, reschedule)

	def _sftpClient(self):
		try:
			transport = self.sshClient.get_transport()
			return paramiko.SFTPClient.from_transport(transport)
		except Exception as exception:
			self.buildLogger.error('transport error getting sftp: ' + str(exception))
			return None

	def _remoteCommand(self, command):
		transport = self.sshClient.get_transport()
		channel = transport.open_session()
		channel.get_pty()
		output = channel.makefile('rb')
		channel.exec_command(command)
		return (output, channel)

	def _getFile(self, localPath, remotePath):
		for attempt in range(3):
			try:
				sftp = self._sftpClient()
				sftp.get(localPath, remotePath)
			except Exception as exception:
				sftp.close()
				self.buildLogger.error('sftp error getting ' + remotePath + ' (attempt ' + attempt + '): ' + str(exception))
				continue
			sftp.close()
			break

	def _putFile(self, remotePath, localPath):
		for attempt in range(3):
			try:
				sftp = self._sftpClient()
				sftp.put(remotePath, localPath)
			except Exception as exception:
				sftp.close()
				self.buildLogger.error('sftp error putting ' + localPath + ' (attempt ' + attempt + '): ' + str(exception))
				continue
			sftp.close()
			break

	def _symlink(self, sourcePath, destPath):
		sftp = self._sftpClient()
		sftp.symlink(sourcePath, destPath)
		sftp.close()

	def _move(self, sourcePath, destPath):
		sftp = self._sftpClient()
		sftp.posix_rename(sourcePath, destPath)
		sftp.close()

	def _ensureDirExists(self, path):
		sftp = self._sftpClient()
		try:
			attributes = sftp.stat(path)
			if not stat.S_ISDIR(attributes.st_mode):
				raise IOError(errno.EEXIST, 'file exists')
		except IOError as exception:
			if exception.errno != errno.ENOENT:
				raise
			sftp.mkdir(path)
		sftp.close()

	def _purgePort(self, scheduledBuild):
		command = ('cd "' + self.config['portstree']['path']
			+ '" && "' + self.config['haikuporter']['path']
			+ '" --config="' + self.config['portstree']['builderConfig']
			+ '" --no-package-obsoletion --ignore-messages --purge "'
			+ scheduledBuild.port.versionedName + '"')

		self.buildLogger.info('purging port with command: ' + command)
		(output, channel) = self._remoteCommand(command)
		self._appendOutputToLog(output)

	def _appendOutputToLog(self, output):
		with output:
			while True:
				line = output.readline()
				if not line:
					return

				self.buildLogger.info(
					line[:-1].decode('utf-8', errors='replace'))

	def _makePackageAvailable(self, packagePath):
		packageName = os.path.basename(packagePath)
		if packageName in self.availablePackages:
			return

		self.logger.info('upload package ' + packageName + ' to builder cache')

		entryPath \
			= self.config['portstree']['packagesCachePath'] + '/' + packageName
		uploadPath = entryPath + '.upload'

		sftp = self._sftpClient()
		with sftp.file(uploadPath, 'w') as remoteFile:
			self.packageRepository.readPackage(packagePath, remoteFile)
		sftp.close()

		self._move(uploadPath, entryPath)
		self.availablePackages.append(packageName)

	def _clearVisiblePackages(self):
		basePath = self.config['portstree']['packagesPath']
		cachePath = self.config['portstree']['packagesCachePath']
		sftp = self._sftpClient()
		for entry in sftp.listdir(basePath):
			if not entry.endswith('.hpkg'):
				continue

			entryPath = basePath + '/' + entry
			attributes = sftp.lstat(entryPath)
			if stat.S_ISLNK(attributes.st_mode):
				self.logger.debug('hiding visible package ' + entry + ' from builder cache')
				sftp.remove(entryPath)
			else:
				self.logger.info('moving real package ' + entry + ' to builder cache')
				cacheEntryPath = cachePath + '/' + entry
				self._move(entryPath, cacheEntryPath)
				self.availablePackages.append(entry)

		self.visiblePackages = []
		sftp.close()

	def _makePackageVisible(self, packagePath):
		packageName = os.path.basename(packagePath)
		if packageName in self.visiblePackages:
			return

		self.logger.info('making package ' + packageName + ' visible from builder cache')
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
