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
"Common type definitions for type hinting"
from collections import namedtuple
from enum import Enum
from typing import Any, Dict, Tuple

BuildInfo = Dict[str, Any]
BuildFlags = Tuple[str, ...]
UnitName = str
LibraryName = str
ObjectState = Dict

LibraryAndUnit = namedtuple("LibraryAndUnit", ["library", "unit"])


class FileType(Enum):
    vhdl = ("vhd", "vhdl")
    verilog = ("v", "vh")
    systemverilog = ("sv", "svh")

    def toString(self):
        return str(self.name)

    #  @classmethod
    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        return {"value": self.name}

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        name = state["value"]
        if name == "vhd":
            return FileType.vhdl
        if name == "verilog":
            return FileType.verilog
        return FileType.systemverilog
