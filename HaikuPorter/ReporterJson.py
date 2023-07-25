# -*- coding: utf-8 -*-
#
# Copyright 2021, Haiku, Inc. All rights reserved.
# Distributed under the terms of the MIT License.
#
# Authors:
#   Alexander von Gluck IV <kallisti5@unixzen.com>

# -- Modules ------------------------------------------------------------------

from .Utils import sysExit, warn, info
import json
import os


class ReporterJson(object):

	def __init__(self, filename, branch, architecture):
		self.filename = filename
		self.branch = branch
		self.architecture = architecture

	def connected(self):
		return True

	def updateBuildrun(self, buildNumber, status):
		tempFile = self.filename + '.temp'
		with open(tempFile, 'w') as outputFile:
			outputFile.write(json.dumps(status))
			os.rename(tempFile, self.filename)
