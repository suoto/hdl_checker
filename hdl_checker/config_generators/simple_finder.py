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

from typing import Iterable, List

from .base_generator import BaseGenerator

from hdl_checker.parser_utils import (
    filterGitIgnoredPaths,
    findRtlSourcesByPath,
    isGitRepo,
)
from hdl_checker.path import Path


def _noFilter(_, paths):
    """
    Dummy filter, returns paths
    """
    return paths


class SimpleFinder(BaseGenerator):
    """
    Implementation of BaseGenerator that searches for paths on a given
    set of paths recursively
    """

    def __init__(self, paths):  # type: (List[str]) -> None
        super(SimpleFinder, self).__init__()
        self._logger.debug("Search paths: %s", paths)
        self._paths = {Path(x) for x in paths}

    def _getLibrary(self, path):  # pylint:disable=no-self-use,unused-argument
        # type: (Path) -> str
        """
        Returns the library name given the path. On this implementation this
        returns a default name; child classes can override this to provide
        specific names (say the library name is embedded on the path itself or
        on the file's contents)
        """
        return NotImplemented

    def _findSources(self):
        # type: (...) -> Iterable[Path]
        """
        Iterates over the paths and searches for relevant files by extension.
        """
        for search_path in self._paths:
            sources = findRtlSourcesByPath(search_path)

            # Filter out ignored git files if on a git repo
            filter_func = filterGitIgnoredPaths if isGitRepo(search_path) else _noFilter

            for source_path in filter_func(search_path, sources):
                yield source_path

    def _populate(self):  # type: (...) -> None
        for path in self._findSources():
            library = self._getLibrary(path)
            self._addSource(
                path, library=None if library is NotImplemented else library
            )
