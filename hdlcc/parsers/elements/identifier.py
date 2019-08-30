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

from hdlcc.utils import HashableByKey


class Identifier(HashableByKey):
    """
    VHDL, Verilog or SystemVerilog identifier to make it easier to handle case
    and comparisons between them
    """

    def __init__(self, name, case_sensitive):
        # type: (str, bool) -> None
        self._name = name
        self._case_sensitive = case_sensitive

    @property
    def name(self):
        "Identifier name as given when creating the object"
        return self._name

    @property
    def case_sensitive(self):
        "Defines if case should be used when comparing identifiers"
        return self._case_sensitive

    def __hash_key__(self):
        return self.name, self.case_sensitive

    def __repr__(self):
        return "{}({}, {})".format(
            self.__class__.__name__,
            self.name,
            "case" if self.case_sensitive else "nocase",
        )

    def __eq__(self, other):
        """Overrides the default implementation"""

        if isinstance(other, self.__class__):
            our_name = self.name if self.case_sensitive else self.name.lower()
            other_name = other.name if other.case_sensitive else other.name.lower()

            return str(our_name) == str(other_name)

        return NotImplemented  # pragma: no cover

    def __ne__(self, other):  # pragma: no cover
        """Overrides the default implementation (unnecessary in Python 3)"""
        result = self.__eq__(other)

        if result is not NotImplemented:
            return not result

        return NotImplemented
