# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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
"VHDL source file parser"

import re
import logging
from hdlcc.parsers.base_parser import BaseSourceFile

_logger = logging.getLogger(__name__)

_VERILOG_IDENTIFIER = r"[a-zA-Z_][a-zA-Z0-9_$]+"
# Design unit scanner
_DESIGN_UNIT_SCANNER = re.compile('|'.join([
    r"\bmodule\s+(?P<module_name>%s)" % _VERILOG_IDENTIFIER,
    ]),)

class VerilogParser(BaseSourceFile):
    """Parses and stores information about a source file such as
    design units it depends on and design units it provides"""

    def _getSourceContent(self):
        """Replace everything from comment ('--') until a line break
        and converts to lowercase"""
        # Remove block comments before splitting
        lines = re.sub(r'/\*.*\*/|//[^(\r\n?|\n)]*', '',
                       open(self.filename, 'r').read(), flags=re.S)
        return [re.sub(r'\r\n?|\n', ' ', lines, flags=re.S)]

    def _iterDesignUnitMatches(self):
        """Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines"""
        for line in self._getSourceContent():
            for match in _DESIGN_UNIT_SCANNER.finditer(line):
                yield match.groupdict()

    def _getDependencies(self):
        """Parses the source and returns a list of dictionaries that
        describe its dependencies"""
        return []

    def _getDesignUnits(self):
        "Parses the source file to find design units and dependencies"
        design_units = []

        for match in self._iterDesignUnitMatches():
            if match['module_name'] not in design_units:
                design_units += [{
                    'name' : match['module_name'],
                    'type' : 'entity'}]

        return design_units

    def _doParse(self):
        """Finds design units and dependencies then translate some design
        units into information useful in the conext of the project"""

        self._design_units = self._getDesignUnits()

    def _getLibraries(self):
        return []



