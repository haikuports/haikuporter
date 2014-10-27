# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Copyright 2013 Haiku, Inc.
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.ConfigParser import ConfigParser
from HaikuPorter.Options import getOption
from HaikuPorter.RecipeTypes import (Extendable, MachineArchitecture, YesNo)
from HaikuPorter.Utils import sysExit

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
    'ALLOW_UNSAFE_SOURCES': {
        'type': YesNo,
        'required': False,
        'default': False,
        'extendable': Extendable.NO,
        'indexable': False,
        'setAttribute': 'allowUnsafeSources'
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
    'DOWNLOAD_MIRROR': {
        'type': types.StringType,
        'required': False,
        'default': 'https://ports-mirror.haiku-os.org',
        'extendable': Extendable.NO,
        'indexable': False,
        'setAttribute': 'downloadMirror',
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
    'SECONDARY_CROSS_DEVEL_PACKAGES': {
        'type': types.ListType,
        'required': False,
        'default': [],
        'extendable': Extendable.NO,
        'indexable': False,
        'optionAttribute': 'secondaryCrossDevelPackages',
        'setAttribute': 'secondaryCrossDevelPackages',
    },
    'SECONDARY_CROSS_TOOLS': {
        'type': types.ListType,
        'required': False,
        'default': [],
        'extendable': Extendable.NO,
        'indexable': False,
    },
    'SECONDARY_TARGET_ARCHITECTURES': {
        'type': types.ListType,
        'required': False,
        'default': [],
        'extendable': Extendable.NO,
        'indexable': False,
        'setAttribute': 'secondaryArchitectures',
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
        self.secondaryArchitectures = None
        self.packager = None
        self.packagerName = None
        self.packagerEmail = None
        self.allowUntested = False
        self.allowUnsafeSources = False
        self.downloadInPortDirectory = False
        self.packageCommand = None
        self.mimesetCommand = None
        self.systemMimeDB = None
        self.licensesDirectory = None
        self.crossTools = None
        self.secondaryCrossTools = {}
        self.crossDevelPackage = None
        self.secondaryCrossDevelPackages = None
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
    def getSecondaryTargetArchitectures():
        return Configuration.configuration.secondaryArchitectures

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
    def shallAllowUnsafeSources():
        return Configuration.configuration.allowUnsafeSources

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
    def getSecondaryCrossToolsDirectory(architecture):
        return Configuration.configuration.secondaryCrossTools.get(architecture)

    @staticmethod
    def getCrossDevelPackage():
        return Configuration.configuration.crossDevelPackage

    @staticmethod
    def getSecondaryCrossDevelPackage(architecture):
        return Configuration.configuration.secondaryCrossDevelPackages.get(
            architecture)

    @staticmethod
    def getOutputDirectory():
        return Configuration.configuration.outputDirectory

    @staticmethod
    def getDownloadMirror():
        return Configuration.configuration.downloadMirror

    def _readConfigurationFile(self):
        # Find the configuration file. It may be
        # * specified on the command line,
        # * in the current directory,
        # * '~/config/settings/haikuports.conf'.
        haikuportsConf = getOption('configFile')
        if not haikuportsConf:
            haikuportsConf = 'haikuports.conf'
            if not os.path.exists(haikuportsConf):
                haikuportsConf = (os.path.expanduser('~')
                    + '/config/settings/haikuports.conf')

        if not os.path.exists(haikuportsConf):
            sysExit("Unable to find haikuports.conf in known search paths.\n"
                + "See haikuports-sample.conf for more information");

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

        # get the secondary cross tools and devel packages
        if self.secondaryArchitectures:
            crossTools = configurationValue.get('SECONDARY_CROSS_TOOLS')
            if crossTools:
                if len(crossTools) != len(self.secondaryArchitectures):
                    sysExit('A cross-tools directory must be specified for '
                        'each secondary architecture')
                for architecture, tools \
                        in zip(self.secondaryArchitectures, crossTools):
                    self.secondaryCrossTools[architecture] = tools

            if self.secondaryCrossDevelPackages:
                crossDevelPackages = self.secondaryCrossDevelPackages
                self.secondaryCrossDevelPackages = {}
                if len(crossDevelPackages) != len(self.secondaryArchitectures):
                    sysExit('A cross-tools devel pacakge must be specified for '
                        'each secondary architecture')
                for architecture, package \
                        in zip(self.secondaryArchitectures, crossDevelPackages):
                    self.secondaryCrossDevelPackages[architecture] = package
            else:
                self.secondaryCrossDevelPackages = {}
        else:
            self.secondaryCrossTools = {}
            self.secondaryCrossDevelPackages = {}
