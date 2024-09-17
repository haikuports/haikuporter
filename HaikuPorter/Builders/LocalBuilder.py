# -*- coding: utf-8 -*-
#
# Copyright 2015 Michael Lotz
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.

import json
import logging
import os
import stat
import time

from .Builder import BuilderState


class LocalBuilder(object):
	def __init__(self, name, packageRepository, outputBaseDir, options):
		self.type = "LocalBuilder"
		self.options = options
		self.name = name
		self.buildCount = 0
		self.failedBuilds = 0
		self.packageRepository = packageRepository
		self.state = BuilderState.AVAILABLE
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
			'lines': 0
		}
		filter.setBuild(self.currentBuild)

	@property
	def status(self):
		return {
			'name': self.name,
			'state': self.state,
			'currentBuild': {
				'build': self.currentBuild['status'],
				'number': self.currentBuild['number']
			} if self.currentBuild else None
		}

	def unsetBuild(self):
		self.buildLogger.removeHandler(self.currentBuild['logHandler'])
		logging.getLogger("buildLogger").removeHandler(
			self.currentBuild['logHandler'])
		self.currentBuild = None

	def runBuild(self):
		scheduledBuild = self.currentBuild['build']
