# -*- coding: utf-8 -*-
#
# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Copyright 2017-2020 Haiku, Inc. All rights reserved.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import json
import logging
import os
import subprocess
import threading
import time

from .Builders.Builder import BuilderState
from .Builders.LocalBuilder import LocalBuilder
from .Builders.RemoteBuilderSSH import RemoteBuilderSSH
from .Configuration import Configuration
from .Options import getOption
from .Port import Port
from .ReporterJson import ReporterJson
from .ReporterMongo import ReporterMongo
from .Utils import ensureCommandIsAvailable, info, sysExit, warn, important


class ThreadFilter(object):
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


class ScheduledBuild(object):
	def __init__(self, port, portsTreePath, missingPackageIDs,
		packageRepository, presentDependencyPackages):
		self.port = port
		self.recipeFilePath \
			= os.path.relpath(port.recipeFilePath, portsTreePath)
		self.resultingPackages \
			= [package.hpkgName for package in self.port.packages]
		self.packageRepository = packageRepository
		self.requiredPackages = presentDependencyPackages
		self.requiredPackageIDs = [
			os.path.basename(path) for path in presentDependencyPackages]
		self.missingPackageIDs = set(missingPackageIDs)
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
					self.packageRepository.packagePath(package.hpkgName))
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


class SkippedBuild(object):
	def __init__(self, portsTreePath, port, reason):
		if isinstance(port, Port):
			self.port = port
			self.recipeFilePath \
				= os.path.relpath(port.recipeFilePath, portsTreePath)
			self.resultingPackages \
				= [package.hpkgName for package in port.packages]
		else:
			self.port = None
			self.name = port
			self.recipeFilePath = ''
			self.resultingPackages = []

		self.reason = reason

	@property
	def status(self):
		return {
			'port': {
				'name': self.port.name if self.port else self.name,
				'version': self.port.version if self.port else '',
				'revision': self.port.revision if self.port else '',
				'revisionedName': \
					self.port.revisionedName if self.port else self.name,
				'recipeFilePath': self.recipeFilePath
			},
			'resultingPackages': self.resultingPackages,
			'reason': self.reason
		}


class BuildRecord(object):
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


class BuildMaster(object):
	def __init__(self, portsTreePath, packageRepository, options):
		self.portsTreePath = portsTreePath
		self._fillPortsTreeInfo()

		self.activeBuilders = []
		self.reconnectingBuilders = []
		self.lostBuilders = []
		self.availableBuilders = []
		self.packageRepository = packageRepository
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

		# Prevents the 'haiku package requirement not met' error
		# These system packages are uploaded to every builder and used as the
		# base set of packages for builds
		if not getOption('systemPackagesDirectory'):
			raise Exception('Error: Must provide --system-packages-directory flag in build-master'
				' mode for global builder package solving')

		self.localBuilders = getOption('localBuilders')
		self.remoteAvailable = False

		logHandler = logging.FileHandler(
			os.path.join(self.buildOutputBaseDir, 'master.log'))
		logHandler.setFormatter(logging.Formatter('%(asctime)s: %(message)s'))

		self.logger = logging.getLogger('buildMaster')
		self.logger.setLevel(logging.DEBUG)
		self.logger.addHandler(logHandler)

		self.logger.info('portstree head is at ' + self.portsTreeHead)

		# Setup our reporting engine
		self.reporter = None
		reportURI = Configuration.getReportingURI()
		if reportURI == None:
			reportFile = os.path.join(self.buildOutputBaseDir, 'status.json')
			info("Reporting to " + reportFile)
			self.reporter = ReporterJson(reportFile, "master",
				Configuration.getTargetArchitecture())
			if not self.reporter.connected():
				sysExit('unable to setup json reporting engine')
		elif reportURI.startswith("mongodb://"):
			self.reporter = ReporterMongo(reportURI, "master",
				Configuration.getTargetArchitecture())
			if not self.reporter.connected():
				sysExit('unable to connect to reporting engine @ ' + reportURI)

		if self.localBuilders == 0:
			info('loading builders from ' + self.builderBaseDir)
			for fileName in os.listdir(self.builderBaseDir):
				configFilePath = os.path.join(self.builderBaseDir, fileName)
				if not configFilePath.endswith(".json"):
					continue
				if not os.path.isfile(configFilePath):
					continue

				builder = None
				try:
					info('loading builder ' + configFilePath)
					builder = RemoteBuilderSSH(configFilePath,
						packageRepository, self.buildOutputBaseDir,
						self.portsTreeOriginURL, self.portsTreeHead)
				except Exception as exception:
					self.logger.error('failed to add builder from config '
						+ configFilePath + ':' + str(exception))
					continue

				self.remoteAvailable = True
				self.activeBuilders.append(builder)
		else:
			logger = logging.getLogger("buildLogger")
			for h in logger.handlers:
				logger.removeHandler(h)
			for i in range(0, self.localBuilders):
				builder = None
				try:
					builder = LocalBuilder(str(i), packageRepository,
						self.buildOutputBaseDir, options)
				except Exception as exception:
					self.logger.error('failed to add local builder: '
						+ str(exception))
					continue

				self.activeBuilders.append(builder)

		print('Active builder count: ' + str(len(self.activeBuilders)))
		for i in self.activeBuilders:
			print('  builder: ' + str(i.name) + ' (' + str(i.type) + ')')

		if len(self.activeBuilders) == 0:
			sysExit('no builders available')

		self.availableBuilders += self.activeBuilders

		self.scheduledBuilds = []
		self.activeBuilds = []
		self.blockedBuilds = []
		self.completeBuilds = []
		self.failedBuilds = []
		self.lostBuilds = []
		self.skippedBuilds = []
		self.buildHistory = []
		self.totalBuildCount = 0
		self.startTime = None
		self.endTime = None
		self.impulseData = [None] * 500
		self.impulseIndex = -1

		self.buildableCondition = threading.Condition()
			# protectes the scheduled builds lists
		self.builderCondition = threading.Condition()
			# protects the builders lists
		self.statusLock = threading.Lock()

		self._setBuildStatus('preparing')

	def addSkipped(self, port, reason):
		portName = port.revisionedName if isinstance(port, Port) else port
		warn('skipped port {}: {}'.format(portName, reason))

		skippedBuild = SkippedBuild(self.portsTreePath, port, reason)
		self.skippedBuilds.append(skippedBuild)
		self._reportStatus()

	def schedule(self, port, missingPackageIDs, presentDependencyPackages):
		# Skip builds that would overwrite existing packages.
		for package in port.packages:
			if not self.packageRepository.hasPackage(package.hpkgName):
				continue

			self.addSkipped(port, 'some packages already exist in package'
				+ ' repository, revision bump required')
			return

		self.logger.info('scheduling build of ' + port.versionedName)
		scheduledBuild = ScheduledBuild(port, self.portsTreePath,
			missingPackageIDs, self.packageRepository,
			presentDependencyPackages)

		if scheduledBuild.buildable:
			self.scheduledBuilds.append(scheduledBuild)
		else:
			self.blockedBuilds.append(scheduledBuild)

		self._setBuildStatus('scheduling')

	def runBuilds(self):
		# Move anything to the lost state that depends on skipped builds.
		for skippedBuild in self.skippedBuilds:
			if skippedBuild.port:
				self._packagesCompleted(skippedBuild.port.packages, False)

		try:
			self._ensureConsistentSchedule()
			self.totalBuildCount = len(self.scheduledBuilds) + len(self.blockedBuilds)
			self.startTime = time.time()
			self._setBuildStatus('starting builds')
			while True:
				self._runBuilds()
				self._waitForBuildsToComplete()
				if len(self.scheduledBuilds) == 0:
					break

			failures = len(self.failedBuilds) + len(self.lostBuilds)
			if failures > 0:
				exitStatus = 'complete (with ' + str(failures) + ' failures)'
			else:
				exitStatus = 'complete'
		except KeyboardInterrupt:
			exitStatus = 'aborted'
		except Exception as exception:
			self.logger.error(str(exception))
			exitStatus = 'failed: ' + str(exception)

		self.logger.info('finished with status: ' + exitStatus)
		self.endTime = time.time()
		self._setBuildStatus(exitStatus)

	def _fillPortsTreeInfo(self):
		try:
			ensureCommandIsAvailable('git')
			origin = subprocess.check_output(['git', 'remote', 'get-url',
					'origin'], cwd=self.portsTreePath, stderr=subprocess.STDOUT).decode('utf-8')
			head = subprocess.check_output(['git', 'rev-parse', 'HEAD'],
				cwd=self.portsTreePath, stderr=subprocess.STDOUT).decode('utf-8')
		except:
			warn('unable to determine origin and revision of haikuports tree')
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
					self.buildableCondition.wait(1)
					continue
				else:
					break

			self._runBuild(buildToRun)

	def _waitForBuildsToComplete(self):
		while True:
			with self.builderCondition:
				if len(self.availableBuilders) == len(self.activeBuilders):
					break
				worker_names = list(map(lambda x: x.name, self.activeBuilders))
				self._setBuildStatus('waiting for workers ' + ','.join(worker_names) + ' to complete')
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
					sysExit('all builders lost')

				if len(self.availableBuilders) == 0:
					self._setBuildStatus('waiting for available builders')
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
		self._reportStatus()
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
			self._buildComplete(scheduledBuild, buildSuccess,
				self.completeBuilds if buildSuccess else self.failedBuilds)

		with self.builderCondition:
			if builder.state == BuilderState.LOST:
				self.logger.error('builder ' + builder.name + ' lost')
				self.activeBuilders.remove(builder)
				self.lostBuilders.append(builder)
			elif builder.state == BuilderState.RECONNECT:
				self.logger.error(
					'builder ' + builder.name + ' is reconnecting')
				self.activeBuilders.remove(builder)
				self.reconnectingBuilders.append(builder)
			else:
				self.availableBuilders.append(builder)

			self.builderCondition.notify()

		self._reportStatus()

	def _ensureConsistentSchedule(self):
		buildingPackagesIDs = []
		for scheduledBuild in self.scheduledBuilds + self.blockedBuilds:
			for package in scheduledBuild.port.packages:
				if package.versionedName not in buildingPackagesIDs:
					buildingPackagesIDs.append(package.versionedName)

		brokenBuilds = []
		for blockedBuild in self.blockedBuilds:
			for missingPackageID in blockedBuild.missingPackageIDs:
				if missingPackageID not in buildingPackagesIDs:
					self.logger.error('missing package ' + missingPackageID
						+ ' of blocked build ' + blockedBuild.port.versionedName
						+ ' is not scheduled')
					brokenBuilds.append(blockedBuild)
					break

		for brokenBuild in brokenBuilds:
			self._buildComplete(brokenBuild, False, self.lostBuilds)

		for lostBuild in self.lostBuilds:
			if lostBuild in self.blockedBuilds:
				self.blockedBuilds.remove(lostBuild)

	@property
	def status(self):
		return {
			'builds': {
				'active': [build.status for build in self.activeBuilds],
				'scheduled': [build.status for build in self.scheduledBuilds],
				'blocked': [build.status for build in self.blockedBuilds],
				'complete': [build.status for build in self.completeBuilds],
				'failed': [build.status for build in self.failedBuilds],
				'lost': [build.status for build in self.lostBuilds],
				'skipped': [build.status for build in self.skippedBuilds]
			},
			'builders': {
				'active': [builder.status for builder in self.activeBuilders
						if builder.currentBuild is not None],
				'reconnecting':
					[builder.status for builder in self.reconnectingBuilders],
				'idle': [builder.status for builder in self.activeBuilders
						if builder.currentBuild is None],
				'lost': [builder.status for builder in self.lostBuilders]
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
		if buildStatus != self.buildStatus:
			important('Update: ' + buildStatus)
			self.buildStatus = buildStatus
		self._reportStatus()

	def _reportStatus(self):
		if not self.reporter:
			return
		with self.statusLock:
			self.reporter.updateBuildrun(self.buildNumber, self.status)
