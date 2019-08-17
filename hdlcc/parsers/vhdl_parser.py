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
"VHDL source file parser"

import logging
import re
from typing import Generator, Dict, Union, Set

from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.design_unit import DesignUnit, DesignUnitType
from hdlcc.parsers import DependencySpec
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
    r"^\s*\blibrary\s+(?P<library_name>[a-z]\w*)\s*;", flags=re.M | re.I)

_ADDITIONAL_DEPS_SCANNER = re.compile(
    r"\bpackage\s+body\s+(?P<package_body_name>\w+)\s+is\b", flags=re.M)


class VhdlParser(BaseSourceFile):
    """
    Parses and stores information about a source file such as design
    units it depends on and design units it provides
    """

    _comment = re.compile(r"--[^\n\r]*", flags=re.S)

    def _getSourceContent(self):
        """
        Replace everything from comment ('--') until a line break and
        converts to lowercase
        """
        content = open(self.filename, mode='rb').read().decode(errors='ignore')
        return self._comment.sub('', content).lower()

    def _iterDesignUnitMatches(self):
        """
        Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines
        """
        content = self.getSourceContent()
        for match in _DESIGN_UNIT_SCANNER.finditer(content):
            start = match.start()
            yield match.groupdict(), content[:start].count('\n')

    def _getDependencies(self): # type: () -> Generator[DependencySpec, None, None]
        libs = self.getLibraries() + ['work']
        lib_deps_regex = re.compile(r'|'.join([ \
                r"%s\.\w+" % x for x in libs]), flags=re.I)

        dependencies = {} # type: Dict[int, Dict[str, Union[str, Set]]]

        text = self.getSourceContent()
        for match in lib_deps_regex.finditer(text):
            library, unit = match.group().split('.')[:2]

            if library == 'work':
                library = self.library

            key = hash((library, unit))

            if key not in dependencies:
                dependencies[key] = {'library': library,
                                     'name': unit,
                                     'locations': set()}

            dependency = dependencies[key]

            line_number = text[:match.end()].count('\n')
            column_number = len(text[:match.start()].split('\n')[-1])

            dependency['locations'].add((self.filename, line_number + 1, column_number + 1))

        for match in _ADDITIONAL_DEPS_SCANNER.finditer(self.getSourceContent()):
            package_body_name = match.groupdict()['package_body_name']
            key = hash((self.library, package_body_name))

            if key not in dependencies:
                dependencies[key] = {'library': library,
                                     'name': unit,
                                     'locations': set()}

            dependency = dependencies[key]
            line_number = text[:match.end()].count('\n')
            column_number = len(text[:match.start()].split('\n')[-1])
            dependency['locations'].add((self.filename, line_number + 1, column_number + 1))


        # Done parsing, won't add any more locations, so generate the specs
        for dep in dependencies.values():
            yield DependencySpec(path=self.filename,
                                 name=dep['name'],
                                 library=dep['library'],
                                 locations=set(dep['locations']))

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

    def _getDesignUnits(self): # type: () -> Generator[DesignUnit, None, None]
        """
        Parses the source file to find design units and dependencies
        """
        for match, line_number in self._iterDesignUnitMatches():
            if match['package_name'] is not None:
                yield DesignUnit(path=self.filename,
                                 name=match['package_name'],
                                 type_=DesignUnitType.package,
                                 locations=((self.filename, line_number, None),))

            elif match['entity_name'] is not None:
                yield DesignUnit(path=self.filename,
                                 name=match['entity_name'],
                                 type_=DesignUnitType.entity,
                                 locations=((self.filename, line_number, None),))
            elif match['context_name'] is not None:
                yield DesignUnit(path=self.filename,
                                 name=match['context'],
                                 type_=DesignUnitType.context,
                                 locations=((self.filename, line_number, None),))
