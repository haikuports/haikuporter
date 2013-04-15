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

from HaikuPorter.RecipeTypes import (ArchitecturesType, LinesOfText, PhaseType)

import types


# -- recipe keys and their attributes -----------------------------------------

recipeAttributes = {
	'ARCHITECTURES': {
		'type': ArchitecturesType,
		'required': True,
		'default': None,
	},
	'BUILD_PACKAGE_ACTIVATION_PHASE': {
		'type': PhaseType,
		'required': False,
		'default': PhaseType('BUILD'),
	},
	'BUILD_PREREQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'perPackage': True,
	},
	'BUILD_REQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'perPackage': True,
	},
	'CHECKSUM_MD5': {
		'type': types.StringType,
		'required': False,
		'default': None,
	},
	'CONFLICTS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'perPackage': True,
	},
	'COPYRIGHT': {
		'type': types.ListType,
		'required': False,
		'default': [],
	},
	'DESCRIPTION': {
		'type': LinesOfText,
		'required': True,
		'default': None,
		'perPackage': True,
	},
	'FRESHENS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'perPackage': True,
	},
	'HOMEPAGE': {
		'type': types.StringType,
		'required': True,
		'default': None,
	},
	'LICENSE': {
		'type': types.ListType,
		'required': False,
		'default': [],
	},
	'MESSAGE': {
		'type': types.StringType,
		'required': False,
		'default': None,
	},
	'PROVIDES': {
		'type': types.ListType,
		'required': True,
		'default': None,
		'perPackage': True,
	},
	'REPLACES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'perPackage': True,
	},
	'REQUIRES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'perPackage': True,
	},
	'REVISION': {
		'type': types.IntType,
		'required': True,
		'default': 1,
	},
	'SOURCE_DIR': {
		'type': types.StringType,
		'required': False,
		'default': None,
	},
	'SRC_URI': {
		'type': types.ListType,
		'required': True,
		'default': [],
	},
	'SUMMARY': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'perPackage': True,
	},
	'SUPPLEMENTS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'perPackage': True,
	},
}
