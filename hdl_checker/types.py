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
"Common type definitions for type hinting"
from collections import namedtuple
from enum import Enum
from typing import NamedTuple, Optional, Tuple, Union

from hdl_checker.exceptions import UnknownTypeExtension
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path


class DesignUnitType(str, Enum):
    "Specifies tracked design unit types"
    package = "package"
    entity = "entity"
    context = "context"


BuildFlags = Tuple[str, ...]
LibraryAndUnit = namedtuple("LibraryAndUnit", ["library", "unit"])

RebuildUnit = NamedTuple(
    "RebuildUnit", (("name", Identifier), ("type_", DesignUnitType))
)
RebuildLibraryUnit = NamedTuple(
    "RebuildLibraryUnit", (("name", Identifier), ("library", Identifier))
)
RebuildPath = NamedTuple("RebuildPath", (("path", Path),))

RebuildInfo = Union[RebuildUnit, RebuildLibraryUnit, RebuildPath]


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


class BuildFlagScope(Enum):
    """
    Scopes of a given set of flags. Values of the items control the actual
    fields extracted from the JSON config
    """

    source_specific = "source_specific"
    single = "single"
    dependencies = "dependencies"
    all = "global"


class MarkupKind(Enum):
    "LSP Markup kinds"
    PlainText = "plaintext"
    Markdown = "markdown"


# A location on a source file
Location = NamedTuple("Location", (("line", Optional[int]), ("column", Optional[int])))

# A location range within a source file
Range = NamedTuple("Range", (("start", Location), ("end", Optional[Location])))


class ConfigFileOrigin(str, Enum):
    "Specifies tracked design unit types"
    user = "user"
    generated = "generated"
