# -*- coding: utf-8 -*-
#
# Copyright 2013 Oliver Tappe
# Distributed under the terms of the MIT License.

import re

# -- MachineArchitecture ------------------------------------------------------


# Defines the set of real machines architectures that are supported.
class MachineArchitecture(str):
    ## REFACTOR collections.namedtuple might make more sense

    ARM = "arm"
    ARM64 = "arm64"
    M68K = "m68k"
    PPC = "ppc"
    RISCV64 = "riscv64"
    SPARC = "sparc"
    X86 = "x86"
    X86_64 = "x86_64"
    X86_GCC2 = "x86_gcc2"

    @staticmethod
    def getAll():
        # TODO: fetch this from PackageKit?
        return [
            Architectures.ARM,
            Architectures.ARM64,
            Architectures.M68K,
            Architectures.PPC,
            Architectures.RISCV64,
            Architectures.SPARC,
            Architectures.X86,
            Architectures.X86_64,
            Architectures.X86_GCC2,
        ]

    ## REFACTOR make this a module constant as it will otherwise create an
    ## object on every call
    @staticmethod
    def getTripleFor(architecture):
        archMap = {
            Architectures.ARM: "arm-unknown-haiku",
            Architectures.ARM64: "aarch64-unknown-haiku",
            Architectures.M68K: "m68k-unknown-haiku",
            Architectures.PPC: "powerpc-apple-haiku",
            Architectures.RISCV64: "riscv64-unknown-haiku",
            Architectures.SPARC: "sparc64-unknown-haiku",
            Architectures.X86: "i586-pc-haiku",
            Architectures.X86_64: "x86_64-unknown-haiku",
            Architectures.X86_GCC2: "i586-pc-haiku",
            # Note: In theory it would make sense to use a different triple
            # for x86_gcc2. Unfortunately that would cause us a lot of work
            # to adjust the GNU autotools and autotools based build systems.
        }
        if architecture in archMap:
            return archMap[architecture]
        return None

    @staticmethod
    def findMatch(architecture):
        """Find a matching packaging architecture for the given architecture
        string that may e.g. be an architecture that uname() reports."""

        architecture = architecture.lower()
        if architecture in MachineArchitecture.getAll():
            return architecture

        # map "sparc64" to "sparc"
        if architecture == "sparc64":
            return MachineArchitecture.SPARC

        return None


# -- Architectures ------------------------------------------------------------


# The ARCHITECTURES key in a recipe describes the port's status on each
# of the supported architectures.
# Within the string, support for an architecture can be specified like this:
#  'x86'  -> this port is known to work on the 'x86' architecture
#  '?x86' -> this port has not been built/tested on the 'x86' architecture yet,
# 			it is expected to work, but that has not been verified
#  '!x86' -> this port is known to have problems on the 'x86' architecture
# An architecture missing from the status specification indicates that nothing
# is known about the status of the port on this architecture.
class Architectures(MachineArchitecture):
    ANY = "any"
    SOURCE = "source"

    @staticmethod
    def getAll():
        return MachineArchitecture.getAll() + [
            Architectures.ANY,
            Architectures.SOURCE,
        ]


# -- Status -------------------------------------------------------------------


# Allowed status for a port on a specific architecure
class Status(str):
    BROKEN = "broken"
    STABLE = "stable"
    UNSUPPORTED = "unsupported"
    UNTESTED = "untested"


# -- Phase --------------------------------------------------------------------


# Identifies a phase of building a port.
class Phase(str):
    PATCH = "PATCH"
    BUILD = "BUILD"
    INSTALL = "INSTALL"
    TEST = "TEST"

    @staticmethod
    def getAllowedValues():
        return [Phase.PATCH, Phase.BUILD, Phase.TEST, Phase.INSTALL]


# -- LinesOfText --------------------------------------------------------------


# Create new type 'LinesOfText', used to handle the description in a recipe
class LinesOfText(list):
    pass


# -- ProvidesList -------------------------------------------------------------


# Create new type 'ProvidesList', used to handle a list of provides
# specifications
class ProvidesList(list):
    pass


# -- RequiresList -------------------------------------------------------------


# Create new type 'RequiresList', used to handle a list of requires
# specifications
class RequiresList(list):
    pass


# -- YesNo --------------------------------------------------------------------


# A string representing a boolean value.
class YesNo(str):
    @staticmethod
    def getAllowedValues():
        return ["yes", "no", "true", "false"]

    @staticmethod
    def toBool(value):
        return value.lower() == "yes" or value.lower() == "true"


# -- Extendable ---------------------------------------------------------------


# Defines the possible values for the 'extendable' attribute of recipe
# attributes:
# 	NO		   -> The attribute is not extendable, i.e. it is per-port.
# 	INHERITED  -> The attribute is extendable (i.e. per-package) and when not
# 				  specified for a package, the attribute value for the main
# 				  package is inherited.
# 	DEFAULT	   -> The attribute is extendable (i.e. per-package) and when not
# 				  specified for a package, the attribute get the default value.
class Extendable(str):
    NO = ("no",)
    INHERITED = ("inherited",)
    DEFAULT = "default"
