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
from typing import Tuple

from hdlcc.path import Path

BuildFlags = Tuple[str, ...]
LibraryAndUnit = namedtuple("LibraryAndUnit", ["library", "unit"])


class UnknownTypeExtension(Exception):
    """
    Exception thrown when trying to get the file type of an unknown extension.
    Known extensions are one of '.vhd', '.vhdl', '.v', '.vh', '.sv', '.svh'
    """

    def __init__(self, path):
        super(UnknownTypeExtension, self).__init__()
        self._path = path

    def __str__(self):
        return "Couldn't determine file type for path '%s'" % self._path


class FileType(Enum):
    "RTL file types"
    vhdl = "vhdl"
    verilog = "verilog"
    systemverilog = "systemverilog"

    @staticmethod
    def fromPath(path):
        # type: (Path) -> FileType
        "Extracts FileType from the given path's extension"
        ext = path.name.split(".")[-1].lower()
        if ext in ("vhd", "vhdl"):
            return FileType.vhdl
        if ext in ("v", "vh"):
            return FileType.verilog
        if ext in ("sv", "svh"):
            return FileType.systemverilog
        raise UnknownTypeExtension(path)

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        return {"value": self.name}

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""
        return cls(state["value"])
