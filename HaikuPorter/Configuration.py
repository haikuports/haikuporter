# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Copyright 2013 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.ConfigParser import ConfigParser
from HaikuPorter.Options import getOption
from HaikuPorter.RecipeTypes import (Extendable, MachineArchitecture, YesNo)

import os
import re
import types


# -----------------------------------------------------------------------------

# allowed types of the configuration file values
haikuportsAttributes = {
	'ALLOW_UNTESTED': {
		'type': YesNo,
		'required': False,
		'default': False,
		'extendable': Extendable.NO,
		'indexable': False,
		'setAttribute': 'allowUntested',
	},
	'CROSS_DEVEL_PACKAGE': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'optionAttribute': 'crossDevelPackage',
		'setAttribute': 'crossDevelPackage',
	},
	'CROSS_TOOLS': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'optionAttribute': 'crossTools',
		'setAttribute': 'crossTools',
	},
	'DOWNLOAD_IN_PORT_DIRECTORY': {
		'type': YesNo,
		'required': False,
		'default': False,
		'extendable': Extendable.NO,
		'indexable': False,
		'setAttribute': 'downloadInPortDirectory',
	},
	'LICENSES_DIRECTORY': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'optionAttribute': 'licensesDirectory',
		'setAttribute': 'licensesDirectory',
	},
	'MIMESET_COMMAND': {
		'type': types.StringType,
		'required': False,
		'default': 'mimeset',
		'extendable': Extendable.NO,
		'indexable': False,
		'optionAttribute': 'commandMimeset',
		'setAttribute': 'mimesetCommand',
	},
	'OUTPUT_DIRECTORY': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'setAttribute': 'outputDirectory',
	},
	'PACKAGE_COMMAND': {
		'type': types.StringType,
		'required': False,
		'default': 'package',
		'extendable': Extendable.NO,
		'indexable': False,
		'optionAttribute': 'commandPackage',
		'setAttribute': 'packageCommand',
	},
	'PACKAGER': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'setAttribute': 'packager',
	},
	'TARGET_ARCHITECTURE': {
		'type': MachineArchitecture,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'setAttribute': 'targetArchitecture',
	},
	'TREE_PATH': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'setAttribute': 'treePath',
	},
	'SYSTEM_MIME_DB': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
		'optionAttribute': 'systemMimeDB',
		'setAttribute': 'systemMimeDB',
	},
}


# -- Configuration class ------------------------------------------------------

class Configuration(object):
	configuration = None

	def __init__(self):
		self.treePath = None
		self.isCrossBuildRepository = False
		self.targetArchitecture = None
		self.packager = None
		self.packagerName = None
		self.packagerEmail = None
		self.allowUntested = False
		self.downloadInPortDirectory = False
		self.packageCommand = None
		self.mimesetCommand = None
		self.systemMimeDB = None
		self.licensesDirectory = None
		self.crossTools = None
		self.crossDevelPackage = None
		self.outputDirectory = None

		self._readConfigurationFile()

		if not self.outputDirectory:
			self.outputDirectory = self.treePath

	@staticmethod
	def init():
		Configuration.configuration = Configuration()

	@staticmethod
	def getTreePath():
		return Configuration.configuration.treePath

	@staticmethod
	def isCrossBuildRepository():
		return Configuration.configuration.isCrossBuildRepository

	@staticmethod
	def getTargetArchitecture():
		return Configuration.configuration.targetArchitecture

	@staticmethod
	def getPackager():
		return Configuration.configuration.packager

	@staticmethod
	def getPackagerName():
		return Configuration.configuration.packagerName

	@staticmethod
	def getPackagerEmail():
		return Configuration.configuration.packagerEmail

	@staticmethod
	def shallAllowUntested():
		return Configuration.configuration.allowUntested

	@staticmethod
	def shallDownloadInPortDirectory():
		return Configuration.configuration.downloadInPortDirectory

	@staticmethod
	def getPackageCommand():
		return Configuration.configuration.packageCommand

	@staticmethod
	def getMimesetCommand():
		return Configuration.configuration.mimesetCommand

	@staticmethod
	def getSystemMimeDbDirectory():
		return Configuration.configuration.systemMimeDB

	@staticmethod
	def getLicensesDirectory():
		return Configuration.configuration.licensesDirectory

	@staticmethod
	def getCrossToolsDirectory():
		return Configuration.configuration.crossTools

	@staticmethod
	def getCrossDevelPackage():
		return Configuration.configuration.crossDevelPackage

	@staticmethod
	def getOutputDirectory():
		return Configuration.configuration.outputDirectory

	def _readConfigurationFile(self):
		haikuportsConf = getOption('configFile')
		configParser = ConfigParser(haikuportsConf, haikuportsAttributes)
		configurationValue = configParser.getEntriesForExtension('')

		# check whether all required values are present
		for key in haikuportsAttributes.keys():
			if 'optionAttribute' in haikuportsAttributes[key]:
				optionAttribute = haikuportsAttributes[key]['optionAttribute']
				optionValue = getOption(optionAttribute)
				if optionValue:
					configurationValue[key] = optionValue

			if key not in configurationValue:
				if haikuportsAttributes[key]['required']:
					sysExit("Required value '" + key + "' not present in "
							+ haikuportsConf)

				# set default value, as no other value has been provided
				if haikuportsAttributes[key]['default'] != None:
					configurationValue[key] \
						= haikuportsAttributes[key]['default']

			if ('setAttribute' in haikuportsAttributes[key]
				and key in configurationValue):
				setAttribute = haikuportsAttributes[key]['setAttribute']
				setattr(self, setAttribute, configurationValue[key])


		self.treePath = self.treePath.rstrip('/')

		# determine if we are using a cross-build repository
		self.isCrossBuildRepository = os.path.exists(self.treePath + '/.cross')
		if self.isCrossBuildRepository and not self.targetArchitecture:
			sysExit('For a cross-build repository, TARGET_ARCHITECTURE '
				'needs to be set in ' + haikuportsConf)

		# split packager into name and email:
		m = re.match('^\s*(?P<name>.+?)\s*<(?P<email>.+?)>$', self.packager)
		if not m:
			sysExit("Couldn't parse name/email from PACKAGER value "
					+ self.packager)
		self.packagerName = m.group('name')
		self.packagerEmail = m.group('email')
