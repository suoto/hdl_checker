# This file is part of HDL Code Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Code Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Code Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Code Checker.  If not, see <http://www.gnu.org/licenses/>.

import logging
from typing import FrozenSet, Optional, Set, Tuple

from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.utils import HashableByKey

_logger = logging.getLogger(__name__)

Location = Tuple[t.Path, Optional[int], Optional[int]]
LocationList = FrozenSet[Location]

class ParsedElement(HashableByKey):

    def __init__(self, path, locations=None):
        # type: (t.Path, Optional[LocationList]) -> None
        self._path = path
        set_of_locations = set()  # type: Set[Location]
        for filename, line_number, column_number in locations or []:
            set_of_locations.add((
                t.Path(filename),
                None if line_number is None else line_number,
                None if column_number is None else column_number))

        self._locations = frozenset(set_of_locations)

    @property
    def path(self):
        return self._path

    @property
    def locations(self):
        return self._locations

    def __jsonEncode__(self):
        return {'path': self.path,
                'location': self.locations}

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        # pylint: disable=protected-access
        _logger.info("Recovering from %s", state)
        obj = super(ParsedElement, cls).__new__(cls)
        obj._path = state['path']
        obj._locations = {tuple(x) for x in state['locations']}
        return obj

    @property
    def __hash_key__(self):
        return (self.path, self.locations)