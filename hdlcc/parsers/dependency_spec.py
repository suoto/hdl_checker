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
from typing import Optional

from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.parsed_element import LocationList, ParsedElement

_logger = logging.getLogger(__name__)

class DependencySpec(ParsedElement):
    def __init__(self, owner, name, library, locations=None):
        # type: (t.Path, str, t.LibraryName, Optional[LocationList]) -> None
        self._owner = owner
        self._library = str(library)
        self._name = str(name)
        super(DependencySpec, self).__init__(locations)

    @property
    def owner(self):
        return self._owner

    @property
    def name(self):
        return self._name

    @property
    def library(self):
        return self._library

    @property
    def case_sensitive(self): # type: () -> bool
        ext = self.owner.split('.')[-1].lower()
        return ext not in t.FileType.vhd.value

    @property
    def __hash_key__(self):
        return (self.owner, self.library, self.name,
                super(DependencySpec, self).__hash_key__)

    def __jsonEncode__(self):
        state = super(DependencySpec, self).__jsonEncode__()
        state['library'] = state['library']
        state['name'] = state['name']
        return state

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        # pylint: disable=protected-access
        _logger.info("Recovering from %s", state)
        obj = super(DependencySpec, cls).__new__(cls)
        obj._library = state['library']
        obj._name = state['name']
        return obj

    def __repr__(self):
        return '{}(owner={}, name={}, library={}, locations={})'.format(
            self.__class__.__name__, repr(self.owner),
            repr(self.name), repr(self.library), repr(self.locations))
