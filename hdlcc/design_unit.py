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

from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.parsed_element import ParsedElement

_logger = logging.getLogger(__name__)

class DesignUnitType(Enum):
    package = 'package'
    entity = 'entity '
    context = 'context '

class DesignUnit(ParsedElement):

    def __init__(self, path, type_, name, locations=None):
        self._type = type_
        self._name = name
        super(DesignUnit, self).__init__(path, locations)

    def __repr__(self):
        return '{}(path="{}", name="{}", type="{}", locations="{}"'.format(
            self.__class__.__name__, self.path, self.name, self.type_,
            self.locations)

    @property
    def type_(self):
        return self._type

    @property
    def name(self):
        return self._name

    @property
    def __hash_key__(self):
        return (self.type_, self.name, super(DesignUnit, self).__hash_key__)
