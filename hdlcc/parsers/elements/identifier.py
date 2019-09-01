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
"VHDL, Verilog or SystemVerilog identifier and comparisons between them"

# pylint: disable=useless-object-inheritance


class Identifier(object):
    """
    VHDL, Verilog or SystemVerilog identifier to make it easier to handle case
    and comparisons between them
    """

    def __init__(self, name, case_sensitive):
        # type: (str, bool) -> None
        self._name = str(name) if case_sensitive else str(name).lower()
        self._display_name = str(name)

    @property
    def name(self):
        "Normalized identifier name"
        return self._name

    @property
    def display_name(self):
        "Identifier name as given when creating the object"
        return self._display_name

    def __hash__(self):
        return hash(self.name)

    def __repr__(self):
        return "{}(name={}, display_name={})".format(
            self.__class__.__name__, repr(self.name), repr(self.display_name)
        )

    def __eq__(self, other):
        """Overrides the default implementation"""

        if isinstance(other, self.__class__):
            return self.name == other.name

        return NotImplemented  # pragma: no cover

    def __ne__(self, other):  # pragma: no cover
        """Overrides the default implementation (unnecessary in Python 3)"""
        result = self.__eq__(other)

        if result is not NotImplemented:
            return not result

        return NotImplemented
