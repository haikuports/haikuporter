from HaikuPorter import version
from pytest import mark


@mark.parametrize("input_ver", ["1", "1.1", "1.1.1", "1.1.1~1", "1.1.1-1"])
def test_basic(input_ver):
    assert version.HpkgVersion(input_ver)

