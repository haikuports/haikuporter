# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

from HaikuPorter.ConfigParser import ConfigParser
from HaikuPorter.Utils import sysExit

import types


# -- HaikuPorts options -------------------------------------------------------

# location of haikuports.conf
haikuportsConf = '/etc/haikuports.conf'


# -----------------------------------------------------------------------------

# allowed types of the /etc/haikuports.conf values
haikuportsAttributes = {
	'PACKAGER': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': False,
		'indexable': False,
	},
	'TREE_PATH': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': False,
		'indexable': False,
	},
}

	
# -- global configuration -----------------------------------------------------
globalConfiguration = {}


# -- read global configuration ------------------------------------------------
def readGlobalConfiguration():
		
	configParser = ConfigParser(haikuportsConf, haikuportsAttributes)
	globalConfiguration.update(configParser.getEntriesForExtension(''))

	# check whether all required values are present
	for key in haikuportsAttributes.keys():
		if (key not in globalConfiguration
			and haikuportsAttributes[key]['required']):
			sysExit("Required value '" + key + "' not present in " 
					+ haikuportsConf)
