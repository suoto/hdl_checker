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
from enum import Enum
from typing import Optional

from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.parsed_element import LocationList, ParsedElement

_logger = logging.getLogger(__name__)

class DesignUnitType(Enum):
    "Specifies tracked design unit types"
    package = 'package'
    entity = 'entity'
    context = 'context'

class DesignUnit(ParsedElement):
    """
    Specifies a design unit (uses mostly VHDL nomenclature)
    """

    def __init__(self, path, type_, name, locations=None):
        # type: (t.Path, DesignUnitType, str, Optional[LocationList]) -> None
        self._path = path
        self._type = type_
        self._name = name
        super(DesignUnit, self).__init__(locations)

    def __repr__(self):
        return '{}(path="{}", name="{}", type="{}", locations="{}"'.format(
            self.__class__.__name__, self.path, self.name, self.type_,
            self.locations)

    @property
    def path(self):
        return self._path

    @property
    def type_(self):
        return self._type

    @property
    def name(self):
        return self._name

    @property
    def __hash_key__(self):
        return (self.path, self.type_, self.name, super(DesignUnit, self).__hash_key__)
