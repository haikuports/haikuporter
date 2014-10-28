from __future__ import absolute_import


def test_chroot_ctor(tmpdir):
    from .. Port import  ChrootSetup
    chroot = ChrootSetup(tmpdir, [])
    assert chroot.path == tmpdir
    assert chroot.buildOk is False
    assert chroot.envVars == []
