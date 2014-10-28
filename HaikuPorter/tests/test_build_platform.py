from __future__ import absolute_import


def test_build_ctor():
    from .. BuildPlatform import BuildPlatform
    build = BuildPlatform()
    build.init("", "", "", "")


def test_build_for_unix_ctor():
    from .. BuildPlatform import BuildPlatformUnix
    build = BuildPlatformUnix()
    build.init("path-to-haikuports-tree", "path-to-output-dir", True)
