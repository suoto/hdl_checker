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
"VHDL source file parser"

import logging
import re
from typing import Any, Generator

from .elements.design_unit import VerilogDesignUnit
from .elements.parsed_element import Location

from hdl_checker.parsers.base_parser import BaseSourceFile
from hdl_checker.types import DesignUnitType
from hdl_checker.utils import readFile

_logger = logging.getLogger(__name__)

_VERILOG_IDENTIFIER = r"[a-zA-Z_][a-zA-Z0-9_$]+"
# Design unit scanner
_DESIGN_UNIT_SCANNER = re.compile(
    "|".join(
        [
            r"\bmodule\s+(?P<module_name>%s)" % _VERILOG_IDENTIFIER,
            r"\bpackage\s+(?P<package_name>%s)" % _VERILOG_IDENTIFIER,
        ]
    ),
    flags=re.S,
)


class VerilogParser(BaseSourceFile):
    """
    Parses and stores information about a Verilog or SystemVerilog
    source file
    """

    _comment = re.compile(r"\/\*.*?\*\/|//[^(\r\n?|\n)]*", flags=re.DOTALL)

    def _getSourceContent(self):
        # type: (...) -> Any
        # Remove multiline comments
        content = readFile(str(self.filename))
        lines = self._comment.sub("", content)
        return re.sub(r"\r\n?|\n", " ", lines, flags=re.S)

    def _iterDesignUnitMatches(self):
        # type: (...) -> Any
        """
        Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines
        """
        content = self.getSourceContent()
        for match in _DESIGN_UNIT_SCANNER.finditer(self.getSourceContent()):
            start = match.start()
            yield match.groupdict(), content[:start].count("\n")

    def _getDependencies(self):
        return []

    def _getDesignUnits(self):  # type: () -> Generator[VerilogDesignUnit, None, None]
        for match, line_number in self._iterDesignUnitMatches():
            if match["module_name"] is not None:
                yield VerilogDesignUnit(
                    owner=self.filename,
                    name=match["module_name"],
                    type_=DesignUnitType.entity,
                    locations={Location(line_number, None)},
                )
            if match["package_name"] is not None:
                yield VerilogDesignUnit(
                    owner=self.filename,
                    name=match["package_name"],
                    type_=DesignUnitType.package,
                    locations={Location(line_number, None)},
                )

    def _getLibraries(self):
        return set()
