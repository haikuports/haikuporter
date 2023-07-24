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

from .Builder import _BuilderState


class LocalBuilder(object):
    def __init__(self, name, packagesPath, outputBaseDir, options):
        self.options = options
        self.name = name
        self.buildCount = 0
        self.failedBuilds = 0
        self.packagesPath = packagesPath
        self.state = _BuilderState.AVAILABLE
        self.currentBuild = None

        self.buildOutputDir = os.path.join(outputBaseDir, "builds")
        if not os.path.isdir(self.buildOutputDir):
            os.makedirs(self.buildOutputDir)

        self.buildLogger = logging.getLogger("builders." + self.name + ".build")
        self.buildLogger.setLevel(logging.DEBUG)

    def setBuild(self, scheduledBuild, buildNumber):
        logHandler = logging.FileHandler(
            os.path.join(self.buildOutputDir, str(buildNumber) + ".log")
        )
        logHandler.setFormatter(logging.Formatter("%(message)s"))
        self.buildLogger.addHandler(logHandler)
        filter = ThreadFilter()
        logHandler.addFilter(filter)
        logging.getLogger("buildLogger").setLevel(logging.DEBUG)
        logging.getLogger("buildLogger").addHandler(logHandler)

        self.currentBuild = {
            "build": scheduledBuild,
            "status": scheduledBuild.status,
            "number": buildNumber,
            "logHandler": logHandler,
            "logFilter": filter,
            "startTime": None,
            "phase": "setup",
            "lines": 0,
        }
        filter.setBuild(self.currentBuild)

    def unsetBuild(self):
        self.buildLogger.removeHandler(self.currentBuild["logHandler"])
        logging.getLogger("buildLogger").removeHandler(self.currentBuild["logHandler"])
        self.currentBuild = None

    def runBuild(self):
        scheduledBuild = self.currentBuild["build"]
