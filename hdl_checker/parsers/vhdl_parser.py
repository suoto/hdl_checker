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
from typing import Any, Dict, Generator, Optional, Set, Tuple, Union

from .elements.dependency_spec import DependencySpec
from .elements.design_unit import VhdlDesignUnit
from .elements.identifier import VhdlIdentifier
from .elements.parsed_element import Location

from hdl_checker.parsers.base_parser import BaseSourceFile
from hdl_checker.types import DesignUnitType
from hdl_checker.utils import readFile

_logger = logging.getLogger(__name__)

# Design unit scanner
_DESIGN_UNIT_SCANNER = re.compile(
    "|".join(
        [
            r"(?<=\bpackage\b)\s+(?P<package_name>\w+)(?=\s+is\b)",
            r"(?<=\bentity\b)\s+(?P<entity_name>\w+)(?=\s+is\b)",
            r"(?<=\blibrary)\s+(?P<library_name>[\w,\s]+)\b",
            r"(?<=\bcontext\b)\s+(?P<context_name>\w+)(?=\s+is\b)",
        ]
    ),
    flags=re.MULTILINE | re.IGNORECASE,
)

_LIBRARY_SCANNER = re.compile(
    r"library\s+([a-z]\w*(?:\s*,\s*[a-z]\w*){0,})\s*;",
    flags=re.MULTILINE | re.IGNORECASE,
)

_ADDITIONAL_DEPS_SCANNER = re.compile(
    r"\bpackage\s+body\s+(?P<package_body_name>\w+)\s+is\b",
    flags=re.MULTILINE | re.IGNORECASE,
)

IncompleteDependency = Dict[str, Union[str, Set[Any]]]


class VhdlParser(BaseSourceFile):
    """
    Parses and stores information about a source file such as design
    units it depends on and design units it provides
    """

    _comment = re.compile(r"--[^\n\r]*", flags=re.S)

    def _getSourceContent(self):
        # type: (...) -> Any
        """
        Replace everything from comment ('--') until a line break
        """
        content = readFile(str(self.filename))

        return self._comment.sub("", content)

    def _iterDesignUnitMatches(self):
        # type: (...) -> Any
        """
        Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines
        """
        content = self.getSourceContent()
        lines = content.split("\n")

        for match in _DESIGN_UNIT_SCANNER.finditer(content):
            start = match.start()
            start_line = content[:start].count("\n")

            total_chars_to_line_with_match = len("\n".join(lines[:start_line]))
            start_char = match.start() - total_chars_to_line_with_match

            yield match.groupdict(), {Location(start_line, start_char)}

    def _getDependencies(self):  # type: () -> Generator[DependencySpec, None, None]
        lib_deps_regex = re.compile(
            r"|".join(
                [r"%s\s*\.\s*\w+" % x for x in set(self.getLibraries() + ["work"])]
            ),
            flags=re.I,
        )

        dependencies = {}  # type: ignore

        text = self.getSourceContent()

        for match in lib_deps_regex.finditer(text):

            # Strip extra whitespaces and line breaks here instead of inside
            # the regex to allow using a single finditer call
            library, unit = [
                x.strip() for x in match.group().split(".")[:2]
            ]  # type: Tuple[Optional[str], str]

            line_number = text[: match.end()].count("\n")
            column_number = len(text[: match.start()].split("\n")[-1])

            key = hash((library, unit))

            if key not in dependencies:
                dependencies[key] = {
                    "library": library,
                    "name": unit,
                    "locations": set(),
                }

            dependency = dependencies[key]
            dependency["locations"].add((line_number, column_number))

        # Done parsing, won't add any more locations, so generate the specs
        for dep in dependencies.values():
            # Remove references to 'work' (will treat library=None as work,
            # which also means not set in case of packages)
            if dep["library"].lower() == "work":
                dep_library = None
            else:
                dep_library = VhdlIdentifier(dep["library"])
            yield DependencySpec(
                owner=self.filename,
                name=VhdlIdentifier(dep["name"]),
                library=dep_library,
                locations=dep["locations"],
            )

        for match in _ADDITIONAL_DEPS_SCANNER.finditer(self.getSourceContent()):
            package_body_name = match.groupdict()["package_body_name"]
            line_number = int(text[: match.end()].count("\n"))
            column_number = len(text[: match.start()].split("\n")[-1])

            yield DependencySpec(
                owner=self.filename,
                name=VhdlIdentifier(package_body_name),
                library=None,
                locations={Location(line_number, column_number)},
            )

    def _getLibraries(self):
        # type: (...) -> Any
        """
        Parses the source file to find design units and dependencies
        """
        libs = set()  # type: Set[str]

        for match in _LIBRARY_SCANNER.finditer(self.getSourceContent()):
            for group in match.groups():
                libs = libs.union(set(map(str.strip, str(group).split(","))))

        # Replace references of 'work' for the actual library name
        if "work" in libs:
            libs = libs - {"work"}

        return libs

    def _getDesignUnits(self):  # type: () -> Generator[VhdlDesignUnit, None, None]
        """
        Parses the source file to find design units and dependencies
        """

        for match, locations in self._iterDesignUnitMatches():

            if match["package_name"] is not None:
                yield VhdlDesignUnit(
                    owner=self.filename,
                    name=match["package_name"],
                    type_=DesignUnitType.package,
                    locations=locations,
                )

            elif match["entity_name"] is not None:
                yield VhdlDesignUnit(
                    owner=self.filename,
                    name=match["entity_name"],
                    type_=DesignUnitType.entity,
                    locations=locations,
                )
            elif match["context_name"] is not None:
                yield VhdlDesignUnit(
                    owner=self.filename,
                    name=match["context_name"],
                    type_=DesignUnitType.context,
                    locations=locations,
                )
