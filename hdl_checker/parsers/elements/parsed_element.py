# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.
"Common characteristics of parsed elements"

import abc
import logging
from typing import Iterable

from hdl_checker.types import Location, LocationList, Range
from hdl_checker.utils import HashableByKey

_logger = logging.getLogger(__name__)


class ParsedElement(HashableByKey):
    "Parsed elements base class"
    __metaclass__ = abc.ABCMeta

    def __init__(self, ranges):
        # type: (Iterable[Range]) -> None
        self._ranges = frozenset(ranges)

    @property
    def ranges(self):
        "ranges this element was found"
        return self._ranges

    @property
    def __hash_key__(self):
        return (self.ranges,)

    @abc.abstractmethod
    def __len__(self):
        # type: (...) -> int
        """
        len(self) should return the length the parsed element uses on the text.
        It will be used to calculate an end position for it and allow checking
        if a given location is within the element's text
        """

    def includes(self, position):
        # type: (Location) -> bool
        """
        Checks if the ranges the element was found countain a given
        location
        """
        name_length = len(self)

        for location in self.ranges:
            if position.line != location.line:
                continue

            if location.column <= position.column < location.column + name_length:
                return True
        return False
