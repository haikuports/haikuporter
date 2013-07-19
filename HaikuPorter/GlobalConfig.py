# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
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

# allowed types of the /etc/haikuports.conf values
haikuportsAttributes = {
	'ALLOW_UNTESTED': {
		'type': YesNo,
		'required': False,
		'default': False,
		'extendable': Extendable.NO,
		'indexable': False,
	},
	'PACKAGER': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
	},
	'TARGET_ARCHITECTURE': {
		'type': MachineArchitecture,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
	},
	'TREE_PATH': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
	},
}


# -- global configuration -----------------------------------------------------
globalConfiguration = {}


# -- read global configuration ------------------------------------------------
def readGlobalConfiguration():
	haikuportsConf = getOption('configFile')
	configParser = ConfigParser(haikuportsConf, haikuportsAttributes)
	globalConfiguration.update(configParser.getEntriesForExtension(''))

	# check whether all required values are present
	for key in haikuportsAttributes.keys():
		if key not in globalConfiguration:
			if haikuportsAttributes[key]['required']:
				sysExit("Required value '" + key + "' not present in "
						+ haikuportsConf)

			# set default value, as no other value has been provided
			if haikuportsAttributes[key]['default'] != None:
				globalConfiguration[key] = haikuportsAttributes[key]['default']

	# determine if we are using a cross-build repository
	if os.path.exists(globalConfiguration['TREE_PATH'] + '/.cross'):
		globalConfiguration['IS_CROSSBUILD_REPOSITORY'] = True
		if 'TARGET_ARCHITECTURE' not in globalConfiguration:
			sysExit('For a cross-build repository, TARGET_ARCHITECTURE needs '
					'to be set in ' + haikuportsConf)
	else:
		globalConfiguration['IS_CROSSBUILD_REPOSITORY'] = False

	# split packager into name and email:
	m = re.match('^\s*(?P<name>.+?)\s*<(?P<email>.+?)>$',
				 globalConfiguration['PACKAGER'])
	if not m:
		sysExit("Couldn't parse name/email from PACKAGER value "
				+ globalConfiguration['PACKAGER'])
	globalConfiguration['PACKAGER_NAME'] = m.group('name')
	globalConfiguration['PACKAGER_EMAIL'] = m.group('email')

