# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

# -- MachineArchitecture ------------------------------------------------------

# Defines the set of real machines architectures that are supported.
class MachineArchitecture(str):
	PPC = 'ppc'
	X86 = 'x86'
	X86_GCC2 = 'x86_gcc2'
	
	@staticmethod
	def getAll():
		# TODO: fetch this from PackageKit?
		return [
			Architectures.PPC,
			Architectures.X86,
			Architectures.X86_GCC2,
		]

	@staticmethod
	def getTripleFor(architecture):
		dict = {
			Architectures.PPC: 'powerpc-apple-haiku',
			Architectures.X86: 'i586-pc-haiku',
			Architectures.X86_GCC2: 'i586-pc-haiku_gcc2',
		}
		if architecture in dict:
			return dict[architecture]
		return None		

	@staticmethod
	def getBuildTripleFor(architecture):
		triple = MachineArchitecture.getTripleFor(architecture)
		if triple:
			triple += '_build'
		return triple


# -- Architectures ------------------------------------------------------------

# The ARCHITECTURES key in a recipe describes the port's status on each
# of the supported architectures.
# Within the string, support for an architecture can be specified like this:
#  'x86'  -> this port is known to work on the 'x86' architecture
#  '?x86' -> this port has not been built/tested on the 'x86' architecture yet,
#			it is expected to work, but that has not been verified
#  '!x86' -> this port is known to have problems on the 'x86' architecture
# An architecture missing from the status specification indicates that nothing
# is known about the status of the port on this architecture.
class Architectures(MachineArchitecture):
	ANY = 'any'
	PPC = 'ppc'
	X86 = 'x86'
	X86_GCC2 = 'x86_gcc2'
	SOURCE = 'source'
	
	@staticmethod
	def getAll():
		return MachineArchitecture.getAll() + [
			Architectures.ANY,
			Architectures.SOURCE,
		]


# -- Status -------------------------------------------------------------------

# Allowed status for a port on a specific architecure
class Status(str):
	BROKEN = 'broken'
	STABLE = 'stable'
	UNSUPPORTED = 'unsupported'
	UNTESTED = 'untested'


# -- Phase --------------------------------------------------------------------

# Identifies a phase of building a port.
class Phase(str):
	PATCH = 'PATCH'
	BUILD = 'BUILD'
	INSTALL = 'INSTALL'
	TEST = 'TEST'
	
	@staticmethod
	def getAllowedValues():
		return [ Phase.PATCH, Phase.BUILD, Phase.TEST, Phase.INSTALL ]


# -- LinesOfText --------------------------------------------------------------

# Create new type 'LinesOfText', used to handle the description in a recipe
class LinesOfText(list):
	pass


# -- YesNo --------------------------------------------------------------------

# A string representing a boolean value.
class YesNo(str):
	
	@staticmethod
	def getAllowedValues():
		return [ 'yes', 'no', 'true', 'false' ]

	@staticmethod
	def toBool(self, value):
		return value.lower() == 'yes' or value.lower() == 'true'

# -- Extendable ---------------------------------------------------------------

# Defines the possible values for the 'extendable' attribute of recipe
# attributes:
#   NO         -> The attribute is not extendable, i.e. it is per-port.
#   INHERITED  -> The attribute is extendable (i.e. per-package) and when not
#                 specified for a package, the attribute value for the main
#                 package is inherited.
#   DEFAULT    -> The attribute is extendable (i.e. per-package) and when not
#                 specified for a package, the attribute get the default value.
class Extendable(str):
	NO			= 'no',
	INHERITED	= 'inherited',
	DEFAULT		= 'default'

