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
from __future__ import absolute_import

from enum import Enum
from typing import Any, AnyStr, Dict, List, NewType, Optional, Tuple, Union

from hdlcc import parsers
from hdlcc.builders import GHDL, XVHDL, Fallback, MSim

Path = NewType('Path', str)
BuildInfo = Dict[str, Any]
BuildFlags = Tuple[str, ...]
UnitName = str
LibraryName = str
SourceFile = Union[parsers.VhdlParser, parsers.VerilogParser]
ObjectState = Dict
DesignUnit = Dict[str, str]
AnyValidBuilder = Union[MSim, XVHDL, GHDL, ]
AnyBuilder = Union[AnyValidBuilder, Fallback]

class BuilderName(Enum):
    @staticmethod
    def fromString(name):
        """
        Returns the enum type from a string. The conversion is case
        insensitive
        """
        name = str(name).lower()
        return getattr(BuilderName, str(name).lower())

    msim = MSim.builder_name
    xvhdl = XVHDL.builder_name
    ghdl = GHDL.builder_name
    fallback = Fallback.builder_name

class FileType(Enum):
    vhd = ('vhd', 'vhdl')
    verilog = ('v', 'vh')
    systemverilog = ('sv', 'svh')
