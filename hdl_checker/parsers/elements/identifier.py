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
"VHDL, Verilog or SystemVerilog identifier and comparisons between them"

# pylint: disable=useless-object-inheritance


class Identifier(object):
    """
    VHDL, Verilog or SystemVerilog identifier to make it easier to handle case
    and comparisons between them
    """

    def __init__(self, name, case_sensitive=False):
        # type: (str, bool) -> None
        self.case_sensitive = case_sensitive
        self._display_name = str(name)
        self._name = self._display_name.lower()

    @property
    def name(self):
        "Normalized identifier name"
        return self._name

    @property
    def display_name(self):
        "Identifier name as given when creating the object"
        return self._display_name

    def __jsonEncode__(self):
        return {"name": self.display_name, "case_sensitive": self.case_sensitive}

    @classmethod
    def __jsonDecode__(cls, state):
        return cls(name=state.pop("name"), case_sensitive=state.pop("case_sensitive"))

    def __hash__(self):
        return hash(self.name)

    def __str__(self):
        return self.display_name

    def __len__(self):
        return len(self.display_name)

    def __repr__(self):
        if self.name == self.display_name:
            return "{}({})".format(self.__class__.__name__, repr(self.name))
        return "{}({}, display_name={})".format(
            self.__class__.__name__, repr(self.name), repr(self.display_name)
        )

    def __eq__(self, other):
        """Overrides the default implementation"""

        try:
            if self.case_sensitive and other.case_sensitive:
                return self.display_name == other.display_name
            return self.name == other.name
        except AttributeError:
            pass

        return NotImplemented  # pragma: no cover

    def __ne__(self, other):  # pragma: no cover
        """Overrides the default implementation (unnecessary in Python 3)"""
        result = self.__eq__(other)

        if result is not NotImplemented:
            return not result

        return NotImplemented


class VhdlIdentifier(Identifier):
    "Equivalent of Identifier(name, case_sensitive=False)"

    def __init__(self, name):
        # type: (str, ) -> None
        super(VhdlIdentifier, self).__init__(name=name, case_sensitive=False)

    @classmethod
    def __jsonDecode__(cls, state):
        return cls(name=state.pop("name"))


class VerilogIdentifier(Identifier):
    "Equivalent of Identifier(name, case_sensitive=True)"

    def __init__(self, name):
        # type: (str, ) -> None
        super(VerilogIdentifier, self).__init__(name=name, case_sensitive=True)

    @classmethod
    def __jsonDecode__(cls, state):
        return cls(name=state.pop("name"))
