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
"Base class for creating a project file"

import abc
import logging
from typing import Dict, Optional, Set, Tuple

from hdl_checker.builder_utils import AnyValidBuilder
from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, FileType

_SOURCE_EXTENSIONS = "vhdl", "sv", "v"
_HEADER_EXTENSIONS = "vh", "svh"

_DEFAULT_LIBRARY_NAME = {"vhdl": "lib", "verilog": "lib", "systemverilog": "lib"}

SourceSpec = Tuple[Path, BuildFlags, Optional[str]]


class BaseGenerator:
    """
    Base class implementing creation of config file semi automatically
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self):  # type: () -> None
        """
        """
        self._logger = logging.getLogger(self.__class__.__name__)
        self._sources = set()  # type: Set[SourceSpec]
        self._include_paths = {
            FileType.verilog: set(),
            FileType.systemverilog: set(),
        }  # type: Dict[FileType, Set[str]]

    def _addSource(self, path, flags=None, library=None):
        # type: (Path, BuildFlags, Optional[str]) -> None
        """
        Add a source to project. 'flags' and 'library' are only used for
        regular sources and not for header files (files ending in .vh or .svh)
        """
        self._logger.debug(
            "Adding path %s (flags=%s, library=%s)", path, flags, library
        )

        if path.basename.split(".")[-1].lower() in ("vh", "svh"):
            file_type = FileType.fromPath(path)
            if file_type in (FileType.verilog, FileType.systemverilog):
                self._include_paths[file_type].add(path.dirname)
        else:
            self._sources.add((path, flags or (), library))

    @abc.abstractmethod
    def _populate(self):  # type: () -> None
        """
        Method that will be called for generating the project file contets and
        should be implemented by child classes
        """

    def _getPreferredBuilder(self):  # type: () -> AnyValidBuilder
        """
        Method should be overridden by child classes to express the preferred
        builder
        """
        return NotImplemented

    def generate(self):
        """
        Runs the child class algorithm to populate the parent object with the
        project info and writes the result to the project file
        """

        self._populate()

        project = {"sources": []}

        builder = self._getPreferredBuilder()
        if builder is not NotImplemented:
            project["builder"] = builder

        # Add include paths if they exists. Need to iterate sorted keys to
        # generate results always in the same order
        for lang in (FileType.verilog, FileType.systemverilog):
            paths = self._include_paths[lang]
            if paths:
                if lang.value not in project:
                    project[lang.value] = {}
                project[lang.value]["include_paths"] = tuple(paths)

        for path, flags, library in self._sources:
            info = {}
            if library:
                info["library"] = library
            if flags:
                info["flags"] = flags

            if info:
                project["sources"].append(
                    (str(path), {"library": library, "flags": tuple(flags)})
                )
            else:
                project["sources"].append(str(path))

        from pprint import pformat

        self._logger.info("Resulting project:\n%s", pformat(project))

        return project
