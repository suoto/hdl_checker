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
    r"\bpackage\s+(?P<package_name>\w+)\s+is\b",
    r"\bentity\s+(?P<entity_name>\w+)\s+is\b",
    r"\blibrary\s+(?P<library_name>[\w,\s]+)\b",
    r"\bcontext\s+(?P<context_name>\w+)\s+is\b",
    ]), flags=re.M)

_LIBRARY_SCANNER = re.compile(
    r"\blibrary\s+(?P<library_name>[^;]+)", flags=re.M)

_ADDITIONAL_DEPS_SCANNER = re.compile('|'.join([
    r"\bpackage\s+body\s+(?P<package_body_name>\w+)\s+is\b",
    r"\bcomponent\s+(?P<component_name>\w+)\s+(generic|port|is)\b"]), flags=re.M)

_SUB_COMMENTS = re.compile(r"--[^\n\r]*", flags=re.S).sub

class VhdlParser(BaseSourceFile):
    """
    Parses and stores information about a source file such as design
    units it depends on and design units it provides
    """

    def _getSourceContent(self):
        """
        Replace everything from comment ('--') until a line break and
        converts to lowercase
        """
        content = open(self.filename, mode='rb').read().decode(errors='ignore')
        return _SUB_COMMENTS('', content).lower()

    def _iterDesignUnitMatches(self):
        """
        Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines
        """
        for match in _DESIGN_UNIT_SCANNER.finditer(self.getSourceContent()):
            yield match.groupdict()

    def _getDependencies(self):
        libs = self.getLibraries() + ['work']
        lib_deps_regex = re.compile(r'|'.join([ \
                r"%s\.\w+" % x for x in libs]), flags=re.I)

        dependencies = []
        for match in lib_deps_regex.finditer(self.getSourceContent()):
            dependency = {}
            dependency['library'], dependency['unit'] = match.group().split('.')[:2]
            # Library 'work' means 'this' library, so we replace it
            # by the library name itself
            if dependency['library'] == 'work':
                dependency['library'] = self.library
            if dependency not in dependencies:
                dependencies.append(dependency)

        for match in _ADDITIONAL_DEPS_SCANNER.finditer(self.getSourceContent()):
            _dict = match.groupdict()
            package_body_name = _dict['package_body_name']
            if package_body_name is not None:
                dependencies.append(
                    {'library' : self.library,
                     'unit': package_body_name})

        return dependencies

    def _getLibraries(self):
        """
        Parses the source file to find design units and dependencies
        """
        libs = ['work']

        for match in _LIBRARY_SCANNER.finditer(self.getSourceContent()):
            match = match.groupdict()
            if match['library_name'] is not None:
                for lib in re.split(r"\s*,\s*", match['library_name']):
                    libs.append(lib.strip())

        libs.remove('work')
        libs.append(self.library)
        return libs

    def _getDesignUnits(self):
        """
        Parses the source file to find design units and dependencies
        """
        design_units = []

        for match in self._iterDesignUnitMatches():
            unit = None
            if match['package_name'] is not None:
                unit = {'name' : match['package_name'],
                        'type' : 'package'}
            elif match['entity_name'] is not None:
                unit = {'name' : match['entity_name'],
                        'type' : 'entity'}
            elif match['context_name'] is not None:
                unit = {'name' : match['context_name'],
                        'type' : 'context'}

            if unit:
                design_units.append(unit)

        return design_units

