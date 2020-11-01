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

import logging
from typing import Iterable, Optional, Set
import abc

from hdl_checker.types import Location
from hdl_checker.utils import HashableByKey

_logger = logging.getLogger(__name__)

LocationList = Iterable[Location]


class ParsedElement(HashableByKey):
    __metaclass__ = abc.ABCMeta

    def __init__(self, locations=None):
        # type: (Optional[LocationList]) -> None
        set_of_locations = set()  # type: Set[Location]
        for line_number, column_number in locations or []:
            set_of_locations.add(
                Location(
                    None if line_number is None else int(line_number),
                    None if column_number is None else int(column_number),
                )
            )

        self._locations = tuple(set_of_locations)

    @property
    def locations(self):
        return self._locations

    @property
    def __hash_key__(self):
        return (self.locations,)

    @abc.abstractmethod
    def __len__(self):
        # type: (...) -> int
        """
        len(self) should return the length the parsed element uses on the text.
        It will be used to calculate an end position for it and allow checking
        if a given location is within the element's text
        """

    def includes(self, line, column):
        # type: (int, int) -> bool
        name_length = len(self)

        for location in self.locations:
            if line != location.line:
                continue

            if location.column <= column < location.column + name_length:
                return True
        return False
