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
# Copyright 2016 Jerome Duval
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

from multiprocessing import cpu_count
from optparse import OptionGroup, OptionParser

from .__version__ import __version__
from .Utils import isCommandAvailable, warn

# -- global options -----------------------------------------------------------

global __Options__


# -- getOption ===-------------------------------------------------------------


def getOption(string):
    """Fetches an option by name"""

    return getattr(__Options__, string)


# -- splitCommaSeparatedList --------------------------------------------------


def setCommaSeparatedList(option, opt, value, parser):
    setattr(parser.values, option.dest, value.split(","))


# -- parseOptions -------------------------------------------------------------


def parseOptions():
    """Does command line argument parsing"""

    parser = OptionParser(
        usage="usage: %prog [options] portname[-portversion]",
        version="%prog " + __version__,
    )

    basic_actions = OptionGroup(parser, "Basic Actions", "Basic haikuporter actions")

    basic_actions.add_option(
        "-l",
        "--list",
        action="store_true",
        dest="list",
        default=False,
        help="list available ports",
    )
    basic_actions.add_option(
        "--list-packages",
        action="store_true",
        dest="listPackages",
        default=False,
        help="list available packages",
    )
    basic_actions.add_option(
        "-a",
        "--about",
        action="store_true",
        dest="about",
        default=False,
        help="show description of the specified port",
    )

    basic_actions.add_option(
        "-s",
        "--search",
        action="store_true",
        dest="search",
        default=False,
        help="search for a port (regex)",
    )
    basic_actions.add_option(
        "--search-packages",
        action="store_true",
        dest="searchPackages",
        default=False,
        help="search for a package (regex)",
    )
    basic_actions.add_option(
        "-E",
        "--enter-chroot",
        action="store_true",
        dest="enterChroot",
        default=False,
        help="just enter the chroot()-environment, do not build",
    )
    basic_actions.add_option(
        "--do-bootstrap",
        action="store_true",
        dest="doBootstrap",
        default=False,
        help="build all packages with cyclic dependencies",
    )
    basic_actions.add_option(
        "-D",
        "--analyze-dependencies",
        action="store_true",
        dest="analyzeDependencies",
        default=False,
        help=(
            "analyze dependencies between ports and print "
            "information; no port parameter required"
        ),
    )
    basic_actions.add_option(
        "-c",
        "--clean",
        action="store_true",
        dest="clean",
        default=False,
        help="clean the working directory of the specified port",
    )

    basic_actions.add_option(
        "--purge",
        action="store_true",
        dest="purge",
        default=False,
        help="clean the working directory and remove downloads of the specified port",
    )
    basic_actions.add_option(
        "-g",
        "--get",
        action="store_true",
        dest="get",
        default=False,
        help="get/update the ports tree",
    )
    basic_actions.add_option(
        "-t",
        "--tree",
        action="store_true",
        dest="tree",
        default=False,
        help="print out the location of the haikuports source tree",
    )
    basic_actions.add_option(
        "--lint",
        action="store_true",
        dest="lint",
        default=False,
        help="scan the ports tree for problems",
    )
    basic_actions.add_option(
        "--list-dependencies",
        action="store_true",
        dest="listDependencies",
        default=False,
        help="list dependencies of a port",
    )
    basic_actions.add_option(
        "--build-master",
        action="store_true",
        dest="buildMaster",
        default=False,
        help="run as build master and delegate builds to builders",
    )

    basic_flags = OptionGroup(
        parser, "Basic Options", "Basic modifications to haikuporter functionality"
    )

    basic_flags.add_option(
        "-o",
        "--location",
        action="store_true",
        dest="location",
        default=False,
        help="print out the location of a recipe (via search, for scripted editing)",
    )

    basic_flags.add_option(
        "-q",
        "--quiet",
        action="store_true",
        dest="quiet",
        default=False,
        help="suppress output from build actions",
    )
    basic_flags.add_option(
        "-v",
        "--verbose",
        action="store_true",
        dest="verbose",
        default=False,
        help="show why the recipe is broken",
    )
    basic_flags.add_option(
        "-y",
        "--yes",
        action="store_true",
        dest="yes",
        default=False,
        help="answer yes to all questions",
    )
    basic_flags.add_option(
        "-j",
        "--jobs",
        action="store",
        type="int",
        dest="jobs",
        default=cpu_count(),
        help="the number of concurrent jobs to build with",
    )
    basic_flags.add_option(
        "-S",
        "--strict-policy",
        action="store_true",
        dest="strictPolicy",
        default=False,
        help=(
            "require strict packaging policy adherence; "
            "packaging will fail on any policy violation"
        ),
    )
    basic_flags.add_option(
        "--debug",
        action="store_true",
        dest="debug",
        default=False,
        help="show Python stack traces for fatal errors",
    )

    basic_flags.add_option(
        "-n",
        "--nopatch",
        action="store_false",
        dest="patch",
        default=True,
        help="don't patch the sources, just download and unpack",
    )
    basic_flags.add_option(
        "-e",
        "--extract-patchset",
        action="store_true",
        dest="extractPatchset",
        default=False,
        help="extract current patchset(s) from port source(s)",
    )
    basic_flags.add_option(
        "-G",
        "--no-git-repo",
        action="store_true",
        dest="noGitRepo",
        default=False,
        help="don't create git-repo(s) for port source(s)",
    )
    basic_flags.add_option(
        "-B",
        "--patch-files-only",
        action="store_true",
        dest="patchFilesOnly",
        default=False,
        help=(
            "don't build the port, just download, unpack and "
            "apply patch files; don't call PATCH() though"
        ),
    )
    basic_flags.add_option(
        "-b",
        "--nobuild",
        action="store_false",
        dest="build",
        default=True,
        help="don't build the port, just download, unpack and patch",
    )
    basic_flags.add_option(
        "-p",
        "--nopackage",
        action="store_false",
        dest="package",
        default=True,
        help="don't create package, stop after build",
    )
    basic_flags.add_option(
        "--all-dependencies",
        action="store_true",
        dest="allDependencies",
        default=False,
        help="build all outdated dependencies for the given port.",
    )
    basic_flags.add_option(
        "--get-dependencies",
        action="store_true",
        dest="getDependencies",
        default=False,
        help="install all needed dependencies, then build the port",
    )
    basic_flags.add_option(
        "--update-dependencies",
        action="store_true",
        dest="updateDependencies",
        default=False,
        help=(
            "build or update required dependencies (stop on hpkg), then build the port"
        ),
    )
    basic_flags.add_option(
        "--missing-dependencies",
        action="store_true",
        dest="missingDependencies",
        default=False,
        help="build missing direct and indirect dependencies, then build the port",
    )

    basic_flags.add_option(
        "--no-source-packages",
        action="store_true",
        dest="noSourcePackages",
        default=False,
        help="don't create any source packages",
    )
    basic_flags.add_option(
        "--test",
        action="store_true",
        dest="test",
        default=False,
        help="run tests on resulting binaries",
    )
    basic_flags.add_option(
        "-C",
        "--nochroot",
        action="store_false",
        dest="chroot",
        default=True,
        help=(
            "build without a chroot()-environment - meant "
            "for debugging the build/install process"
        ),
    )
    basic_flags.add_option(
        "-f",
        "--force",
        action="store_true",
        dest="force",
        default=False,
        help="force to perform the steps (unpack, patch, build)",
    )
    basic_flags.add_option(
        "-F",
        "--preserve-flags",
        action="store_true",
        dest="preserveFlags",
        default=False,
        help="don't clear any flags when a changed recipe file is detected",
    )

    basic_flags.add_option(
        "-P",
        "--portsfile",
        action="store",
        type="string",
        dest="portsfile",
        default="",
        help="handle all ports in the given file",
    )
    basic_flags.add_option(
        "--create-source-packages",
        action="store_true",
        dest="createSourcePackages",
        default=False,
        help="build only the (regular) source packages",
    )
    basic_flags.add_option(
        "--create-source-packages-for-bootstrap",
        action="store_true",
        dest="createSourcePackagesForBootstrap",
        default=False,
        help="build only source packages as required by thebootstrap image",
    )
    basic_flags.add_option(
        "-w",
        "--why",
        action="store",
        type="string",
        dest="why",
        default="",
        help=(
            "determine why the given port is pulled in as a "
            "dependency of the port to be built"
        ),
    )

    basic_flags.add_option(
        "--config",
        action="store",
        type="string",
        dest="configFile",
        default=None,
        help=(
            "specifies the location of the global config file; "
            'the default is "~/config/settings/haikuports.conf"'
        ),
    )

    basic_flags.add_option(
        "--print-raw",
        action="store_true",
        dest="printRaw",
        default=False,
        help="print machine readable output for use by scripts",
    )

    basic_flags.add_option(
        "--print-filenames",
        action="store_true",
        dest="printFilenames",
        default=False,
        help="print filenames instead of "
        + "package names in package listings and searches",
    )

    basic_flags.add_option(
        "--ignore-messages",
        action="store_true",
        dest="ignoreMessages",
        default=False,
        help="ignore messages within recipes",
    )

    advanced_flags = OptionGroup(
        parser,
        "Advanced Options",
        "Advanced modifications to haikuporter functionality",
    )

    advanced_flags.add_option(
        "--cross-devel-package",
        action="store",
        type="string",
        dest="crossDevelPackage",
        default=None,
        help=(
            "path to the cross development package (the actual "
            '"sysroot" package); the default (when '
            "cross-building at all) is the one to be found in "
            '"/boot/system/develop/cross" matching the target '
            "architecture"
        ),
    )
    advanced_flags.add_option(
        "--secondary-cross-devel-packages",
        action="callback",
        callback=setCommaSeparatedList,
        type="string",
        dest="secondaryCrossDevelPackages",
        default=[],
        help=(
            "comma-separated list of paths to a secondary cross "
            'development package (the actual "sysroot" '
            "package); one path must be specified for each "
            "configured secondary target architecture "
            "(specified in the same order)"
        ),
    )
    advanced_flags.add_option(
        "--licenses",
        action="store",
        type="string",
        dest="licensesDirectory",
        default=None,
        help=(
            "path to the directory containing the well-known "
            "licenses; the default is "
            '"<systemDir>/data/licenses"'
        ),
    )
    advanced_flags.add_option(
        "--system-mimedb",
        action="store",
        type="string",
        dest="systemMimeDB",
        default=None,
        help=(
            "path to the directory containing the system "
            'MIME DB; the default is "<systemDir>/data/mime_db"'
        ),
    )
    advanced_flags.add_option(
        "--command-mimeset",
        action="store",
        type="string",
        dest="commandMimeset",
        default=None,
        help='specifies the "mimeset" command; the default is "mimeset"',
    )
    advanced_flags.add_option(
        "--command-package",
        action="store",
        type="string",
        dest="commandPackage",
        default=None,
        help='specifies the "package" command; the default is "package"',
    )
    advanced_flags.add_option(
        "--command-package-repo",
        action="store",
        type="string",
        dest="commandPackageRepo",
        default=None,
        help='specifies the "package_repo" command; the default is "package_repo"',
    )
    advanced_flags.add_option(
        "--cross-tools",
        action="store",
        type="string",
        dest="crossTools",
        default=None,
        help=(
            "specifies the path to the cross-tools directory "
            "created by the Haiku build system's configure "
            "script"
        ),
    )

    advanced_flags.add_option(
        "--sourceforge-mirror",
        action="store",
        type="string",
        dest="sourceforgeMirror",
        default=None,
        help="mirror to be used for sourceforge",
    )
    advanced_flags.add_option(
        "--no-system-packages",
        action="store_true",
        dest="noSystemPackages",
        default=False,
        help="do not use system packages to resolve dependencies",
    )

    advanced_flags.add_option(
        "--repository-update",
        action="store_true",
        dest="repositoryUpdate",
        default=False,
        help="update dependency infos in the repository",
    )
    advanced_flags.add_option(
        "--check-repository-consistency",
        action="store_true",
        dest="checkRepositoryConsistency",
        default=False,
        help="check the consistency of the repository",
    )
    advanced_flags.add_option(
        "--no-repository-update",
        action="store_true",
        dest="noRepositoryUpdate",
        default=False,
        help="do not update dependency infos in the repository",
    )
    advanced_flags.add_option(
        "--no-package-obsoletion",
        action="store_true",
        dest="noPackageObsoletion",
        default=False,
        help="do not move obsolete packages out of packages dir",
    )
    advanced_flags.add_option(
        "--prune-package-repository",
        action="store_true",
        dest="prunePackageRepository",
        default=False,
        help="prune the package repository",
    )
    advanced_flags.add_option(
        "--create-package-repository",
        action="store",
        type="string",
        dest="createPackageRepository",
        default=None,
        help="create a package repository at the given output path",
    )
    advanced_flags.add_option(
        "--sign-package-repository-privkey-file",
        action="store",
        type="string",
        dest="packageRepositorySignPrivateKeyFile",
        default=None,
        help="sign the package repository with the given minisign private key file",
    )
    advanced_flags.add_option(
        "--sign-package-repository-privkey-pass",
        action="store",
        type="string",
        dest="packageRepositorySignPrivateKeyPass",
        default=None,
        help="sign the package repository with the given minisign password",
    )
    advanced_flags.add_option(
        "--check-package-repository-consistency",
        action="store_true",
        dest="checkPackageRepositoryConsistency",
        default=False,
        help="check consistency of package repository by"
        + " dependency solving all packages",
    )
    advanced_flags.add_option(
        "--literal-search-strings",
        action="store_true",
        dest="literalSearchStrings",
        default=False,
        help="treat search strings as literals instead of as expressions",
    )
    advanced_flags.add_option(
        "--ports-for-files",
        action="store_true",
        dest="portsForFiles",
        default=False,
        help="list all ports affected by the supplied list of files",
    )
    advanced_flags.add_option(
        "--ports-for-packages",
        action="store_true",
        dest="portsForPackages",
        default=False,
        help="list ports producing the supplied list of packages",
    )
    advanced_flags.add_option(
        "--active-versions-only",
        action="store_true",
        dest="activeVersionsOnly",
        default=False,
        help="only check in active versions of ports instead of all ports",
    )
    advanced_flags.add_option(
        "--check-ports-releases",
        action="store_true",
        dest="checkPortsReleases",
        default=False,
        help="check for newer releases of ports published upstream",
    )

    buildmaster_flags = OptionGroup(
        parser,
        "Build Master Options",
        "Options only relevant to Haikuporter running in build master mode",
    )
    buildmaster_flags.add_option(
        "--system-packages-directory",
        action="store",
        type="string",
        dest="systemPackagesDirectory",
        default=None,
        help="specifies the directory to be used to look up system packages",
    )
    buildmaster_flags.add_option(
        "--build-master-output-dir",
        action="store",
        type="string",
        dest="buildMasterOutputDir",
        default=None,
        help="specifies where build master output shall be written",
    )
    buildmaster_flags.add_option(
        "--reporting-uri",
        action="store",
        type="string",
        dest="reportingURI",
        default=None,
        help="specifies an optional remote reporting server (ex: mongodb://)",
    )
    buildmaster_flags.add_option(
        "--local-builders",
        action="store",
        type="int",
        dest="localBuilders",
        default=0,
        help="number of local builders (native Haiku only)",
    )
    buildmaster_flags.add_option(
        "--console",
        action="store_true",
        dest="display",
        default=False,
        help="display a build master curses console",
    )

    parser.add_option_group(basic_actions)
    parser.add_option_group(basic_flags)
    parser.add_option_group(advanced_flags)
    parser.add_option_group(buildmaster_flags)

    global __Options__

    (__Options__, args) = parser.parse_args()

    # some normalization
    if (
        getOption("patchFilesOnly")
        or not getOption("patch")
        or getOption("extractPatchset")
    ):
        setattr(__Options__, "build", False)
    if not getOption("build"):
        setattr(__Options__, "package", False)
    if getOption("updateDependencies") or getOption("missingDependencies"):
        setattr(__Options__, "allDependencies", True)
    if getOption("enterChroot"):
        setattr(__Options__, "noSourcePackages", True)
    elif not isCommandAvailable("git"):
        if not getOption("doBootstrap"):
            warn("deactivating creation of source packages as 'git' is not available")
        setattr(__Options__, "noSourcePackages", True)

    return (__Options__, args)
