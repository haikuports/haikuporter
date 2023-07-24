# -*- coding: utf-8 -*-
#
# Copyright 2013 Ingo Weinhold
# Distributed under the terms of the MIT License.

# -- Modules ------------------------------------------------------------------

import os
import re
from subprocess import CalledProcessError, check_output

from .Options import getOption
from .PackageInfo import PackageInfo, ResolvableExpression
from .ProvidesManager import ProvidesManager
from .ShellScriptlets import getScriptletPrerequirements
from .Utils import printError, sysExit, warn


class RestartDependencyResolutionException(Exception):
    def __init__(self, packageNode, message):
        Exception.__init__(self)
        self.packageNode = packageNode
        self.message = message


# -- PackageNode class --------------------------------------------------------


class PackageNode(object):
    def __init__(self, packageInfo, isBuildhostPackage):
        self.packageInfo = packageInfo
        self.realPath = os.path.realpath(packageInfo.path)
        self.isBuildhostPackage = isBuildhostPackage
        self.dependencyCount = 0

    def __eq__(self, other):
        return (
            self.packageInfo.name == other.packageInfo.name
            and self.packageInfo.version == other.packageInfo.version
            and self.realPath == other.realPath
            and self.isBuildhostPackage == other.isBuildhostPackage
        )

    def __str__(self):
        return "%s-%s :: %s ::%s" % (
            self.packageInfo.name,
            self.packageInfo.version,
            self.realPath,
            self.isBuildhostPackage,
        )

    @property
    def versionedName(self):
        return self.packageInfo.versionedName

    @property
    def path(self):
        return self.packageInfo.path

    def bumpDependencyCount(self):
        self.dependencyCount += 1


# -- DependencyResolver class ----------------------------------------------------


class DependencyResolver(object):
    packageInfoCache = {}

    def __init__(self, buildPlatform, requiresTypes, repositories, **kwargs):
        self._providesManager = ProvidesManager()
        self._platform = buildPlatform
        self._requiresTypes = requiresTypes
        self._repositories = repositories
        self._stopAtHpkgs = kwargs.get("stopAtHpkgs", False)
        self._ignoreBase = kwargs.get("ignoreBase", False)
        self._presentDependencyPackages = kwargs.get("presentDependencyPackages", None)
        self._quiet = kwargs.get("quiet", False)
        self._updateDependencies = (
            getOption("updateDependencies") and len(repositories) > 2
        )
        self._satisfiedPackagesCache = []

        self._populateProvidesManager()

    def determineRequiredPackagesFor(self, dependencyInfoFiles):
        packageInfos = [
            self._parsePackageInfo(dif, True) for dif in dependencyInfoFiles
        ]

        errorMessages = []
        while True:
            try:
                self._packageNodes = []
                if self._presentDependencyPackages:
                    del self._presentDependencyPackages[:]

                self._pending = [PackageNode(pi, False) for pi in packageInfos]

                self._traversed = set(
                    [str(packageNode) for packageNode in self._pending]
                )

                self._buildDependencyGraph()
                break

            except RestartDependencyResolutionException as exception:
                errorMessages.append(exception.message)
                if exception.packageNode.packageInfo in packageInfos:
                    # The resolution failure has bubbled to the top, we failed.
                    raise LookupError("\n".join(errorMessages))

                self._providesManager.removeProvidesOfPackageInfo(
                    exception.packageNode.packageInfo
                )
                continue

        self._sortPackageNodesTopologically()

        result = [node.path for node in self._packageNodes]

        self._satisfiedPackagesCache += result
        return result

    def _populateProvidesManager(self):
        for repository in self._repositories:
            for entry in os.listdir(repository):
                if not (
                    entry.endswith(".DependencyInfo")
                    or entry.endswith(".hpkg")
                    or entry.endswith(".PackageInfo")
                ):
                    continue
                packageInfo = self._parsePackageInfo(
                    repository + "/" + entry, not entry.endswith(".hpkg")
                )
                if packageInfo is None:
                    continue
                self._providesManager.addProvidesFromPackageInfo(packageInfo)

    def _buildDependencyGraph(self):
        numberOfInitialPackages = len(self._pending)
        numberOfHandledPackages = 0
        while self._pending:
            packageNode = self._pending.pop(0)

            if "REQUIRES" in self._requiresTypes:
                self._addAllImmediateRequiresOf(packageNode)
            if "BUILD_REQUIRES" in self._requiresTypes:
                self._addAllImmediateBuildRequiresOf(packageNode)
            if "BUILD_PREREQUIRES" in self._requiresTypes:
                self._addAllImmediateBuildPrerequiresOf(packageNode)
            if "TEST_REQUIRES" in self._requiresTypes:
                self._addAllImmediateTestRequiresOf(packageNode)
            if "SCRIPTLET_PREREQUIRES" in self._requiresTypes:
                self._addScriptletPrerequiresOf(packageNode)

            # when the batch of passed in packages has been handled, we need
            # to activate the REQUIRES, too, since these are needed to run
            # all the following packages
            numberOfHandledPackages += 1
            if (
                numberOfHandledPackages == numberOfInitialPackages
                and "REQUIRES" not in self._requiresTypes
            ):
                self._requiresTypes.append("REQUIRES")

    def _sortPackageNodesTopologically(self):
        sortedPackageNodes = []
        while self._packageNodes:
            lowestDependencyCount = 1000000
            nodesWithLowestDependencyCount = []
            for node in self._packageNodes:
                if lowestDependencyCount > node.dependencyCount:
                    lowestDependencyCount = node.dependencyCount
                    nodesWithLowestDependencyCount = [node]
                elif lowestDependencyCount == node.dependencyCount:
                    nodesWithLowestDependencyCount.append(node)

            sortedPackageNodes += nodesWithLowestDependencyCount
            self._packageNodes = [
                node
                for node in self._packageNodes
                if node not in nodesWithLowestDependencyCount
            ]

        self._packageNodes = sortedPackageNodes

    def _addAllImmediateRequiresOf(self, requiredPackageInfo):
        packageInfo = requiredPackageInfo.packageInfo
        forBuildhost = requiredPackageInfo.isBuildhostPackage

        for requires in packageInfo.requires:
            self._addImmediate(requiredPackageInfo, requires, "requires", forBuildhost)

    def _addAllImmediateBuildRequiresOf(self, requiredPackageInfo):
        packageInfo = requiredPackageInfo.packageInfo
        forBuildhost = requiredPackageInfo.isBuildhostPackage

        for requires in packageInfo.buildRequires:
            self._addImmediate(
                requiredPackageInfo, requires, "build-requires", forBuildhost
            )

    def _addAllImmediateBuildPrerequiresOf(self, requiredPackageInfo):
        packageInfo = requiredPackageInfo.packageInfo

        for requires in packageInfo.buildPrerequires:
            self._addImmediate(requiredPackageInfo, requires, "build-prerequires", True)

    def _addAllImmediateTestRequiresOf(self, requiredPackageInfo):
        packageInfo = requiredPackageInfo.packageInfo

        for requires in packageInfo.testRequires:
            self._addImmediate(requiredPackageInfo, requires, "test-requires", False)

    def _addScriptletPrerequiresOf(self, requiredPackageInfo):
        scriptletPrerequirements = getScriptletPrerequirements()
        for requires in scriptletPrerequirements:
            self._addImmediate(
                requiredPackageInfo,
                ResolvableExpression(requires),
                "scriptlet-prerequires",
                True,
            )

    def _addImmediate(self, parent, requires, typeString, forBuildhost):
        implicitProvides = []
        if self._platform:
            implicitProvides = self._platform.getImplicitProvides(forBuildhost)

        isImplicit = requires.name in implicitProvides
        # Skip, if this is one of the implicit provides of the build platform,
        # unless we are collecting the source packages for the bootstrap, in
        # case of which we try to add all requires (as in that case the actual
        # buildhost is Haiku and we need to put the corresponding source
        # packages onto the bootstrap image).
        if isImplicit and not getOption("createSourcePackagesForBootstrap"):
            return

        # if a prerequires type is requested, priorize any hpkg fitting the
        # version requirements, and not the latest recipe.
        isPrerequiresType = typeString.endswith("-prerequires")
        provides = self._providesManager.getMatchingProvides(
            requires, isPrerequiresType, self._ignoreBase
        )

        if not provides:
            if isImplicit:
                return
            if getOption("getDependencies"):
                try:
                    print("Fetching package for " + str(requires) + " ...")
                    output = check_output(
                        ["pkgman", "install", "-y", str(requires).replace(" ", "")]
                    ).decode("utf-8")
                    for pkg in re.findall(r"://.*/([^/\n]+\.hpkg)", output):
                        pkginfo = PackageInfo("/boot/system/packages/" + pkg)
                        self._providesManager.addProvidesFromPackageInfo(pkginfo)
                        provides = self._providesManager.getMatchingProvides(
                            requires, isPrerequiresType, self._ignoreBase
                        )
                except CalledProcessError:
                    raise RestartDependencyResolutionException(
                        parent, "failed to install package for {}".format(requires)
                    )
            else:
                message = '%s "%s" of package "%s" could not be resolved' % (
                    typeString,
                    str(requires),
                    parent.versionedName,
                )
                if not self._quiet:
                    printError(message)
                raise RestartDependencyResolutionException(parent, message)

        if provides.packageInfo.path in self._satisfiedPackagesCache:
            return

        requiredPackageInfo = PackageNode(provides.packageInfo, forBuildhost)
        if requiredPackageInfo.path.endswith(".hpkg"):
            if (
                self._presentDependencyPackages is not None
                and requiredPackageInfo.path not in self._presentDependencyPackages
            ):
                self._presentDependencyPackages.append(requiredPackageInfo.path)

            self._addPackageNode(requiredPackageInfo, not self._stopAtHpkgs)
        else:
            parent.bumpDependencyCount()
            self._addPackageNode(requiredPackageInfo, True)

    def _addPackageNode(self, requiredPackageInfo, addToPending):
        if str(requiredPackageInfo) not in self._traversed:
            self._traversed.add(str(requiredPackageInfo))
            self._packageNodes.append(requiredPackageInfo)
            if addToPending:
                self._pending.append(requiredPackageInfo)

    def _parsePackageInfo(self, packageInfoFile, fatal):
        if packageInfoFile in DependencyResolver.packageInfoCache:
            return DependencyResolver.packageInfoCache[packageInfoFile]

        try:
            packageInfo = PackageInfo(packageInfoFile)
            DependencyResolver.packageInfoCache[packageInfoFile] = packageInfo
        except CalledProcessError:
            message = 'failed to parse "%s"' % packageInfoFile
            sysExit(message) if fatal else warn(message)
            return None

        return packageInfo
