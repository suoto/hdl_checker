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
"Class defining a parsed design unit"

import logging
from typing import Optional, Union

from .identifier import (  # pylint: disable=unused-import
    Identifier,
    VerilogIdentifier,
    VhdlIdentifier,
)
from .parsed_element import LocationList, ParsedElement  # pylint: disable=unused-import

from hdl_checker.path import Path  # pylint: disable=unused-import
from hdl_checker.types import DesignUnitType  # pylint: disable=unused-import

_logger = logging.getLogger(__name__)


class _DesignUnit(ParsedElement):
    """
    Specifies a design unit (uses mostly VHDL nomenclature)
    """

    def __init__(self, owner, type_, name, locations=None):
        # type: (Path, DesignUnitType, Identifier, Optional[LocationList]) -> None
        self._owner = owner
        self._type = type_
        self._name = name

        super(_DesignUnit, self).__init__(locations)

    def __len__(self):
        return len(self.name)

    def __repr__(self):
        return '{}(name="{}", type={}, owner={}, locations={})'.format(
            self.__class__.__name__,
            repr(self.name),
            repr(self.type_),
            repr(self.owner),
            self.locations,
        )

    def __str__(self):
        return "{}(name='{}', type={}, owner='{}')".format(
            self.__class__.__name__, self.name.display_name, self.type_, str(self.owner)
        )

    def __jsonEncode__(self):
        return {
            "owner": self.owner,
            "type_": self.type_,
            "name": self.name,
            "locations": tuple(self.locations),
        }

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        # pylint: disable=protected-access
        return cls(
            state.pop("owner"),
            state.pop("type_"),
            state.pop("name"),
            state.pop("locations", None),
        )

    @property
    def owner(self):
        # type: () -> Path
        "Owner of the design unit"
        return self._owner

    @property
    def type_(self):
        # type: () -> DesignUnitType
        "Design unit type"
        return self._type

    @property
    def name(self):
        # type: () -> Identifier
        "Design unit name"
        return self._name

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
        # type: (Path, DesignUnitType, str, Optional[LocationList]) -> None
        super(VhdlDesignUnit, self).__init__(
            owner=owner, type_=type_, name=VhdlIdentifier(name), locations=locations
        )


class VerilogDesignUnit(_DesignUnit):
    """
    Specifies a design unit whose name is case sensitive
    """

    def __init__(self, owner, type_, name, locations=None):
        # type: (Path, DesignUnitType, str, Optional[LocationList]) -> None
        super(VerilogDesignUnit, self).__init__(
            owner=owner, type_=type_, name=VerilogIdentifier(name), locations=locations
        )


tAnyDesignUnit = Union[VhdlDesignUnit, VerilogDesignUnit]
