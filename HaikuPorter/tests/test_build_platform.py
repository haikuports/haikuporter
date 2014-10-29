from __future__ import absolute_import

import pytest


def test_build_ctor(DummyConfiguration):
    from .. BuildPlatform import BuildPlatform
    build = BuildPlatform()
    build.init("", "", "", "")


def test_build_for_unix_ctor(DummyConfiguration):
    from .. BuildPlatform import BuildPlatformUnix
    build = BuildPlatformUnix()
    build.init("path-to-haikuports-tree", "path-to-output-dir", True)
