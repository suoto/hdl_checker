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

import re
from typing import Any, Dict, Generator, Iterable, Optional, Set, Tuple, Union

from .elements.dependency_spec import RequiredDesignUnit
from .elements.design_unit import VhdlDesignUnit
from .elements.identifier import VhdlIdentifier
from .elements.parsed_element import Location

from hdl_checker.parsers.base_parser import BaseSourceFile
from hdl_checker.types import DesignUnitType

# Design unit scanner
_DESIGN_UNITS = re.compile(
    "|".join(
        [
            r"(?<=\bpackage\b)\s+(?P<package_name>\w+)(?=\s+is\b)",
            r"(?<=\bentity\b)\s+(?P<entity_name>\w+)(?=\s+is\b)",
            r"(?<=\blibrary)\s+(?P<library_name>[\w,\s]+)\b",
            r"(?<=\bcontext\b)\s+(?P<context_name>\w+)(?=\s+is\b)",
            r"(?P<comment>\s*--.*)",
        ]
    ),
    flags=re.MULTILINE | re.IGNORECASE,
)

_LIBRARIES = re.compile(
    r"(?:\blibrary\s+(?P<name>[a-z]\w*(?:\s*,\s*[a-z]\w*){0,})\s*;)|(?:\s*--.*)",
    flags=re.MULTILINE | re.IGNORECASE,
)

_PACKAGE_BODY = re.compile(
    r"\bpackage\s+body\s+(?P<package_body_name>\w+)\s+is\b"
    r"|"
    r"(?P<comment>\s*--.*)",
    flags=re.MULTILINE | re.IGNORECASE,
)

_LIBRARY_USES = re.compile(
    r"(?:(?P<library>\b\w+)\s*\.\s*(?P<unit>\b\w+\w+))|(?:\s*--.*)", flags=re.I
)
IncompleteDependency = Dict[str, Union[str, Set[Any]]]


class _PartialDependency(object):  # pylint: disable=useless-object-inheritance
    """
    Stores dependencies definitions to create immutable objects later on
    """

    def __init__(self):
        #  type: (...) -> None
        self._keys = set()  # type: Set[int]
        self._libraries = {}  # type: Dict[int, Optional[VhdlIdentifier]]
        self._units = {}  # type: Dict[int, VhdlIdentifier]
        self._locations = {}  # type: Dict[int, Set[Location]]

    def add(self, library, unit, line, column):
        #  type: (str, str, int, int) -> None
        """
        Adds a dependency definition to the list
        """
        _library = None if library.lower() == "work" else VhdlIdentifier(library)
        _unit = VhdlIdentifier(unit)

        key = hash((_library, _unit))
        if key not in self._keys:
            self._keys.add(key)
            self._libraries[key] = _library
            self._units[key] = _unit
            self._locations[key] = set()

        self._locations[key].add(Location(line, column))

    def items(self):
        #  type: () -> Iterable[Tuple[Optional[VhdlIdentifier], VhdlIdentifier, Set[Location]]]
        """
        Returns items added previously
        """
        for key in self._keys:
            yield self._libraries[key], self._units[key], self._locations[key]


class VhdlParser(BaseSourceFile):
    """
    Parses and stores information about a source file such as design
    units it depends on and design units it provides
    """

    def _iterDesignUnitMatches(self):
        # type: (...) -> Any
        """
        Iterates over the matches of _DESIGN_UNITS against
        source's lines
        """
        content = self.getSourceContent()
        lines = content.split("\n")

        for match in _DESIGN_UNITS.finditer(content):
            start = match.start()
            start_line = content[:start].count("\n")

            total_chars_to_line_with_match = len("\n".join(lines[:start_line]))
            start_char = match.start() - total_chars_to_line_with_match

            yield match.groupdict(), {Location(start_line, start_char)}

    def _getDependencies(self):  # type: () -> Generator[RequiredDesignUnit, None, None]
        library_names = {x.lower() for x in self.getLibraries()}
        library_names.add("work")

        dependencies = _PartialDependency()

        text = self.getSourceContent()

        for match in _LIBRARY_USES.finditer(text):
            if match.groupdict()["library"] is None:
                continue

            # Strip extra whitespaces and line breaks here instead of inside
            # the regex to allow using a single finditer call
            library = match.groupdict()["library"]

            if library.lower() not in library_names:
                continue

            unit = match.groupdict()["unit"]

            line_number = text[: match.end()].count("\n")
            column_number = len(text[: match.start()].split("\n")[-1])

            dependencies.add(library, unit, line_number, column_number)

        # Done parsing, won't add any more locations, so generate the specs
        for _library, name, locations in dependencies.items():
            # Remove references to 'work' (will treat library=None as work,
            # which also means not set in case of packages)
            yield RequiredDesignUnit(
                owner=self.filename, name=name, library=_library, locations=locations
            )

        # Package bodies need a package declaration; include those as
        # dependencies as well
        for match in _PACKAGE_BODY.finditer(self.getSourceContent()):
            package_body_name = match.groupdict()["package_body_name"]
            if package_body_name is None:
                continue
            line_number = int(text[: match.end()].count("\n"))
            column_number = len(text[: match.start()].split("\n")[-1])

            yield RequiredDesignUnit(
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

        for match in _LIBRARIES.finditer(self.getSourceContent()):
            for group in match.groups():
                if group is not None:
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
