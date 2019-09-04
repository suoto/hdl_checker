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
"Base class for creating a project file"

import abc
import logging
from typing import Dict, Optional, Set, Tuple

from hdlcc import types as t
from hdlcc.builders import AnyValidBuilder
from hdlcc.path import Path
from hdlcc.utils import getFileType

_SOURCE_EXTENSIONS = "vhdl", "sv", "v"
_HEADER_EXTENSIONS = "vh", "svh"

_DEFAULT_LIBRARY_NAME = {"vhdl": "lib", "verilog": "lib", "systemverilog": "lib"}

Flags = str
SourceSpec = Tuple[Path, Flags, t.LibraryName]


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
            t.FileType.verilog: set(),
            t.FileType.systemverilog: set(),
        }  # type: Dict[t.FileType, Set[str]]

    def _addSource(self, path, flags=None, library=None):
        # type: (Path, Optional[Flags], Optional[str]) -> None
        """
        Add a source to project. 'flags' and 'library' are only used for
        regular sources and not for header files (files ending in .vh or .svh)
        """
        self._logger.debug(
            "Adding path %s (flags=%s, library=%s)", path, flags, library
        )

        if path.basename().split(".")[-1].lower() in ("vh", "svh"):
            file_type = getFileType(path)
            if file_type in ("verilog", "systemverilog"):
                self._include_paths[file_type].add(path.dirname())
        else:
            self._sources.add(
                (
                    path,
                    " ".join([str(x) for x in flags or []]),
                    library or "<undefined>",
                )
            )

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

        contents = ["# Files found: %s" % len(self._sources)]

        builder = self._getPreferredBuilder()
        if builder is not NotImplemented:
            contents += ["builder = %s" % builder]

        # Add include paths if they exists. Need to iterate sorted keys to
        # generate results always in the same order
        for lang in sorted(self._include_paths.keys()):
            paths = sorted(self._include_paths[lang])
            if paths:
                contents += ["include_paths[%s] = %s" % (lang, " ".join(paths))]

        if self._include_paths:
            contents += [""]

        # Add sources
        sources = []

        for path, flags, library in self._sources:
            file_type = getFileType(path)
            sources.append((file_type, library, path, flags))

        sources.sort(key=lambda x: x[2])

        for file_type, library, path, flags in sources:
            contents += [
                "{0} {1} {2}{3}".format(
                    file_type, library, path, " %s" % flags if flags else ""
                )
            ]

        self._logger.info("Resulting file has %d lines", len(contents))

        return "\n".join(contents)
