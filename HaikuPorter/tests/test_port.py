from __future__ import absolute_import


def test_chroot_ctor(tmpdir):
    from .. Port import  ChrootSetup
    chroot = ChrootSetup(tmpdir, [])
    assert chroot.path == tmpdir
    assert chroot.buildOk is False
    assert chroot.envVars == []


def test_port_ctor():
    from .. Port import Port
    port = Port(
        name="test",
        version="0.1",
        category="",
        baseDir="/",
        outputDir="/",
        globalShellVariables={},
        policy=None,
        )
    assert port.baseName == "test"
    assert port.secondaryArchitecture is None
    assert port.version == "0.1"
    assert port.versionedName == "test-0.1"
    assert port.category == ""
    assert port.baseDir == "/"
    assert port.outputDir == ""
    assert port.recipeIsBroken is False
    assert port.recipeHasBeenParsed is False

    assert port.workDir == ""
    assert port.effectiveTargetArchitecture == ""
    assert port.isMetaPort is False

    assert port.recipeFilePath == ""
    assert port.packageInfoName == ""
    assert port.revision is None
    assert port.fullVersion is None
    assert port.revisionedName is None
    assert port.definedPhases == []

    assert port.shellVariables == {}
    assert port.buildArchitecture == ""
    assert port.targetArchitecture == ""
    assert port.hostArchitecture == ""
    assert port.allPackages == []
    assert port.packages == []

    assert port.downloadDir == ""
    assert port.patchesDir == ""
    assert port.licensesDir == ""
    assert port.additionalFilesDir == ""

    assert port.sourceBaseDir == ""
    assert port.packageInfoDir == ""
    assert port.buildPackageDir == ""
    assert port.packagingBaseDir == ""
    assert port.hpkgDir == ""
    assert port.preparedRecipeFile == ""
    assert port.policy is None
    assert port.requiresUpdater is None
