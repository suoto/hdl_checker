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
from pprint import pformat
from typing import Dict, Optional, Set, Tuple

from hdl_checker.path import Path
from hdl_checker.types import BuildFlags, FileType

SourceSpec = Tuple[Path, BuildFlags, Optional[str]]


class BaseGenerator:
    """
    Base class implementing creation of config file semi automatically
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self):  # type: () -> None
        self._logger = logging.getLogger(self.__class__.__name__)
        self._sources = set()  # type: Set[SourceSpec]

    def _addSource(self, path, flags=None, library=None):
        # type: (Path, BuildFlags, Optional[str]) -> None
        """
        Add a source to project, which includes regular sources AND headers
        """
        self._logger.debug(
            "Adding path %s (flags=%s, library=%s)", path, flags, library
        )
        self._sources.add((path, flags or (), library))

    @abc.abstractmethod
    def _populate(self):  # type: () -> None
        """
        Method that will be called for generating the project file contets and
        should be implemented by child classes
        """

    def _getPreferredBuilder(self):  # pylint:disable=no-self-use
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

        self._logger.info("Resulting project:\n%s", pformat(project))

        return project
