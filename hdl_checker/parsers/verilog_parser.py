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
from typing import Any, Generator, Iterable

from .elements.dependency_spec import (
    BaseDependencySpec,
    IncludedPath,
    RequiredDesignUnit,
)
from .elements.design_unit import VerilogDesignUnit
from .elements.parsed_element import Location

from hdl_checker.parsers.base_parser import BaseSourceFile
from hdl_checker.parsers.elements.identifier import VerilogIdentifier
from hdl_checker.types import DesignUnitType, FileType
from hdl_checker.utils import readFile

_logger = logging.getLogger(__name__)

_VERILOG_IDENTIFIER = r"[a-zA-Z_][a-zA-Z0-9_$]+"
_COMMENT = r"(?:\/\*.*?\*\/|//[^(?:\r\n?|\n)]*)"


# Design unit scanner
_DESIGN_UNITS = re.compile(
    "|".join(
        [
            r"(?<=\bmodule\b)\s*(?P<module_name>%s)" % _VERILOG_IDENTIFIER,
            r"(?<=\bpackage\b)\s*(?P<package_name>%s)" % _VERILOG_IDENTIFIER,
            _COMMENT,
        ]
    ),
    flags=re.DOTALL,
)

_DEPENDENCIES = re.compile(
    "|".join(
        [
            r"(?P<package>\b{0})\s*::\s*(?:{0}|\*)".format(_VERILOG_IDENTIFIER),
            r"\bvirtual\s+class\s+(?P<class>\b{0})".format(
                _VERILOG_IDENTIFIER
            ),
            r"(?<=`include\b)\s*\"(?P<include>.*?)\"",
            _COMMENT,
        ]
    ),
    flags=re.DOTALL,
)


class VerilogParser(BaseSourceFile):
    """
    Parses and stores information about a Verilog or SystemVerilog
    source file
    """

    def _getSourceContent(self):
        # type: (...) -> Any
        # Remove multiline comments
        content = readFile(str(self.filename))
        return content
        #  lines = _COMMENT.sub("", content)
        #  return re.sub(r"\r\n?|\n", " ", lines, flags=re.S)

    def _iterDesignUnitMatches(self):
        # type: (...) -> Any
        """
        Iterates over the matches of _DESIGN_UNITS against
        source's lines
        """
        content = self.getSourceContent()
        lines = content.split("\n")
        for match in _DESIGN_UNITS.finditer(self.getSourceContent()):
            start = match.start()
            start_line = content[:start].count("\n")

            total_chars_to_line_with_match = len("\n".join(lines[:start_line]))
            start_char = match.start() - total_chars_to_line_with_match

            yield match.groupdict(), {Location(start_line, start_char)}

    def _getDependencies(self):  # type: () -> Iterable[BaseDependencySpec]
        text = self.getSourceContent()

        for match in _DEPENDENCIES.finditer(text):
            include_name = match.groupdict().get("include", None)

            # package 'std' seems to be built-in. Need to have a look a this
            if include_name is not None:
                line_number = text[: match.end()].count("\n")
                column_number = len(text[: match.start()].split("\n")[-1])

                yield IncludedPath(
                    owner=self.filename,
                    name=VerilogIdentifier(include_name),
                    locations=(Location(line_number, column_number),),
                )

            # Only SystemVerilog has imports
            if self.filetype is FileType.verilog:
                continue

            name = match.groupdict().get("package", None)

            # package 'std' seems to be built-in. Need to have a look a this
            #  if include_name is not None and include_name != 'std':
            if name not in (None, "std"):
                line_number = text[: match.end()].count("\n")
                column_number = len(text[: match.start()].split("\n")[-1])

                yield RequiredDesignUnit(
                    owner=self.filename,
                    name=VerilogIdentifier(name),  # type: ignore
                    locations=(Location(line_number, column_number),),
                )

            name = match.groupdict().get("class", None)

            if name is not None:
                line_number = text[: match.end()].count("\n")
                column_number = len(text[: match.start()].split("\n")[-1])

                yield RequiredDesignUnit(
                    owner=self.filename,
                    name=VerilogIdentifier(name),
                    locations=(Location(line_number, column_number),),
                )

    def _getDesignUnits(self):  # type: () -> Generator[VerilogDesignUnit, None, None]
        for match, locations in self._iterDesignUnitMatches():
            if match["module_name"] is not None:
                yield VerilogDesignUnit(
                    owner=self.filename,
                    name=match["module_name"],
                    type_=DesignUnitType.entity,
                    locations=locations,
                )
            if match["package_name"] is not None:
                yield VerilogDesignUnit(
                    owner=self.filename,
                    name=match["package_name"],
                    type_=DesignUnitType.package,
                    locations=locations,
                )
