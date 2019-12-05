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
"Spec for a parsed dependency"

from typing import Optional

from .identifier import Identifier
from .parsed_element import LocationList, ParsedElement  # pylint: disable=unused-import

from hdl_checker.path import Path  # pylint: disable=unused-import


class BaseDependencySpec(ParsedElement):
    "Placeholder for a source dependency"

    def __init__(self, owner, name, library=None, locations=None):
        # type: (Path, Identifier, Optional[Identifier], Optional[LocationList]) -> None
        assert isinstance(name, Identifier), "Incorrect arg: {}".format(name)
        assert library is None or isinstance(
            library, Identifier
        ), "Incorrect arg: {}".format(library)

        self._owner = owner
        self._library = library
        self._name = name
        super(BaseDependencySpec, self).__init__(locations)

    @property
    def owner(self):
        # type: (...) -> Path
        """
        Path of the file that the dependency was found in
        """
        return self._owner

    @property
    def name(self):
        # type: (...) -> Identifier
        """
        Name of the design unit this dependency refers to
        """
        return self._name

    @property
    def library(self):
        # type: (...) -> Optional[Identifier]
        """
        Library, if any, this dependency was found. If None, should be
        equivalent to the library of the owner (aka 'work' library)
        """
        return self._library

    def __len__(self):
        if self.library is None:
            return len(self.name)
        return len(self.name) + len(self.library) + 1

    @property
    def __hash_key__(self):
        return (
            self.owner,
            self.library,
            self.name,
            super(BaseDependencySpec, self).__hash_key__,
        )

    def __jsonEncode__(self):
        return {
            "owner": self.owner,
            "name": self.name,
            "library": self.library,
            "locations": tuple(self.locations),
        }

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        return cls(
            library=state.pop("library"),
            name=state.pop("name"),
            owner=state.pop("owner"),
            locations=state.pop("locations"),
        )

    def __repr__(self):
        return "{}(name={}, library={}, owner={}, locations={})".format(
            self.__class__.__name__,
            repr(self.name),
            repr(self.library),
            repr(self.owner),
            repr(self.locations),
        )


class RequiredDesignUnit(BaseDependencySpec):
    pass


class IncludedPath(BaseDependencySpec):
    """
    Special type of dependency for Verilog and SystemVerilog files. Its name is
    actually the string that the source is including.
    """

    def __init__(self, owner, name, locations=None):
        # type: (Path, Identifier, Optional[LocationList]) -> None
        super(IncludedPath, self).__init__(
            owner=owner, name=name, library=None, locations=locations
        )

    def __jsonEncode__(self):
        return {
            "owner": self.owner,
            "name": self.name,
            "locations": tuple(self.locations),
        }

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        return cls(
            name=state.pop("name"),
            owner=state.pop("owner"),
            locations=state.pop("locations"),
        )
