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
"Base source file parser"

import abc
import logging
import os.path as p
from typing import Any, Dict, Optional, Set

from .elements.dependency_spec import (
    BaseDependencySpec,
)  # pylint: disable=unused-import
from .elements.design_unit import tAnyDesignUnit  # pylint: disable=unused-import

from hdl_checker.path import Path
from hdl_checker.types import FileType
from hdl_checker.utils import HashableByKey, readFile, removeDuplicates

_logger = logging.getLogger(__name__)


class BaseSourceFile(HashableByKey):  # pylint:disable=too-many-instance-attributes
    """
    Parses and stores information about a source file such as design
    units it depends on and design units it provides
    """

    __metaclass__ = abc.ABCMeta

    def __init__(self, filename):
        # type: (Path, ) -> None
        assert isinstance(filename, Path), "Invalid type: {}".format(filename)
        self.filename = filename
        self._cache = {}  # type: Dict[str, Any]
        self._content = None  # type: Optional[str]
        self._mtime = 0  # type: Optional[float]
        self.filetype = FileType.fromPath(self.filename)
        self._dependencies = None  # type: Optional[Set[BaseDependencySpec]]
        self._design_units = None  # type: Optional[Set[tAnyDesignUnit]]
        self._libraries = None

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = self.__dict__.copy()
        del state["_content"]
        del state["_design_units"]
        del state["_dependencies"]
        return state

    @classmethod
    def __jsonDecode__(cls, state):
        """
        Returns an object of cls based on a given state
        """
        obj = super(BaseSourceFile, cls).__new__(cls)
        obj.filename = state["filename"]
        obj.filetype = state["filetype"]
        obj._cache = state["_cache"]  # pylint: disable=protected-access
        obj._content = None  # pylint: disable=protected-access
        obj._mtime = state["_mtime"]  # pylint: disable=protected-access
        obj._dependencies = None  # pylint: disable=protected-access
        obj._design_units = None  # pylint: disable=protected-access
        obj._libraries = state["_libraries"]  # pylint: disable=protected-access

        return obj

    def __repr__(self):
        return "{}(filename={}, design_units={}, dependencies={})".format(
            self.__class__.__name__,
            self.filename,
            self._design_units,
            self._dependencies,
        )

    @property
    def __hash_key__(self):
        return (self.filename, self._content)

    def _changed(self):
        # type: (...) -> Any
        """
        Checks if the file changed based on the modification time
        provided by p.getmtime
        """
        if not p.exists(str(self.filename)):
            return False
        return bool(self.getmtime() > self._mtime)  # type: ignore

    def _clearCachesIfChanged(self):
        # type: () -> None
        """
        Clears all the caches if the file has changed to force updating
        every parsed info
        """
        if self._changed():
            self._content = None
            self._dependencies = None
            self._design_units = None
            self._libraries = None
            self._cache = {}

    def getmtime(self):
        # type: () -> Optional[float]
        """
        Gets file modification time as defined in p.getmtime
        """
        if not p.exists(self.filename.name):
            return None
        return self.filename.mtime

    def getSourceContent(self):
        # type: (...) -> Any
        """
        Cached version of the _getSourceContent method
        """
        self._clearCachesIfChanged()

        if self._content is None:
            self._content = self._getSourceContent()
            self._mtime = self.getmtime()

        return self._content

    def _getSourceContent(self):
        # type: () -> str
        """
        Method that can be overriden to change the contents of the file, like
        striping comments off.
        """
        return readFile(str(self.filename))

    def getDesignUnits(self):  # type: () -> Set[tAnyDesignUnit]
        """
        Cached version of the _getDesignUnits method
        """
        if not p.exists(self.filename.name):
            return set()
        self._clearCachesIfChanged()
        if self._design_units is None:
            self._design_units = set(self._getDesignUnits())

        return self._design_units

    def getDependencies(self):
        # type: () -> Set[BaseDependencySpec]
        """
        Cached version of the _getDependencies method
        """
        if not p.exists(self.filename.name):
            return set()

        self._clearCachesIfChanged()
        if self._dependencies is None:
            try:
                self._dependencies = set(self._getDependencies())
            except:  # pragma: no cover
                print("Failed to parse %s" % self.filename)
                _logger.exception("Failed to parse %s", self.filename)
                raise

        return self._dependencies

    def getLibraries(self):
        # type: (...) -> Any
        """
        Cached version of the _getLibraries method
        """
        if not p.exists(self.filename.name):
            return []

        self._clearCachesIfChanged()
        if self._libraries is None:
            self._libraries = removeDuplicates(self._getLibraries())

        return self._libraries

    @abc.abstractmethod
    def _getDesignUnits(self):
        """
        Method that should implement the real parsing of the source file
        to find design units defined. Use the output of the getSourceContent
        method to avoid unnecessary I/O
        """

    def _getLibraries(self):
        """
        Parses the source file to find libraries required by the file
        """
        return ()

    @abc.abstractmethod
    def _getDependencies(self):
        """
        Parses the source and returns a list of dictionaries that
        describe its dependencies
        """
