# -*- coding: utf-8 -*-
#
# Copyright 2013 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Options import getOption
from HaikuPorter.Utils import (check_output, sysExit)

import re

# -- PackageInfo class --------------------------------------------------------

class PackageInfo(object):
	def __init__(self, path):
		# extract the package info from the package
		output = check_output(
			getOption('commandPackage') + ' list ' + path
			+ ' | grep -E "^[[:space:]]*[[:alpha:]]+:[[:space:]]+"',
			shell=True)

		# get the version
		match = re.search(r"version:\s*(\S+)", output)
		if not match:
			sysExit('Failed to get version of package "%s"' % path)
		self.version = match.group(1)

		# get the architecture
		match = re.search(r"architecture:\s*(\S+)", output)
		if not match:
			sysExit('Failed to get architecture of package "%s"' % path)
		self.architecture = match.group(1)

	def getVersion(self):
		return self.version

	def getArchitecture(self):
		return self.architecture
