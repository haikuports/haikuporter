# -*- coding: utf-8 -*-
#
# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.

import errno
import json
import logging
import os
import socket
import stat
import time

from .Builder import _BuilderState

# These usages kinda need refactored
from ..ConfigParser import ConfigParser
from ..Configuration import Configuration

try:
	import paramiko
except ImportError:
	paramiko = None


class RemoteBuilderSSH(object):

	def __init__(self, configFilePath, packagesPath, outputBaseDir, portsTreeOriginURL,
	             portsTreeHead):
		self._loadConfig(configFilePath)
		self.availablePackages = []
		self.visiblePackages = []
		self.portsTreeOriginURL = portsTreeOriginURL
		self.portsTreeHead = portsTreeHead
		self.packagesPath = packagesPath

		if not paramiko:
			raise Exception('paramiko unavailable')

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

		if 'hostKeyFile' not in self.config['ssh']:
			self.logger.warning('Missing hostKeyFile for builder ' + self.name)

		formatter = logging.Formatter('%(asctime)s: %(message)s')
		logHandler = logging.FileHandler(os.path.join(self.builderOutputDir,
		                                              self.name + '.log'),
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

		if 'ssh' not in self.config:
			raise Exception('missing ssh config for builder ' + self.name)
		if 'port' not in self.config['ssh']:
			self.config['ssh']['port'] = 22
		if 'user' not in self.config['ssh']:
			raise Exception('missing ssh user config for builder ' + self.name)
		if 'host' not in self.config['ssh']:
			raise Exception('missing ssh host config for builder ' + self.name)
		if 'privateKeyFile' not in self.config['ssh']:
			raise Exception('missing ssh privateKeyFile config for builder ' +
			                self.name)
		if not os.path.isabs(self.config['ssh']['privateKeyFile']):
			self.config['ssh']['privateKeyFile'] = os.path.join(
			    os.path.dirname(configFilePath), self.config['ssh']['privateKeyFile'])

		if 'hostKeyFile' not in self.config['ssh']:
			raise Exception('missing ssh hostKeyFile config for builder' + self.name)
		if not os.path.isabs(self.config['ssh']['hostKeyFile']):
			self.config['ssh']['hostKeyFile'] = os.path.join(
			    os.path.dirname(configFilePath), self.config['ssh']['hostKeyFile'])

		if 'portstree' not in self.config:
			raise Exception('missing portstree config for builder ' + self.name)
		if 'path' not in self.config['portstree']:
			raise Exception('missing portstree path config for builder ' + self.name)
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
			self.sshClient = paramiko.SSHClient()
			self.sshClient.load_host_keys(self.config['ssh']['hostKeyFile'])
			self.logger.info('trying to connect to builder ' + self.name)
			self.sshClient.connect(hostname=self.config['ssh']['host'],
			                       port=int(self.config['ssh']['port']),
			                       username=self.config['ssh']['user'],
			                       key_filename=self.config['ssh']['privateKeyFile'],
			                       compress=True,
			                       allow_agent=False,
			                       look_for_keys=False,
			                       timeout=10)

			self.sshClient.get_transport().set_keepalive(15)
			self.sftpClient = self.sshClient.open_sftp()

			self.logger.info('connected to builder')
			self.connectionErrors = 0
		except Exception as exception:
			self.logger.error('failed to connect to builder: ' + str(exception))

			self.connectionErrors += 1
			self.state = _BuilderState.RECONNECT

			if self.connectionErrors >= self.maxConnectionErrors:
				self.logger.error('giving up on builder after ' +
				                  str(self.connectionErrors) +
				                  ' consecutive connection errors')
				self.state = _BuilderState.LOST
				raise

			# avoid DoSing the remote host, increasing delay as retries increase.
			time.sleep(5 + (1.2 * self.connectionErrors))
			raise

	def _validatePortsTree(self):
		try:
			command = ('if [ ! -d "' + self.config['portstree']['path'] + '" ]; ' +
			           'then git clone "' + self.portsTreeOriginURL + '" ' +
			           self.config['portstree']['path'] + '; fi')
			self.logger.info('running command: ' + command)
			(output, channel) = self._remoteCommand(command)
			return channel.recv_exit_status() == 0
		except Exception as exception:
			self.logger.error('failed to validate ports tree: ' + str(exception))
			raise

	def _syncPortsTree(self):
		try:
			command = ('cd "' + self.config['portstree']['path'] +
			           '" && git fetch && git checkout ' + self.portsTreeHead)
			self.logger.info('running command: ' + command)
			(output, channel) = self._remoteCommand(command)
			if channel.recv_exit_status() != 0:
				raise Exception('sync command failed')
		except Exception as exception:
			self.logger.error('failed to sync ports tree: ' + str(exception))
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

			with self._openRemoteFile(self.config['portstree']['builderConfig'],
			                          'w') as remoteFile:
				remoteFile.write(ConfigParser.configurationStringFromDict(config))
		except Exception as exception:
			self.logger.error('failed to write builder config: ' + str(exception))
			raise

	def _createNeededDirs(self):
		try:
			self._ensureDirExists(self.config['portstree']['packagesPath'])
			self._ensureDirExists(self.config['portstree']['packagesCachePath'])
		except Exception as exception:
			self.logger.error('failed to create needed dirs: ' + str(exception))
			raise

	def _getAvailablePackages(self):
		try:
			self._clearVisiblePackages()

			for entry in self._listDir(self.config['portstree']['packagesCachePath']):
				if not entry.endswith('.hpkg'):
					continue

				if entry not in self.availablePackages:
					self.availablePackages.append(entry)
		except Exception as exception:
			self.logger.error('failed to get available packages: ' + str(exception))
			raise

	def _removeObsoletePackages(self):
		cachePath = self.config['portstree']['packagesCachePath']
		for entry in list(self.availablePackages):
			if not os.path.exists(os.path.join(self.packagesPath, entry)):
				self.logger.info(
				    'removing obsolete package {} from cache'.format(entry))
				entryPath = cachePath + '/' + entry
				self.sftpClient.remove(entryPath)
				self.availablePackages.remove(entry)

	def _setupForBuilding(self):
		if self.state == _BuilderState.AVAILABLE:
			return True
		if self.state == _BuilderState.LOST:
			return False

		self._connect()
		self._validatePortsTree()
		self._syncPortsTree()
		self._writeBuilderConfig()
		self._createNeededDirs()
		self._getAvailablePackages()
		self._removeObsoletePackages()

		self.state = _BuilderState.AVAILABLE
		return True

	def setBuild(self, scheduledBuild, buildNumber):
		logHandler = logging.FileHandler(os.path.join(self.buildOutputDir,
		                                              str(buildNumber) + '.log'),
		                                 encoding='utf-8')
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

			self.buildLogger.info('building port ' + scheduledBuild.port.versionedName)

			# TODO: We don't actually want to source the build host environment
			# but the one from within the provided Haiku package. This does
			# clash with the manipulation of PATH that is done by haikuporter
			# to support secondary architectures and cross builds. Ideally the
			# shell scriptlet to set up the chroot environment would take over
			# these tasks and would initially source the environment from within
			# the chroot and then do any necessary manipulation.
			command = ('source /boot/system/boot/SetupEnvironment' + ' && cd "' +
			           self.config['portstree']['path'] + '" && "' +
			           self.config['haikuporter']['path'] + '" --config="' +
			           self.config['portstree']['builderConfig'] +
			           '" --no-system-packages --no-package-obsoletion' +
			           ' --ignore-messages ' + self.config['haikuporter']['args'] +
			           ' "' + scheduledBuild.port.versionedName + '"')

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
				self._purgePort(scheduledBuild)
				self._clearVisiblePackages()
				raise Exception('build failure')

			for package in scheduledBuild.port.packages:
				self.buildLogger.info('download package ' + package.hpkgName +
				                      ' from builder')

				packageFile = os.path.join(self.packagesPath, package.hpkgName)
				downloadFile = packageFile + '.download'
				self._getFile(
				    self.config['portstree']['packagesPath'] + '/' + package.hpkgName,
				    downloadFile)
				os.rename(downloadFile, packageFile)

			self._purgePort(scheduledBuild)
			self._clearVisiblePackages()
			self.buildLogger.info('build completed successfully')
			buildSuccess = True

		except socket.error as exception:
			self.buildLogger.error('connection failed: ' + str(exception))
			if self.state == _BuilderState.AVAILABLE:
				self.state = _BuilderState.RECONNECT

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
		output = channel.makefile('rb')
		channel.exec_command(command)
		return (output, channel)

	def _getFile(self, localPath, remotePath):
		self.sftpClient.get(localPath, remotePath)

	def _putFile(self, remotePath, localPath):
		self.sftpClient.put(remotePath, localPath)

	def _symlink(self, sourcePath, destPath):
		self.sftpClient.symlink(sourcePath, destPath)

	def _move(self, sourcePath, destPath):
		# Unfortunately we can't use SFTPClient.rename as that uses the rename
		# command (vs. posix-rename) which uses hardlinks which fail on BFS
		(output,
		 channel) = self._remoteCommand('mv "' + sourcePath + '" "' + destPath + '"')
		if channel.recv_exit_status() != 0:
			raise IOError('failed moving {} to {}'.format(sourcePath, destPath))

	def _openRemoteFile(self, path, mode):
		return self.sftpClient.open(path, mode)

	def _ensureDirExists(self, path):
		try:
			attributes = self.sftpClient.stat(path)
			if not stat.S_ISDIR(attributes.st_mode):
				raise IOError(errno.EEXIST, 'file exists')
		except IOError as exception:
			if exception.errno != errno.ENOENT:
				raise

			self.sftpClient.mkdir(path)

	def _listDir(self, remotePath):
		return self.sftpClient.listdir(remotePath)

	def _purgePort(self, scheduledBuild):
		command = ('cd "' + self.config['portstree']['path'] + '" && "' +
		           self.config['haikuporter']['path'] + '" --config="' +
		           self.config['portstree']['builderConfig'] +
		           '" --no-package-obsoletion --ignore-messages --purge "' +
		           scheduledBuild.port.versionedName + '"')

		self.buildLogger.info('purging port with command: ' + command)
		(output, channel) = self._remoteCommand(command)
		self._appendOutputToLog(output)

	def _appendOutputToLog(self, output):
		with output:
			while True:
				line = output.readline()
				if not line:
					return

				self.buildLogger.info(line[:-1].decode('utf-8', errors='replace'))

	def _makePackageAvailable(self, packagePath):
		packageName = os.path.basename(packagePath)
		if packageName in self.availablePackages:
			return

		self.logger.info('upload package ' + packageName + ' to builder')

		entryPath \
         = self.config['portstree']['packagesCachePath'] + '/' + packageName
		uploadPath = entryPath + '.upload'

		self._putFile(packagePath, uploadPath)
		self._move(uploadPath, entryPath)

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
				self.logger.info('moving package ' + entry + ' to cache')
				cacheEntryPath = cachePath + '/' + entry
				self._move(entryPath, cacheEntryPath)
				self.availablePackages.append(entry)

		self.visiblePackages = []

	def _makePackageVisible(self, packagePath):
		packageName = os.path.basename(packagePath)
		if packageName in self.visiblePackages:
			return

		self.logger.debug('making package ' + packageName + ' visible')
		self._symlink(self.config['portstree']['packagesCachePath'] + '/' + packageName,
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
