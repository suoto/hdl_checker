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
"Base source file parser"

import abc
import logging
import os.path as p
import time
from contextlib import contextmanager
from tempfile import NamedTemporaryFile
from typing import Any, Dict, Optional, Set

from .elements.dependency_spec import DependencySpec  # pylint: disable=unused-import
from .elements.design_unit import tAnyDesignUnit  # pylint: disable=unused-import

from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.path import Path
from hdlcc.utils import HashableByKey, getFileType, removeDuplicates, toBytes

_logger = logging.getLogger(__name__)


class BaseSourceFile(HashableByKey):  # pylint:disable=too-many-instance-attributes
    """
    Parses and stores information about a source file such as design
    units it depends on and design units it provides
    """

    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def _comment(self):
        """
        Should return a regex object that matches a comment (or comments)
        used by the language
        """

    def __init__(self, filename):
        # type: (Path, ) -> None
        self.filename = Path(p.abspath(p.normpath(filename.name)))
        self._cache = {}  # type: Dict[str, Any]
        self._content = None
        self._mtime = 0  # type: Optional[float]
        self.filetype = getFileType(self.filename)
        self._dependencies = None  # type: Optional[Set[DependencySpec]]
        self._design_units = None  # type: Optional[Set[tAnyDesignUnit]]
        self._libraries = None

        self.shadow_filename = None  # type: Optional[Path]

    #  @property
    #  def abspath(self):
    #      # type: (...) -> Any
    #      "Returns the absolute path of the source file"
    #      return p.abspath(self.filename)

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = self.__dict__.copy()
        del state["_content"]
        del state["shadow_filename"]
        if "raw_content" in state["_cache"]:
            del state["_cache"]["raw_content"]
        return state

    @classmethod
    def __jsonDecode__(cls, state):
        """
        Returns an object of cls based on a given state"""

        obj = super(BaseSourceFile, cls).__new__(cls)
        obj.filename = state["filename"]
        obj.shadow_filename = None
        obj.filetype = state["filetype"]
        obj._cache = state["_cache"]  # pylint: disable=protected-access
        obj._content = None  # pylint: disable=protected-access
        obj._mtime = state["_mtime"]  # pylint: disable=protected-access
        obj._dependencies = state["_dependencies"]  # pylint: disable=protected-access
        obj._design_units = state["_design_units"]  # pylint: disable=protected-access
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
        if None in (self._mtime, self.getmtime()):
            return True
        return bool(self.getmtime() > self._mtime)  # type: ignore

    def _clearCachesIfChanged(self):
        # type: () -> None
        """
        Clears all the caches if the file has changed to force updating
        every parsed info
        """
        if self._changed():
            # Since the content was set by the caller, we can't really clear
            # this unless we're handling with a proper file
            if not self.shadow_filename:
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
        if self.shadow_filename:
            return 0
        if not p.exists(self.filename.name):
            return None
        return self.filename.mtime()

    def _getTemporaryFile(self):
        # type: () -> Any
        "Gets the temporary dump file context"
        return NamedTemporaryFile(
            suffix="." + self.filename.name.split(".")[-1],
            prefix="temp_" + self.filename.basename(),
        )

    @contextmanager
    def havingBufferContent(self, content):
        # type: (...) -> Any
        """
        Context manager for handling a source file with a custom content
        that is different from the file it points to. This is intended to
        allow as-you-type checking
        """
        with self._getTemporaryFile() as tmp_file:
            _logger.debug("Dumping content to %s", tmp_file.name)
            # Save attributes that will be overwritten
            mtime, prev_content = self._mtime, self._content

            self.shadow_filename = self.filename

            # Overwrite attributes
            self.filename = tmp_file.name
            self._content = content
            self._mtime = time.time()
            # Dump data to the temporary file
            tmp_file.file.write(toBytes(self._content))
            tmp_file.file.flush()

            try:
                yield
            finally:
                _logger.debug("Clearing buffer content")

                # Restore previous values
                self._mtime, self._content = mtime, prev_content
                self.filename = self.shadow_filename
                self.shadow_filename = None

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

    def getRawSourceContent(self):
        # type: (...) -> Any
        """
        Gets the whole source content, without removing comments or
        other preprocessing
        """
        self._clearCachesIfChanged()

        if self.shadow_filename:
            return self._content
        if "raw_content" not in self._cache or self._changed():
            self._cache["raw_content"] = (
                open(self.filename.name, mode="rb").read().decode(errors="ignore")
            )

        return self._cache["raw_content"]

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
        # type: () -> Set[DependencySpec]
        """
        Cached version of the _getDependencies method
        """
        if not p.exists(self.filename.name):
            return set()

        self._clearCachesIfChanged()
        if self._dependencies is None:
            try:
                self._dependencies = set(self._getDependencies())
            except:
                print("failed to parse %s" % self.filename)
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
    def _getSourceContent(self):
        """
        Method that should implement pre parsing of the source file.
        This includes removing comments and unnecessary or unimportant
        chunks of text to make the life of the real parsing easier.
        Should return a string and NOT a list of lines
        """

    @abc.abstractmethod
    def _getDesignUnits(self):
        """
        Method that should implement the real parsing of the source file
        to find design units defined. Use the output of the getSourceContent
        method to avoid unnecessary I/O
        """

    @abc.abstractmethod
    def _getLibraries(self):
        """
        Parses the source file to find libraries required by the file
        """

    @abc.abstractmethod
    def _getDependencies(self):
        """
        Parses the source and returns a list of dictionaries that
        describe its dependencies
        """
