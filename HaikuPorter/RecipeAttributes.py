# -*- coding: utf-8 -*-
# copyright 2007-2011 Brecht Machiels
# copyright 2009-2010 Chris Roberts
# copyright 2009-2011 Scott McCreary
# copyright 2009 Alexander Deynichenko
# copyright 2009 HaikuBot (aka RISC)
# copyright 2010-2011 Jack Laxson (Jrabbit)
# copyright 2011 Ingo Weinhold
# copyright 2013 Oliver Tappe

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Package import PackageType
from HaikuPorter.RecipeTypes import (Architectures, LinesOfText, Phase)

import types


# -- recipe keys and their attributes -----------------------------------------

recipeAttributes = {
	# non-extendable and non-indexable, i.e. per-port attributes
	'BUILD_PACKAGE_ACTIVATION_PHASE': {
		'type': Phase,
		'required': False,
		'default': Phase('BUILD'),
		'extendable': False,
		'indexable': False,
	},
	'HOMEPAGE': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': False,
		'indexable': False,
	},
	'MESSAGE': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': False,
		'indexable': False,
	},
	'REVISION': {
		'type': types.IntType,
		'required': True,
		'default': 1,
		'extendable': False,
		'indexable': False,
	},
				
	# indexable, i.e. per-source attributes
	'CHECKSUM_MD5': {
		'type': types.StringType,
		'required': False,
		'default': {},
		'extendable': False,
		'indexable': True,
	},
	'PATCHES': {
		'type': types.ListType,
		'required': False,
		'default': {},
		'extendable': False,
		'indexable': True,
	},
	'SOURCE_DIR': {
		'type': types.StringType,
		'required': False,
		'default': {},
		'extendable': False,
		'indexable': True,
	},
	'SRC_FILENAME': {
		'type': types.StringType,
		'required': False,
		'default': {},
		'extendable': False,
		'indexable': True,
	},
	'SRC_URI': {
		'type': types.ListType,
		'required': True,
		'default': {},
		'extendable': False,
		'indexable': True,
	},

	# extendable, i.e. per-package attributes
	'ARCHITECTURES': {
		'type': Architectures,
		'required': True,
		'default': None,
		'extendable': True,
		'indexable': False,
	},
	'BUILD_PREREQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'BUILD_REQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'CONFLICTS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'COPYRIGHT': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'DESCRIPTION': {
		'type': LinesOfText,
		'required': True,
		'default': None,
		'extendable': True,
		'indexable': False,
	},
	'FRESHENS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'GLOBAL_WRITABLE_FILES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'LICENSE': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'PACKAGE_GROUPS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'PACKAGE_USERS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'PROVIDES': {
		'type': types.ListType,
		'required': True,
		'default': None,
		'extendable': True,
		'indexable': False,
	},
	'REPLACES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'REQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'SUMMARY': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': True,
		'indexable': False,
		'suffix': {
			PackageType.DEVELOPMENT: ' (development files)',
			PackageType.DEBUG: ' (debug info)',
			PackageType.DOCUMENTATION: ' (documentation)',
			PackageType.SOURCE: ' (source files)',
		}
	},
	'SUPPLEMENTS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
	'USER_SETTINGS_FILES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
		'indexable': False,
	},
}
