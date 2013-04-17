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
	# non-extendable, i.e. per-port attributes
	'BUILD_PACKAGE_ACTIVATION_PHASE': {
		'type': Phase,
		'required': False,
		'default': Phase('BUILD'),
		'extendable': False,
	},
	'CHECKSUM_MD5': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': False,
	},
	'HOMEPAGE': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': False,
	},
	'MESSAGE': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': False,
	},
	'REVISION': {
		'type': types.IntType,
		'required': True,
		'default': 1,
		'extendable': False,
	},
	'SOURCE_DIR': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': False,
	},
	'SRC_URI': {
		'type': types.ListType,
		'required': True,
		'default': [],
		'extendable': False,
	},

	# extendable, i.e. per-package attributes
	'ARCHITECTURES': {
		'type': Architectures,
		'required': True,
		'default': None,
		'extendable': True,
	},
	'BUILD_PREREQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'BUILD_REQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'CONFLICTS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'COPYRIGHT': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'DESCRIPTION': {
		'type': LinesOfText,
		'required': True,
		'default': None,
		'extendable': True,
	},
	'FRESHENS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'LICENSE': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'NAME_EXTENSION': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': True,
	},
	'PROVIDES': {
		'type': types.ListType,
		'required': True,
		'default': None,
		'extendable': True,
	},
	'REPLACES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'REQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': True,
	},
	'SUMMARY': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': True,
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
	},
}
