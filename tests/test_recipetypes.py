"""Unit tests for RecipeTypes.py"""
from HaikuPorter.RecipeTypes import Architectures, MachineArchitecture, Phase, YesNo
from pytest import mark

# Constant test assets necessary for testing
_ARCHITECTURE_LIST = [
    "arm",
    "arm64",
    "m68k",
    "ppc",
    "riscv64",
    "sparc",
    "sparc64",
    "x86",
    "x86_64",
    "x86_gcc2",
    "unknown_arch",
]

_EXPECTED_ARCHITECTURES_LIST = [
    "arm",
    "arm64",
    "m68k",
    "ppc",
    "riscv64",
    "sparc",
    "x86",
    "x86_64",
    "x86_gcc2",
    "any",
    "source",
]

_EXPECTED_ARCHITECTURE_LIST = [
    "arm",
    "arm64",
    "m68k",
    "ppc",
    "riscv64",
    "sparc",
    "sparc",
    "x86",
    "x86_64",
    "x86_gcc2",
    None,
]

_TRIPLETS_LIST = [
    "arm-unknown-haiku",
    "aarch64-unknown-haiku",
    "m68k-unknown-haiku",
    "powerpc-apple-haiku",
    "riscv64-unknown-haiku",
    "sparc64-unknown-haiku",
    None,  # necessary for findMath() testing
    "i586-pc-haiku",
    "x86_64-unknown-haiku",
    "i586-pc-haiku",
    None,
]


# MachineArchitecture tests
def test_machinearchitecture_getall_positive():
    """UT for getAll() - positive test case."""
    assert MachineArchitecture.getAll() == [
        "arm",
        "arm64",
        "m68k",
        "ppc",
        "riscv64",
        "sparc",
        "x86",
        "x86_64",
        "x86_gcc2",
    ]


def test_machinearchitecture_gettriplefor_positive():
    """UT for getTripleFor() - positive test case."""
    for index, value in enumerate(_ARCHITECTURE_LIST):
        assert MachineArchitecture.getTripleFor(value) == _TRIPLETS_LIST[index]


def test_machinearchitecture_findmatch_positive():
    """UT for findMatch() - positive test case."""
    for index, value in enumerate(_ARCHITECTURE_LIST):
        assert (
            MachineArchitecture.findMatch(value) == _EXPECTED_ARCHITECTURE_LIST[index]
        )


# YesNo tests
def test_yesno_getallowedvalues():
    """UT for getAllowedValues() - positive test case."""
    assert YesNo.getAllowedValues() == ["yes", "no", "true", "false"]


@mark.parametrize(
    "value, expected_response",
    [["yes", True], ["tRue", True], ["no", False], ["false", False]],
)
def test_yesno_tobool(value, expected_response):
    """UT for toBool() - positive test case."""
    assert YesNo.toBool(value) == expected_response


# Phase tests
def test_phase_getallowedvalues():
    """UT for getAllowedValues() - positive test case."""
    assert Phase.getAllowedValues() == ["PATCH", "BUILD", "TEST", "INSTALL"]


# Architectures tests
def test_architectures_getall():
    """UT for getAll() - positive test case."""
    assert Architectures.getAll() == _EXPECTED_ARCHITECTURES_LIST
