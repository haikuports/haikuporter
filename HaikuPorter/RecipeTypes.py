# -*- coding: utf-8 -*-
# copyright 2013 Oliver Tappe

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
	def getTargetTripleFor(architecture):
		dict = {
			Architectures.PPC: 'powerpc-apple-haiku',
			Architectures.X86: 'i586-pc-haiku',
			Architectures.X86_GCC2: 'i586-pc-haiku_legacy',
		}
		if architecture in dict:
			return dict[architecture]
		return None		

	@staticmethod
	def getForTargetTriple(triple):
		dict = {
			'powerpc-apple-haiku': Architectures.PPC,
			'i586-pc-haiku': Architectures.X86,
			'i586-pc-haiku_legacy': Architectures.X86_GCC2,
		}
		if triple in dict:
			return dict[triple]
		return None		

	@staticmethod
	def getHostTripleFor(architecture):
		triple = MachineArchitecture.getTargetTripleFor(architecture)
		if triple:
			triple += '_host'
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
		# TODO: fetch this from PackageKit?
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
