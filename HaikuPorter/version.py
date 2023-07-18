import re
from typing import Callable, Tuple, Union

from packaging._structures import (Infinity, InfinityType, NegativeInfinity,
                                   NegativeInfinityType)
from packaging.version import InvalidVersion, Version, _cmpkey, _Version

_HPKG_REGEX: str = r"(?P<release>\d+(?:\.\d+)*)(?P<pre>[~]?(?P<pre_n>(\d+)?))(?P<post>[-]?(?P<post_n1>(\d+)?))"


InfiniteTypes = Union[InfinityType, NegativeInfinityType]
PrePostDevType = Union[InfiniteTypes, Tuple[str, int]]
SubLocalType = Union[InfiniteTypes, int, str]
LocalType = Union[
    NegativeInfinityType,
    Tuple[
        Union[
            SubLocalType,
            Tuple[SubLocalType, str],
            Tuple[NegativeInfinityType, SubLocalType],
        ],
        ...,
    ],
]
CmpKey = Tuple[int, Tuple[int, ...], PrePostDevType, PrePostDevType, PrePostDevType, LocalType]
VersionComparisonMethod = Callable[[CmpKey, CmpKey], bool]


class HpkgVersion(Version):
    _regex: re.Pattern = re.compile(_HPKG_REGEX, re.VERBOSE | re.IGNORECASE)
    # _regex: re.Pattern = re.compile(r"^\s" + _HPKG_REGEX + r"\s+$|", re.VERBOSE | re.IGNORECASE)

    def __init__(self, version: str) -> None:
        """Initialize a Version object.

        :param version:
            The string representation of a version which will be parsed and normalized
            before use.
        :raises InvalidVersion:
            If the ``version`` does not conform to PEP 440 in any way then this
            exception will be raised.
        """

        # Validate the version and parse it into pieces
        match = self._regex.search(version)
        if not match:
            raise InvalidVersion(f"Invalid version: '{version}'")

        # Store the parsed out pieces of the version
        self._version = _Version(
            epoch=0,
            release=tuple(int(i) for i in match.group("release").split(".")),
            pre=match.group("pre_n"),
            post=match.group("post_n1"),
            dev=0,
            local=(0,),
        )

        # Generate a key which will be used for sorting
        self._key = _cmpkey(
            self._version.epoch,
            self._version.release,
            self._version.pre,
            self._version.post,
            self._version.dev,
            self._version.local,
        )
