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
"Project wide database"

# pylint: disable=useless-object-inheritance

import logging
import os.path as p
from collections import namedtuple
from itertools import chain
from threading import RLock
from typing import (
    Any,
    Dict,
    FrozenSet,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
    Union,
)

import six

from hdlcc.diagnostics import (
    CheckerDiagnostic,
    DependencyNotUnique,
    PathNotInProjectFile,
)
from hdlcc.parser_utils import getSourceParserFromPath
from hdlcc.parsers.elements.dependency_spec import DependencySpec
from hdlcc.parsers.elements.design_unit import tAnyDesignUnit
from hdlcc.parsers.elements.identifier import Identifier
from hdlcc.path import Path
from hdlcc.types import BuildFlags, FileType
from hdlcc.utils import HashableByKey, getMostCommonItem

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache  # type: ignore

_logger = logging.getLogger(__name__)
_default_library_name = Identifier("library")

tResolvedLibrary = Identifier
tUnresolvedLibrary = Union[Identifier, None]
tLibraryUnitTuple = Tuple[tUnresolvedLibrary, Identifier]


class SourceEntry(namedtuple("SourceEntry", ("path", "library", "flags"))):
    """
    Placeholder for a source definintion that will get added to the database
    """

    @classmethod
    def _make(cls, iterable):  # pylint: disable=arguments-differ
        path = iterable
        info = {}

        if not isinstance(path, six.string_types):
            path = iterable[0]
            info = iterable[1]

        library = info.get("library", None)
        flags = info.get("flags", tuple())

        return super(SourceEntry, cls)._make([path, library, flags])


class Database(HashableByKey):
    "Stores info on and provides operations for a project file set"

    def __init__(self):  # type: () -> None
        self._lock = RLock()

        #  self._builder_name = None  # type: Union[str, None]
        self._paths = {}  # type: Dict[Path, float]
        self._libraries = {}  # type: Dict[Path, Identifier]
        self._inferred_libraries = set()  # type: Set[Path]
        self._flags = {}  # type: Dict[Path, BuildFlags]
        self._design_units = set()  # type: Set[tAnyDesignUnit]
        self._dependencies = {}  # type: Dict[Path, Set[DependencySpec]]
        self._diags = {}  # type: Dict[Path, Set[CheckerDiagnostic]]

        self._cached_methods = {
            getattr(self, x)
            for x in dir(self)
            if hasattr(getattr(self, x), "cache_clear")
        }

        #  self._addVunitIfFound()

    @property
    def __hash_key__(self):
        return 0

    @property
    def builder_name(self):  # type: (...) -> Union[str, None]
        "Builder name"
        return self._builder_name

    @property
    def design_units(self):  # type: (...) -> FrozenSet[tAnyDesignUnit]
        "Set of design units found"
        return frozenset(self._design_units)

    def refresh(self):
        # type: (...) -> Any
        self._clearLruCaches()

        while self._inferred_libraries:
            try:
                name = self._inferred_libraries.pop()
                del self._libraries[name]
                _logger.debug("Removed inferred library '%s'", name)
            except KeyError:
                pass

        for path in self._paths:
            self._parseSourceIfNeeded(path)

    def reset(self):
        "Clears the database from previous data"
        self._builder_name = None
        self._paths = {}
        self._libraries = {}
        self._flags = {}
        self._design_units = set()
        self._dependencies = {}
        self._diags = dict()

        self._clearLruCaches()

        # Re-add VUnit files back again
        #  self._addVunitIfFound()

    def addSources(self, entries):
        # type: (Iterable[Tuple[str, Dict[str, Union[str, BuildFlags, None]]]]) -> None
        """
        Updates the database from a iterable containing tuples in the format
        (path, {"library": library_name, "flags": path_specific_flags})
        """
        for entry in entries:
            source = SourceEntry._make(entry)
            self._addSource(Path(source.path), source.library, source.flags)

    def _addSource(self, path, library, flags):
        # type: (Path, Optional[str], BuildFlags) -> None
        """
        Adds a source to the database, triggering its parsing even if the
        source has already been added previously
        """
        # Default when updating is set the modification time to zero
        # because we're cleaning up the parsed info too
        self._paths[path] = 0
        self._flags[path] = tuple(flags)
        # TODO: Parse on a process pool
        self._parseSourceIfNeeded(path)

        if library is not None:
            self._libraries[path] = Identifier(
                library, case_sensitive=FileType.fromPath(path) != FileType.vhdl
            )

    def _addDiagnostic(self, diagnostic):
        # type: (CheckerDiagnostic) -> None
        """
        Adds a diagnostic to the diagnostic map. Diagnostics can then be read
        to report processing internals and might make it to the user interface
        """
        assert diagnostic.filename is not None
        if diagnostic.filename not in self._diags:
            self._diags[diagnostic.filename] = set()

        self._diags[diagnostic.filename].add(diagnostic)

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = {"sources": []}

        for path in self._paths:
            state["sources"].append(
                {
                    "path": path,
                    "mtime": self._paths[path],
                    "library": self._libraries[path],
                    "flags": self._flags[path],
                    "dependencies": tuple(self._dependencies[path]),
                    "diags": tuple(self._diags.get(path, ())),
                }
            )

        state["inferred_libraries"] = tuple(self._inferred_libraries)
        state["design_units"] = tuple(self._design_units)

        return state

    @classmethod
    def __jsonDecode__(cls, state):
        # pylint: disable=protected-access
        obj = super(Database, cls).__new__(cls)
        obj._design_units = {x for x in state.pop("design_units")}
        obj._inferred_libraries = {x for x in state.pop("inferred_libraries")}
        obj._paths = {}  # type: Dict[Path, float]
        obj._libraries = {}  # type: Dict[Path, Identifier]
        obj._flags = {}  # type: Dict[Path, BuildFlags]
        obj._dependencies = {}  # type: Dict[Path, Set[DependencySpec]]
        obj._diags = {}  # type: Dict[Path, Set[CheckerDiagnostic]]
        for info in state.pop("sources"):
            path = info.pop("path")
            obj._paths[path] = float(info.pop("mtime"))
            obj._libraries[path] = info.pop("library")
            obj._flags[path] = tuple(info.pop("flags"))
            obj._dependencies[path] = {x for x in info.pop("dependencies")}
            obj._diags[path] = {x for x in info.pop("diags")}
        # pylint: enable=protected-access

        return obj

    def getFlags(self, path):
        # type: (Path) -> BuildFlags
        """
        Return a list of flags for the given path or an empty tuple if the path
        is not found in the database.
        """
        return self._flags.get(path, ())

    @property
    def paths(self):
        # type: () -> Iterable[Path]
        "Returns a list of paths currently in the database"
        return self._paths.keys()

    def _updatePathLibrary(self, path, library):
        # type: (Path, Identifier) -> None
        """
        Updates dependencies of the given path so they reflect the change in
        their owner's path
        """
        if self._libraries.get(path, None):
            _logger.info(
                "Replacing old library '%s' for '%s' with '%s'",
                self._libraries[path],
                path,
                library,
            )
        else:
            _logger.info("Setting library for '%s' to '%s'", path, library)

        self._libraries[path] = library
        # Extract the unresolved dependencies that will be replaced
        unresolved_dependencies = {
            x for x in self._dependencies[path] if x.library is None
        }

        # DependencySpec is not mutable, so we actually need to replace the objects
        for dependency in unresolved_dependencies:
            self._dependencies[path].add(
                DependencySpec(
                    owner=dependency.owner,
                    name=dependency.name,
                    library=library,
                    locations=dependency.locations,
                )
            )

        # Safe to remove the unresolved ones
        self._dependencies[path] -= unresolved_dependencies

    @lru_cache()
    def getLibrary(self, path):
        # type: (Path) -> tUnresolvedLibrary
        "Gets a library of a given source (this is likely to be removed)"
        if path not in self._paths:
            # Add the path to the project but put it on a different library
            self._parseSourceIfNeeded(path)
            self._updatePathLibrary(path, Identifier("not_in_project", True))
            self._addDiagnostic(PathNotInProjectFile(path))

        elif path not in self._libraries:
            # Library is not defined, try to infer
            _logger.info("Library for '%s' not set, inferring it", path)
            library = self._inferLibraryIfNeeded(path)
            if library is not None:
                self._updatePathLibrary(path, library)
        return self._libraries.get(path, None)

    def _parseSourceIfNeeded(self, path):
        # type: (Path) -> None
        """
        Parses a given path if needed, removing info from the database prior to that
        """
        # Sources will get parsed on demand
        mtime = p.getmtime(path.name)

        if mtime == self._paths.get(path, 0):
            return

        # Update the timestamp
        self._paths[path] = mtime

        # Remove all design units that referred to this path before adding new
        # ones, but use the non API method for that to avoid recursing
        self._design_units -= frozenset(self._getDesignUnitsByPath(path))

        src_parser = getSourceParserFromPath(path)
        self._design_units |= src_parser.getDesignUnits()
        self._dependencies[path] = src_parser.getDependencies()
        self._clearLruCaches()

        #  # If the library was inferred and the source changed, undo that
        #  if self._libraries[path] in self._inferred_libraries:
        #      del self._libraries[path]

    def _clearLruCaches(self):
        "Clear caches from lru_caches"
        for meth in self._cached_methods:
            meth.cache_clear()

    #  def _addVunitIfFound(self):  # type: () -> None
    #      """
    #      Tries to import files to support VUnit right out of the box
    #      """
    #      for library, path, flags in getVunitSources():
    #          self._addSource(path, library, flags)

    def getDesignUnitsByPath(self, path):  # type: (Path) -> Set[tAnyDesignUnit]
        "Gets the design units for the given path (if any)"
        self._parseSourceIfNeeded(path)
        return self._getDesignUnitsByPath(path)

    @lru_cache(maxsize=128, typed=False)
    def _getDesignUnitsByPath(self, path):  # type: (Path) -> Set[tAnyDesignUnit]
        """
        Gets the design units for the given path (if any). Differs from the
        public method in that changes to the file are not checked before
        running.
        """
        return {x for x in self.design_units if x.owner == path}

    def getDependenciesByPath(self, path):
        # type: (Path) -> Set[DependencySpec]
        return self._dependencies[path].copy()

    def getPathsByDesignUnit(self, unit):
        # type: (tAnyDesignUnit) -> Iterator[Path]
        """
        Return the source (or sources) that define the given design
        unit
        """
        for design_unit in self.design_units:
            if (unit.name, unit.type_) == (design_unit.name, design_unit.type_):
                yield design_unit.owner

    def _inferLibraryIfNeeded(self, path):
        # type: (Path) -> tUnresolvedLibrary
        """
        Tries to infer which library the given path should be compiled on by
        looking at where and how the design units it defines are used
        """
        # Find all units this path defines
        units = set(self.getDesignUnitsByPath(path))
        _logger.debug("Units defined here in %s: %s", path, list(map(str, units)))
        # Store all cases to use in case there are multiple libraries that
        # could be used. If that happens, we'll use the most common one
        all_libraries = list(
            chain.from_iterable(
                self.getLibrariesReferredByUnit(name=unit.name) for unit in units
            )
        )

        libraries = set(all_libraries)

        if not libraries:
            _logger.warning("Couldn't work out a library for path %s", path)
            #  self._diags[path].add(PathNotInProjectFile(path))
            library = None
        elif len(libraries) == 1:
            library = libraries.pop()
        else:
            library = getMostCommonItem(all_libraries)
            _msg = []
            for lib in libraries:
                _msg.append("%s (x%d)" % (lib, all_libraries.count(lib)))
            _logger.warning(
                "Path %s is in %d libraries: %s, using %s",
                path,
                len(libraries),
                ", ".join(_msg),
                library,
            )

        self._inferred_libraries.add(path)
        return library

    @lru_cache()
    def getLibrariesReferredByUnit(self, name, library=None):
        # type: (Identifier, tUnresolvedLibrary) -> List[Identifier]
        """
        Gets libraries that the (library, name) pair is used throughout the
        project
        """
        result = []  # List[Identifier]
        for path, dependencies in self._dependencies.items():
            for dependency in dependencies:
                library = dependency.library
                if library is None or name != dependency.name:
                    continue

                # If the dependency's library refers to 'work', it's actually
                # referring to the library its owner is in
                if library is None:
                    library = self._libraries.get(path, None)
                if library is not None:
                    result.append(library)

        return result

    @lru_cache()
    def getPathsDefining(self, name, library=None):
        # type: (Identifier, tUnresolvedLibrary) -> Iterable[Path]
        """
        Search for paths that define a given name optionally inside a library.
        """
        _logger.debug("Searching for paths defining %s.%s", library, name)

        units = {unit for unit in self.design_units if unit.name == name}

        if not units:
            _logger.warning(
                "Could not find any source defining '%s' (%s)", name, library
            )
            return ()

        if library is not None:
            units_matching_library = {
                unit for unit in units if (self.getLibrary(unit.owner) == library)
            }

            if not units_matching_library:
                # If no units match when using the library, it means the database
                # is incomplete and we should try to infer the library from the
                # usage of this unit
                for owner in {x.owner for x in units}:
                    # Force getting library for this path to trigger library
                    # inference if needed
                    self.getLibrary(owner)
            else:
                units = units_matching_library

        paths = {unit.owner for unit in units}

        _logger.debug(
            "Found %d paths defining %s: %s",
            len(paths),
            tuple(str(x) for x in units),
            paths,
        )

        return paths

    def getDependenciesUnits(self, path):
        # type: (Path) -> Set[tLibraryUnitTuple]
        """
        Returns design units that should be compiled before compiling the given
        path but only within the project file set. If a design unit can't be
        found in any source, it will be silently ignored.
        """
        units = set()  # type: Set[tLibraryUnitTuple]

        search_paths = set((path,))
        own_units = {
            (self.getLibrary(path), x.name) for x in self.getDesignUnitsByPath(path)
        }

        while search_paths:
            # Get the dependencies of the search paths and which design units
            # they define and remove the ones we've already seen
            new_deps = {
                (
                    dependency.library or self.getLibrary(dependency.owner),
                    dependency.name,
                )
                for search_path in search_paths
                for dependency in self._dependencies[search_path]
            } - units

            _logger.debug(
                "Searching %s resulted in dependencies: %s", search_paths, new_deps
            )

            # Add the new ones to the set tracking the dependencies seen since
            # the search started
            units |= new_deps

            # Paths to be searched on the next iteration are the paths of the
            # dependencies we have not seen before
            search_paths = set()

            for library, name in new_deps:
                new_paths = set(self.getPathsDefining(name=name, library=library))
                if not new_paths:
                    _logger.warning(
                        "Couldn't find where %s/%s is defined", library, name
                    )
                elif len(new_paths) > 1:
                    _logger.warning(
                        "%s/%s is defined in multiple files: %s",
                        library,
                        name,
                        new_paths,
                    )
                    #  self._diags[path].add(DependencyNotUnique(
                    #      filename=path,
                    #      design_unit='%s.%s' % (library, name),
                    #      actual=
                    #      choices=
                    #      line_number=
                    #      column_number=))

                search_paths |= new_paths

            _logger.debug("Search paths: %s", search_paths)

        # Remove units defined by the path passed as argument
        units -= own_units
        return units

    def getBuildSequence(self, path):
        # type: (Path) -> Iterable[Tuple[Identifier, Path]]
        """
        Gets the build sequence that satisfies the preconditions to compile the
        given path
        """
        units_compiled = set()  # type: Set[tLibraryUnitTuple]
        units_to_build = self.getDependenciesUnits(path)
        paths_to_build = set(
            chain.from_iterable(
                self.getPathsDefining(name=name, library=library)
                for library, name in units_to_build
            )
        )

        # Limit the number of iterations to the worst case of every pass
        # compiling only a single source and all of them having a chain of
        # dependencies on the previous one
        iteration_limit = len(paths_to_build)

        for i in range(iteration_limit):
            paths_built = set()  # type: Set[Path]

            for current_path in paths_to_build:
                current_path_library = self.getLibrary(current_path)
                own = {
                    (current_path_library, x.name)
                    for x in self.getDesignUnitsByPath(current_path)
                }

                deps = {
                    (x.library or self.getLibrary(x.owner), x.name)
                    for x in self._dependencies[current_path]
                }
                still_needed = deps - units_compiled - own

                if still_needed:
                    if _logger.isEnabledFor(logging.DEBUG):  # pragma: no cover
                        _msg = [(library, name.name) for library, name in still_needed]
                        _logger.debug("%s still needs %s", current_path, _msg)
                else:
                    yield self.getLibrary(
                        current_path
                    ) or _default_library_name, current_path
                    paths_built.add(current_path)
                    units_compiled |= own

            paths_to_build -= paths_built
            units_to_build -= units_compiled

            if not paths_built:
                if paths_to_build:
                    _logger.warning(
                        "%d paths were not built: %s",
                        len(paths_to_build),
                        list(map(str, paths_to_build)),
                    )
                else:
                    _logger.info("Nothing more to do after %d steps", i)
                return

            _logger.info(
                "Got %d units compiled: %s", len(units_compiled), units_compiled
            )

        _logger.error("Iteration limit of %d reached", iteration_limit)
