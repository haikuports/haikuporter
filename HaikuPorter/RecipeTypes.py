# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

# -- ArchitecturesType --------------------------------------------------------

# Create new type 'ArchitecturesType' for identifying the port's status on each
# of the supported architectures.
# Within the string, support for an architecture can be specified like this:
#  'x86'  -> this port is known to work on the 'x86' architecture
#  '?x86' -> this port has not been built/tested on the 'x86' architecture yet,
#			it is expected to work, but that has not been verified
#  '!x86' -> this port is known to have problems on the 'x86' architecture
# An architecture missing from the status specification indicates that nothing
# is known about the status of the port on this architecture.
class ArchitecturesType(str):
	@staticmethod
	def getArchitectures():
		# TODO: fetch this from PackageKit?
		return [
			'any',
			'x86',
			'x86_gcc2',
		]


# -- Status -------------------------------------------------------------------

# Allowed status for a port on a specific architecure
class Status(str):
	BROKEN = 'broken'
	STABLE = 'stable'
	UNSUPPORTED = 'unsupported'
	UNTESTED = 'untested'


# -- PhaseType ----------------------------------------------------------------

# Create new type 'PhaseType' for identifying a port phase.
class PhaseType(str):
	@staticmethod
	def getAllowedValues():
		return [ 'BUILD', 'TEST', 'INSTALL' ]


# -- LinesOfText --------------------------------------------------------------

# Create new type 'LinesOfText', used to handle the description in a recipe
class LinesOfText(list):
	pass
