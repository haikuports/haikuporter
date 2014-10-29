from __future__ import absolute_import


def test_configuration(DummyConfiguration):
    cfg = DummyConfiguration.configuration
    assert cfg.treePath is None
    assert cfg.targetArchitecture is None
    assert cfg.secondaryArchitectures is None
    assert cfg.packager is None
    assert cfg.packagerName is None
    assert cfg.packagerEmail is None
    assert cfg.allowUntested is False
    assert cfg.allowUnsafeSources is False
    assert cfg.downloadInPortDirectory is False
    assert cfg.packageCommand is None
    assert cfg.mimesetCommand is None
    assert cfg.systemMimeDB is None
    assert cfg.licensesDirectory is None
    assert cfg.crossTools is None
    assert cfg.secondaryCrossTools == {}
    assert cfg.crossDevelPackage is None
    assert cfg.secondaryCrossDevelPackages is None
    assert cfg.outputDirectory is None
