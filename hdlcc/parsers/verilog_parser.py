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
    r"\bpackage\s+(?P<package_name>%s)" % _VERILOG_IDENTIFIER,
    ]), flags=re.S)

class VerilogParser(BaseSourceFile):
    """
    Parses and stores information about a Verilog or SystemVerilog
    source file
    """

    _comment = re.compile(r'/\*.*\*/|//[^(\r\n?|\n)]*', flags=re.S)

    def _getSourceContent(self):
        # Remove multiline comments
        content = open(self.filename, mode='rb').read().decode(errors='ignore')
        lines = self._comment.sub('', content)
        return re.sub(r'\r\n?|\n', ' ', lines, flags=re.S)

    def _iterDesignUnitMatches(self):
        """
        Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines
        """
        for match in _DESIGN_UNIT_SCANNER.finditer(self.getSourceContent()):
            yield match.groupdict()

    def _getDependencies(self):
        return []

    def _getDesignUnits(self):
        design_units = []

        for match in self._iterDesignUnitMatches():
            if match.get('module_name', None):
                design_units += [{
                    'name' : match['module_name'],
                    'type' : 'entity'}]
            elif match.get('package_name', None):
                design_units += [{
                    'name' : match['package_name'],
                    'type' : 'package'}]
            else:  # pragma: no cover
                assert False

        return design_units

    def _getLibraries(self):
        return []

