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
""

import logging

_logger = logging.getLogger(__name__)

class DependencySpec(object):
    __hash__ = None # Force unhashable, locations can change

    def __init__(self, library, name, locations=None):
        self._library = library
        self._name = name
        self._locations = set(locations or [])
        for filename, line_number, column_number in locations or []:
            self.addLocation(filename, line_number, column_number)

    def __jsonEncode__(self):
        state = self.__dict__.copy()
        state['_locations'] = list(state['_locations'])
        return state

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        # pylint: disable=protected-access
        _logger.info("Recovering from %s", state)
        obj = super(DependencySpec, cls).__new__(cls)
        obj._library = state['_library']
        obj._name = state['_name']
        obj._locations = {tuple(x) for x in state['_locations']}
        return obj

    def addLocation(self, filename, line_number, column_number):
        self._locations.add((filename, line_number, column_number))

    @property
    def library(self):
        return self._library

    @property
    def name(self):
        return self._name

    @property
    def __eq_key__(self):
        return self.library, self.name, self._locations

    def __repr__(self):
        return '{}.{}(library={}, name={}, locations={})'.format(
            __name__, self.__class__.__name__, repr(self.library),
            repr(self.name), repr(self._locations))

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, DependencySpec):
            return self.__eq_key__ == other.__eq_key__
        return NotImplemented

    def __ne__(self, other):
        """Overrides the default implementation (unnecessary in Python 3)"""
        result = self.__eq__(other)
        if result is not NotImplemented:
            return not result
        return NotImplemented
