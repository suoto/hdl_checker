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
from typing import Optional, Union

from .identifier import Identifier
from .parsed_element import LocationList, ParsedElement

from hdlcc import types as t  # pylint: disable=unused-import

_logger = logging.getLogger(__name__)


class DesignUnitType(Enum):
    "Specifies tracked design unit types"
    package = "package"
    entity = "entity"
    context = "context"


class _DesignUnit(ParsedElement):
    """
    Specifies a design unit (uses mostly VHDL nomenclature)
    """

    def __init__(self, owner, type_, name, locations=None):
        # type: (t.Path, DesignUnitType, Identifier, Optional[LocationList]) -> None
        self._owner = owner
        self._type = type_
        self._name = name

        super(_DesignUnit, self).__init__(locations)

    def __repr__(self):
        return '{}(name="{}", type={}, owner={}, locations={})'.format(
            self.__class__.__name__,
            self.name,
            self.type_,
            repr(self.owner),
            self.locations,
        )

    def __str__(self):
        return "{}(name={}, type={}, owner={})".format(
            self.__class__.__name__, repr(self.name), self.type_, repr(self.owner)
        )

    @property
    def owner(self):
        return self._owner

    @property
    def type_(self):
        return self._type

    @property
    def name(self):
        return self._name

    @property
    def case_sensitive(self):  # type: () -> bool
        ext = self.owner.split(".")[-1].lower()
        return ext not in t.FileType.vhd.value

    @property
    def __hash_key__(self):
        return (
            self.owner,
            self.type_,
            self.name,
            super(_DesignUnit, self).__hash_key__,
        )


class VhdlDesignUnit(_DesignUnit):
    """
    Specifies a design unit whose name is case insensitive
    """

    def __init__(self, owner, type_, name, locations=None):
        # type: (t.Path, DesignUnitType, str, Optional[LocationList]) -> None
        super(VhdlDesignUnit, self).__init__(
            owner=owner,
            type_=type_,
            name=Identifier(name, case_sensitive=False),
            locations=locations,
        )


class VerilogDesignUnit(_DesignUnit):
    """
    Specifies a design unit whose name is case sensitive
    """

    def __init__(self, owner, type_, name, locations=None):
        # type: (t.Path, DesignUnitType, str, Optional[LocationList]) -> None
        super(VerilogDesignUnit, self).__init__(
            owner=owner,
            type_=type_,
            name=Identifier(name, case_sensitive=True),
            locations=locations,
        )


tAnyDesignUnit = Union[VhdlDesignUnit, VerilogDesignUnit]
