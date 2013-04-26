# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

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
class Architectures(str):
	ANY = 'any'
	X86 = 'x86'
	X86_GCC2 = 'x86_gcc2'
	SOURCE = 'src'
	
	@staticmethod
	def getArchitectures():
		# TODO: fetch this from PackageKit?
		return [
			Architectures.ANY,
			Architectures.X86,
			Architectures.X86_GCC2,
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
