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
"Base class that implements the base builder flow"

import abc
import logging
import os
import os.path as p
from threading import Lock
from typing import Any, Dict, Iterable, Optional, Set, Tuple

from hdlcc.database import Database  # pylint: disable=unused-import
from hdlcc.diagnostics import CheckerDiagnostic, DiagType
from hdlcc.exceptions import SanityCheckError
from hdlcc.parsers.elements.identifier import Identifier
from hdlcc.path import Path
from hdlcc.types import (
    BuildFlags,
    BuildFlagScope,
    FileType,
    RebuildInfo,
    RebuildLibraryUnit,
    RebuildPath,
    RebuildUnit,
)


class BaseBuilder(object):  # pylint: disable=useless-object-inheritance
    """
    Class that implements the base builder flow
    """

    __metaclass__ = abc.ABCMeta

    # Set an empty container for the default flags
    default_flags = {
        BuildFlagScope.dependencies: {},
        BuildFlagScope.single: {},
        BuildFlagScope.all: {},
    }  # type: Dict[BuildFlagScope, Dict[FileType, BuildFlags]]

    _external_libraries = {FileType.vhdl: set(), FileType.verilog: set()}  # type: dict

    _include_paths = {FileType.vhdl: set(), FileType.verilog: set()}  # type: dict

    @classmethod
    def addExternalLibrary(cls, lang, library_name):
        # type: (...) -> Any
        """
        Adds an external library so it may be referenced by the builder
        directly
        """
        assert lang in cls._external_libraries, "Uknown language '%s'" & lang
        cls._external_libraries[lang].add(library_name)

    @classmethod
    def addIncludePath(cls, lang, path):
        # type: (...) -> Any
        """
        Adds an include path to be used by the builder where applicable
        """
        cls._include_paths[lang].add(path)

    @abc.abstractproperty
    def builder_name(self):
        # type: (...) -> Any
        """
        Defines the builder identification
        """

    @abc.abstractproperty
    def file_types(self):
        # type: (...) -> Any
        """
        Returns the file types supported by the builder
        """

    def __init__(self, target_folder, database):
        # type: (Path, Database) -> None
        # Shell accesses must be atomic
        self._lock = Lock()

        self._logger = logging.getLogger(__package__ + "." + self.builder_name)
        self._database = database
        self._target_folder = p.abspath(p.expanduser(target_folder.name))
        self._build_info_cache = {}  # type: Dict[Path, Dict[str, Any]]
        self._builtin_libraries = set()  # type: Set[Identifier]
        self._added_libraries = set()  # type: Set[Identifier]

        # Skip creating a folder for the fallback builder
        if self.builder_name != "fallback":
            if not p.exists(self._target_folder):
                self._logger.info("Target folder '%s' was created", self._target_folder)
                os.makedirs(self._target_folder)
            else:
                self._logger.info("%s already exists", self._target_folder)

        self.checkEnvironment()

        try:
            self._parseBuiltinLibraries()
            if self._logger.isEnabledFor(logging.DEBUG):  # pragma: no cover
                if self._builtin_libraries:  # pragma: no cover
                    self._logger.debug(
                        "Builtin libraries: %s", tuple(self._builtin_libraries)
                    )
                else:  # pragma: no cover
                    self._logger.debug("No builtin libraries found")
        except NotImplementedError:
            pass

    @classmethod
    def __jsonDecode__(cls, state):
        # type: (...) -> Any
        """
        Returns an object of cls based on a given state
        """
        # pylint: disable=protected-access
        obj = super(BaseBuilder, cls).__new__(cls)
        obj._logger = logging.getLogger(state.pop("_logger"))
        obj._builtin_libraries = set(state.pop("_builtin_libraries"))
        obj._added_libraries = set(state.pop("_added_libraries"))

        obj._lock = Lock()
        obj._build_info_cache = {}
        obj.__dict__.update(state)
        # pylint: enable=protected-access

        return obj

    def __jsonEncode__(self):
        # type: (...) -> Any
        """
        Gets a dict that describes the current state of this object
        """
        state = self.__dict__.copy()
        state["_logger"] = self._logger.name
        state["_builtin_libraries"] = list(self._builtin_libraries)
        state["_added_libraries"] = list(self._added_libraries)
        del state["_build_info_cache"]
        del state["_lock"]
        return state

    @staticmethod
    def isAvailable():  # pragma: no cover
        # type: (...) -> Any
        """
        Method that should be overriden by child classes and return True
        if the given builder is available on the current environment
        """
        raise NotImplementedError

    def checkEnvironment(self):
        # type: (...) -> Any
        """
        Sanity environment check for child classes. Any exception raised
        is translated to SanityCheckError exception.
        """
        try:
            self._checkEnvironment()
        except Exception as exc:
            raise SanityCheckError(self.builder_name, str(exc))

    @abc.abstractmethod
    def _shouldIgnoreLine(self, line):
        """
        Method called for each stdout output and should return True if
        the given line should not be parsed using _makeRecords
        and _searchForRebuilds
        """

    @abc.abstractmethod
    def _makeRecords(self, line):
        """
        Static method that converts a string into a dict that has
        elements identifying its fields
        """

    def _getRebuilds(self, path, line, library):
        # type: (Path, str, Identifier) -> Set[RebuildInfo]
        """
        Gets info on what should be rebuilt to satisfy the builder
        """
        try:
            parse_results = self._searchForRebuilds(line)
        except NotImplementedError:  # pragma: no cover
            return set()

        rebuilds = set()  # type: Set[RebuildInfo]
        for rebuild in parse_results:
            unit_type = rebuild.get("unit_type", None)
            library_name = rebuild.get("library_name", None)
            unit_name = rebuild.get("unit_name", None)
            rebuild_path = rebuild.get("rebuild_path", None)

            if None not in (unit_type, unit_name):
                for dependency in self._database.getDependenciesByPath(path):
                    if dependency.name.name == rebuild["unit_name"]:
                        rebuilds.add(RebuildUnit(unit_name, unit_type))
                        break
            elif None not in (library_name, unit_name):
                if library_name == "work":
                    library_name = library.name
                rebuilds.add(RebuildLibraryUnit(unit_name, library_name))
            elif rebuild_path is not None:
                # GHDL sometimes gives the full path of the file that
                # should be recompiled
                rebuilds.add(RebuildPath(rebuild_path))
            else:  # pragma: no cover
                self._logger.warning("Don't know what to do with %s", rebuild)

        return rebuilds

    def _searchForRebuilds(self, line):  # pragma: no cover
        # type: (...) -> Any
        """
        Finds units that the builders is telling us to rebuild
        """
        raise NotImplementedError

    def _parseBuiltinLibraries(self):
        # type: (...) -> Any
        """
        Discovers libraries that exist regardless before we do anything
        """
        raise NotImplementedError

    @property
    def builtin_libraries(self):
        # type: (...) -> Any
        """
        Return a list with the libraries this compiler currently knows
        """
        return frozenset(self._builtin_libraries)

    @abc.abstractmethod
    def _checkEnvironment(self):
        """
        Sanity environment check that should be implemented by child
        classes. Nothing is done with the return, the child class should
        raise an exception by itself
        """

    @abc.abstractmethod
    def _buildSource(self, path, library, flags=None):
        # type: (Path, Identifier, Optional[BuildFlags]) -> Iterable[str]
        """
        Callback called to actually build the source
        """

    def _getFlags(self, path, scope):
        # type: (Path, BuildFlagScope) -> BuildFlags
        """
        Gets flags to build the path, both builder based and from the database.
        If a build is forced, assume we're building a single file (not its
        dependencies)
        """
        return tuple(self._database.getFlags(path, scope)) + tuple(
            self.default_flags.get(scope, {}).get(FileType.fromPath(path), ())
            + self.default_flags.get(BuildFlagScope.all, {}).get(
                FileType.fromPath(path), ()
            )
        )

    def _buildAndParse(
        self, path, library, flags
    ):  # type: (Path, Identifier, BuildFlags) -> Tuple[Set[CheckerDiagnostic],Set[RebuildInfo]]
        """
        Runs _buildSource method and parses the output to find message
        records and units that should be rebuilt
        """
        if library is None:
            library = self._database.getLibrary(path)  # or Identifier("work")

        self._createLibraryIfNeeded(library)

        for lib in (x.library for x in self._database.getDependenciesByPath(path)):
            self._createLibraryIfNeeded(lib or Identifier("work"))

        diagnostics = set()  # type: Set[CheckerDiagnostic]
        rebuilds = set()  # type: Set[RebuildInfo]

        for line in self._buildSource(path, library, flags=flags):
            if self._shouldIgnoreLine(line):
                continue

            #  # In case we're compiling a temporary dump, replace in the lines
            #  # all references to the temp name with the original (shadow)
            #  # filename
            #  if path.shadow_filename:
            #      line = line.replace(path.filename, path.shadow_filename)

            for _record in self._makeRecords(line):
                try:
                    diagnostics |= {_record}
                except:
                    self._logger.exception(
                        " - %s hash: %s | %s",
                        _record,
                        _record.__hash__,
                        type(_record).__mro__,
                    )
                    raise
            rebuilds |= self._getRebuilds(path, line, library)

        # If no filename is set, assume it's for the current path
        for diag in diagnostics:
            if diag.filename is None:
                diag.filename = path

        self._logBuildResults(diagnostics, rebuilds)

        return diagnostics, rebuilds

    def _logBuildResults(self, diagnostics, rebuilds):  # pragma: no cover
        # type: (...) -> Any
        """
        Logs diagnostics and rebuilds only for debugging purposes
        """
        if not self._logger.isEnabledFor(logging.DEBUG):
            return

        if diagnostics:
            self._logger.debug("Diagnostic messages found")
            for record in diagnostics:
                self._logger.debug(record)

        if rebuilds:
            self._logger.debug("Rebuilds found")
            for rebuild in rebuilds:
                self._logger.debug(rebuild)

    def _createLibraryIfNeeded(self, library):
        # type: (Identifier) -> None
        if library in self._added_libraries | self._builtin_libraries:
            return
        self._createLibrary(library)

    @abc.abstractmethod
    def _createLibrary(self, library):
        # type: (...) -> Any
        """
        Callback called to create a library
        """

    def _isFileTypeSupported(self, path):
        # type: (Path) -> bool
        """
        Checks if a given path is supported by this builder
        """
        return FileType.fromPath(path) in self.file_types

    def build(self, path, library, scope, forced=False):
        # type: (Path, Identifier, BuildFlagScope, bool) -> Tuple[Set[CheckerDiagnostic], Set[RebuildInfo]]
        """
        Method that interfaces with parents and implements the building
        chain
        """

        if not self._isFileTypeSupported(path):
            self._logger.warning(
                "Path '%s' with file type '%s' is not " "supported",
                path,
                FileType.fromPath(path),
            )
            return set(), set()

        if path not in self._build_info_cache:
            self._build_info_cache[path] = {
                "compile_time": 0.0,
                "diagnostics": [],
                "rebuilds": [],
            }

        cached_info = self._build_info_cache[path]

        build = False
        if forced:
            build = True
            self._logger.info("Forcing build of %s", str(path))
        elif path.mtime > cached_info["compile_time"]:
            build = True
            self._logger.info("Building %s", str(path))

        if build:
            with self._lock:
                diagnostics, rebuilds = self._buildAndParse(
                    path, library, self._getFlags(path, scope)
                )

            cached_info["diagnostics"] = diagnostics
            cached_info["rebuilds"] = rebuilds
            cached_info["compile_time"] = path.mtime

            if DiagType.ERROR in [x.severity for x in diagnostics]:
                cached_info["compile_time"] = 0

        else:
            self._logger.debug("Nothing to do for %s", path)
            diagnostics = cached_info["diagnostics"]
            rebuilds = cached_info["rebuilds"]

        return diagnostics, rebuilds
