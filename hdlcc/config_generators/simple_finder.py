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

import os
import os.path as p
from typing import Generator, List

from .base_generator import BaseGenerator

from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.path import Path
from hdlcc.utils import UnknownTypeExtension, getFileType, isFileReadable

_SOURCE_EXTENSIONS = "vhdl", "sv", "v"
_HEADER_EXTENSIONS = "vh", "svh"


class SimpleFinder(BaseGenerator):
    """
    Implementation of BaseGenerator that searches for paths on a given
    set of paths recursively
    """

    def __init__(self, paths):  # type: (List[Path]) -> None
        super(SimpleFinder, self).__init__()
        self._logger.debug("Search paths: %s", [x.abspath for x in paths])
        self._paths = paths
        self._valid_extensions = tuple(
            list(_SOURCE_EXTENSIONS) + list(_HEADER_EXTENSIONS)
        )

    def _getLibrary(self, path):  # type: (Path) -> str
        """
        Returns the library name given the path. On this implementation this
        returns a default name; child classes can override this to provide
        specific names (say the library name is embedded on the path itself or
        on the file's contents)
        """
        return NotImplemented

    def _findSources(self):  # type: () -> Generator[Path, None, None]
        """
        Iterates over the paths and searches for relevant files by extension.
        """
        for path in self._paths:
            for dirpath, _, filenames in os.walk(path.name):
                for filename in filenames:
                    path = p.join(dirpath, filename)

                    if not p.isfile(path.name):
                        continue

                    try:
                        # getFileType will fail if the file's extension is not
                        # valid (one of '.vhd', '.vhdl', '.v', '.vh', '.sv',
                        # '.svh')
                        getFileType(filename)
                    except UnknownTypeExtension:
                        continue

                    if isFileReadable(path.name):
                        yield path

    def _populate(self):  # type: (...) -> None
        for path in self._findSources():
            library = self._getLibrary(path)
            self._addSource(
                path, library="work" if library is NotImplemented else library
            )
