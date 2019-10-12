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
from collections import namedtuple
from typing import Any, FrozenSet, Iterable, Optional, Set, Tuple

from hdl_checker import types as t  # pylint: disable=unused-import
from hdl_checker.utils import HashableByKey

_logger = logging.getLogger(__name__)

Location = namedtuple("Location", ["line", "column"])
LocationList = Iterable[Location]


class ParsedElement(HashableByKey):
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

        self._locations = frozenset(set_of_locations)

    @property
    def locations(self):
        return self._locations

    @property
    def __hash_key__(self):
        return (self.locations,)
