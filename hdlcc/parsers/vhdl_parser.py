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

# Design unit scanner
_DESIGN_UNIT_SCANNER = re.compile('|'.join([
    r"^\s*package\s+(?P<package_name>\w+)\s+is\b",
    r"^\s*package\s+body\s+(?P<package_body_name>\w+)\s+is\b",
    r"^\s*entity\s+(?P<entity_name>\w+)\s+is\b",
    r"^\s*library\s+(?P<library_name>[\w,\s]+)\b",
    r"^\s*context\s+(?P<context_name>\w+)\s+is\b",
    ]), flags=re.I)

class VhdlParser(BaseSourceFile):
    """Parses and stores information about a source file such as
    design units it depends on and design units it provides"""

    def _getSourceContent(self):
        """Replace everything from comment ('--') until a line break
        and converts to lowercase"""
        lines = list([re.sub(r"\s*--.*", "", x).lower() for x in \
                open(self.filename, 'r').read().split("\n")])
        return lines

    def _iterDesignUnitMatches(self):
        """Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines"""
        for line in self._getSourceContent():
            for match in _DESIGN_UNIT_SCANNER.finditer(line):
                yield match.groupdict()

    def _getDependencies(self, libraries):
        """Parses the source and returns a list of dictionaries that
        describe its dependencies"""
        lib_deps_regex = re.compile(r'|'.join([ \
                r"%s\.\w+" % x for x in libraries]), flags=re.I)
        dependencies = []
        for line in self._getSourceContent():
            for match in lib_deps_regex.finditer(line):
                dependency = {}
                dependency['library'], dependency['unit'] = match.group().split('.')[:2]
                # Library 'work' means 'this' library, so we replace it
                # by the library name itself
                if dependency['library'] == 'work':
                    dependency['library'] = self.library
                if dependency not in dependencies:
                    dependencies.append(dependency)

        return dependencies

    def _getParsedData(self):
        "Parses the source file to find design units and dependencies"
        design_units = []
        libraries = ['work']

        for match in self._iterDesignUnitMatches():
            unit = None
            if match['package_name'] is not None:
                unit = {'name' : match['package_name'],
                        'type' : 'package'}
            elif match['package_body_name'] is not None:
                unit = {'name' : match['package_body_name'],
                        'type' : 'package body'}
            elif match['entity_name'] is not None:
                unit = {'name' : match['entity_name'],
                        'type' : 'entity'}
            elif match['context_name'] is not None:
                unit = {'name' : match['context_name'],
                        'type' : 'context'}
            if match['library_name'] is not None:
                libraries += re.split(r"\s*,\s*", match['library_name'])

            if unit:
                design_units.append(unit)

        return design_units, self._getDependencies(libraries)

    def _doParse(self):
        """Finds design units and dependencies then translate some design
        units into information useful in the conext of the project"""
        design_units, dependencies = self._getParsedData()

        self._design_units = []
        for design_unit in design_units:
            if design_unit['type'] == 'package body':
                dependencies += [{'library' : self.library, 'unit': design_unit['name']}]
            else:
                self._design_units += [design_unit]

        self._deps = dependencies

