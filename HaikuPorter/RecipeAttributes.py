# -*- coding: utf-8 -*-
#
# Copyright 2007-2011 Brecht Machiels
# Copyright 2009-2010 Chris Roberts
# Copyright 2009-2011 Scott McCreary
# Copyright 2009 Alexander Deynichenko
# Copyright 2009 HaikuBot (aka RISC)
# Copyright 2010-2011 Jack Laxson (Jrabbit)
# Copyright 2011 Ingo Weinhold
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from HaikuPorter.Package import PackageType
from HaikuPorter.RecipeTypes import (Architectures, Extendable, LinesOfText,
									 Phase, ProvidesList, RequiresList, YesNo)
import copy
import types


# -- recipe keys and their attributes -----------------------------------------

recipeAttributes = {
	# non-extendable and non-indexable, i.e. per-port attributes
	'BUILD_PACKAGE_ACTIVATION_PHASE': {
		'type': Phase,
		'required': False,
		'default': Phase('BUILD'),
		'extendable': Extendable.NO,
		'indexable': False,
	},
	'DISABLE_SOURCE_PACKAGE': {
		'type': YesNo,
		'required': False,
		'default': False,
		'extendable': Extendable.NO,
		'indexable': False,
	},
	'HOMEPAGE': {
		'type': types.ListType,
		'required': True,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
	},
	'MESSAGE': {
		'type': types.StringType,
		'required': False,
		'default': None,
		'extendable': Extendable.NO,
		'indexable': False,
	},
	'REVISION': {
		'type': types.IntType,
		'required': True,
		'default': 1,
		'extendable': Extendable.NO,
		'indexable': False,
	},

	# indexable, i.e. per-source attributes
	'ADDITIONAL_FILES': {
		'type': types.ListType,
		'required': False,
		'default': {},
		'extendable': Extendable.NO,
		'indexable': True,
	},
	'CHECKSUM_MD5': {
		'type': types.StringType,
		'required': False,
		'default': {},
		'extendable': Extendable.NO,
		'indexable': True,
	},
	'PATCHES': {
		'type': types.ListType,
		'required': False,
		'default': {},
		'extendable': Extendable.NO,
		'indexable': True,
	},
	'SOURCE_DIR': {
		'type': types.StringType,
		'required': False,
		'default': {},
		'extendable': Extendable.NO,
		'indexable': True,
	},
	'SRC_FILENAME': {
		'type': types.StringType,
		'required': False,
		'default': {},
		'extendable': Extendable.NO,
		'indexable': True,
	},
	'SRC_URI': {
		'type': types.ListType,
		'required': True,
		'default': {},
		'extendable': Extendable.NO,
		'indexable': True,
	},

	# extendable, i.e. per-package attributes
	'ARCHITECTURES': {
		'type': Architectures,
		'required': True,
		'default': None,
		'extendable': Extendable.INHERITED,
		'indexable': False,
	},
	'BUILD_PREREQUIRES': {
		'type': RequiresList,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'BUILD_REQUIRES': {
		'type': RequiresList,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'CONFLICTS': {
		'type': RequiresList,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'COPYRIGHT': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.INHERITED,
		'indexable': False,
	},
	'DESCRIPTION': {
		'type': LinesOfText,
		'required': True,
		'default': None,
		'extendable': Extendable.INHERITED,
		'indexable': False,
	},
	'FRESHENS': {
		'type': RequiresList,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'GLOBAL_WRITABLE_FILES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'LICENSE': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.INHERITED,
		'indexable': False,
	},
	'PACKAGE_GROUPS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'PACKAGE_USERS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'PROVIDES': {
		'type': ProvidesList,
		'required': True,
		'default': None,
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'POST_INSTALL_SCRIPTS': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'REPLACES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'REQUIRES': {
		'type': RequiresList,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'SECONDARY_ARCHITECTURES': {
		'type': Architectures,
		'required': False,
		'default': [],
		'extendable': Extendable.INHERITED,
		'indexable': False,
	},
	'SUMMARY': {
		'type': types.StringType,
		'required': True,
		'default': None,
		'extendable': Extendable.INHERITED,
		'indexable': False,
		'suffix': {
			PackageType.DEVELOPMENT: ' (development files)',
			PackageType.DEBUG_INFO: ' (debug info)',
			PackageType.DOCUMENTATION: ' (documentation)',
			PackageType.SOURCE: ' (source files)',
		}
	},
	'SUPPLEMENTS': {
		'type': RequiresList,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
	'USER_SETTINGS_FILES': {
		'type': types.ListType,
		'required': False,
		'default': [],
		'extendable': Extendable.DEFAULT,
		'indexable': False,
	},
}

def getRecipeAttributes():
	return copy.deepcopy(recipeAttributes)
