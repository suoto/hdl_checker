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
from functools import lru_cache
from itertools import chain
from threading import RLock
from typing import (  # List,
    Any,
    Dict,
    FrozenSet,
    Generator,
    Iterable,
    Iterator,
    List,
    Optional,
    Set,
    Tuple,
)

#  from hdlcc import exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import BuilderName, getVunitSources
from hdlcc.parsers import (
    ConfigParser,
    DependencySpec,
    Identifier,
    getSourceParserFromPath,
    tAnyDesignUnit,
)
from hdlcc.path import Path
from hdlcc.utils import HashableByKey, getFileType, getMostCommonItem

_logger = logging.getLogger(__name__)


class Database(HashableByKey):
    "Stores info on and provides operations for a project file set"

    def __init__(self):  # type: () -> None
        self._lock = RLock()

        self._builder_name = BuilderName.fallback
        self._paths = {}  # type: Dict[Path, float]
        self._libraries = {}  # type: Dict[Path, Identifier]
        self._flags = {}  # type: Dict[Path, t.BuildFlags]
        self._design_units = set()  # type: Set[tAnyDesignUnit]
        self._dependencies = {}  # type: Dict[Path, Set[DependencySpec]]
        self._cache = {}  # type: Dict[Path, Set[tAnyDesignUnit]]

        self._addVunitIfFound()

    @property
    def __hash_key__(self):
        return 0

    @property
    def builder_name(self):  # type: (...) -> BuilderName
        "Builder name"
        return self._builder_name

    @property
    def design_units(self):  # type: (...) -> FrozenSet[tAnyDesignUnit]
        "Set of design units found"
        return frozenset(self._design_units)

    def reset(self):
        "Clears the database from previous data"
        self._builder_name = BuilderName.fallback
        self._paths = {}
        self._libraries = {}
        self._flags = {}
        self._design_units = set()
        self._dependencies = {}

        # Re-add VUnit files back again
        self._addVunitIfFound()

    def accept(self, parser):  # type: (ConfigParser) -> None
        "Updates the database from a configuration parser"
        return self.updateFromDict(parser.parse())

    def updateFromDict(self, config):  # type: (Any) -> None
        "Updates the database from a dictionary"

        self._builder_name = config.get("builder_name", self._builder_name)

        for library, path, flags in config.get("sources", []):
            self._addSource(library, Path(path), flags)

    def _addSource(self, library, path, flags):
        # type: (str, Path, t.BuildFlags) -> None
        """
        Adds a source to the database, triggering its parsing even if the
        source is already on the database
        """
        # Default when updating is set the modification time to zero
        # because we're cleaning up the parsed info too
        self._paths[path] = 0
        self._flags[path] = tuple(flags)
        # TODO: Parse on a process pool
        self._parseSourceIfNeeded(path)

        if library is not None:
            self._libraries[path] = Identifier(
                library, case_sensitive=getFileType(path) != t.FileType.vhd
            )

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = {}

        for path in self._paths:
            state[path] = {
                "library": self._libraries[path],
                "flags": self._flags[path],
                "design_units": tuple(self._design_units),
                "dependencies": self._dependencies[path],
            }

        return state

    def getFlags(self, path):
        # type: (Path) -> t.BuildFlags
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
                "Replacing old library '%s' for %s with '%s'",
                self._libraries[path],
                path,
                library,
            )

        self._libraries[path] = library
        # Extract the unresolved dependencies that will be replaced
        unresolved_dependencies = {
            x for x in self._dependencies[path] if x.library.name == "work"
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

    def getLibrary(self, path):
        # type: (Path) -> Identifier
        "Gets a library of a given source (this is likely to be removed)"
        if path not in self._paths:
            self._updatePathLibrary(path, Identifier("<path_not_found>", True))
        elif path not in self._libraries:
            self._updatePathLibrary(path, self._inferLibraryIfNeeded(path))
        return self._libraries[path]

    def _parseSourceIfNeeded(self, path):
        # type: (Path) -> None
        """
        Parses a given path if needed, removing info from the database prior to that
        """
        # Sources will get parsed on demand
        mtime = p.getmtime(path.name)

        if mtime == self._paths.get(path, 0):
            return

        #  _logger.debug("Parsing %s (%s)", path, mtime)

        # Update the timestamp
        self._paths[path] = mtime
        # Remove all design units that referred to this path before adding new
        # ones, but use the non API method for that to avoid recursing

        if path in self._paths:
            before = len(self._design_units)
            # Need to use _getDesignUnitsByPath to avoid circular recursion
            self._design_units -= frozenset(self._getDesignUnitsByPath(path))

            #  del self._cache[path]

            if before != len(self._design_units):
                _logger.debug(
                    "Reparsing source removes %d design units",
                    before - len(self._design_units),
                )

        src_parser = getSourceParserFromPath(path)
        self._design_units |= src_parser.getDesignUnits()
        self._dependencies[path] = src_parser.getDependencies()

        # Clear caches from lru_caches
        for attr_name in dir(self):
            if attr_name.startswith("__"):
                continue
            try:
                meth = getattr(getattr(self, attr_name), "cache_clear")
                _logger.info("Clearning cache for %s", attr_name)
                meth()
            except AttributeError:
                pass

    def _addVunitIfFound(self):  # type: () -> None
        """
        Tries to import files to support VUnit right out of the box
        """
        for library, path, flags in getVunitSources(self._builder_name):
            self._addSource(library, path, flags)

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
        # type: (Path) -> Identifier
        """
        Tries to infer which library the given path should be compiled on by
        looking at where and how the design units it defines are used
        """
        _logger.debug("Inferring library for path %s", path)
        # Find all units this path defines
        units = set(self.getDesignUnitsByPath(path))
        _logger.debug("Units defined here: %s", units)
        all_libraries = []  # type: List[Identifier]
        # For each unit, find every dependency with the same name
        for unit in units:
            _logger.debug("Checking unit %s", unit)
            all_libraries += list(self.getLibrariesReferredByUnit(name=unit.name))

        libraries = set(all_libraries)

        if not libraries:
            _logger.warning("Couldn't work out a library for path %s", path)
            library = Identifier("__unknown_library_name__", False)
        elif len(libraries) == 1:
            library = libraries.pop()
        else:
            library = getMostCommonItem(all_libraries)
            _logger.warning(
                "Path %s is in %d libraries: %s, using %s",
                path,
                len(libraries),
                list(map(str, libraries)),
                library,
            )

        return library

    def getLibrariesReferredByUnit(self, name, library=None):
        # type: (Identifier, Optional[Identifier]) -> Iterable[Identifier]
        """
        Gets libraries that the (library, name) pair is used throughout the
        project
        """
        for dependencies in self._dependencies.values():
            #  if name not in (x.name for x in dependencies):
            #      continue
            for dependency in dependencies:
                library = dependency.library
                if library is None:
                    continue
                if name != dependency.name:
                    continue

                # If the dependency's library refers to 'work', it's actually
                # referring to the library its owner is in
                if library.name == "work":
                    #
                    library = self._libraries.get(dependency.owner, None)
                    #  library = self.getLibrary(dependency.owner)
                if library is not None:
                    yield library

    def getPathsDefining(self, name, library=None):
        # type: (Identifier, Optional[Identifier]) -> Iterable[Path]
        """
        Search for paths that define a given name optionally inside a library.
        """
        _logger.debug("Searching for paths defining %s.%s", library, name)

        units = {unit for unit in self.design_units if unit.name == name}

        _logger.debug("Units step 1: %s", tuple(str(x) for x in units))

        if not units:
            _logger.warning(
                "Could not find any source defining '%s' (%s)", name, library
            )
            return ()

        if library is not None:
            units_matching_library = {
                unit for unit in units if (self.getLibrary(unit.owner) == library)
            }
            _logger.debug(
                "Units step 2: %s", tuple(str(x) for x in units_matching_library)
            )

            if not units_matching_library:
                # If no units match when using the library, it means the database
                # is incomplete and we should try to infer the library from the
                # usage of this unit
                for owner in {x.owner for x in units}:
                    self.getLibrary(owner)
                    #  self._inferLibraryIfNeeded(owner)
            else:
                units = units_matching_library

        _logger.debug("Units step 3: %s", tuple(str(x) for x in units))

        return (unit.owner for unit in units)

    def _resolveLibraryIfNeeded(self, library, name):
        # type: (Identifier, Identifier) -> Tuple[Identifier, Identifier]
        """
        Tries to resolve undefined libraries by checking usages of 'name'
        """
        if library is None:
            paths = tuple(self.getPathsDefining(name=name, library=None))
            if not paths:
                _logger.warning("Couldn't find a path definint unit %s", name)
                library = Identifier("work", False)
                assert False
            elif len(paths) == 1:
                path = paths[0]
                #  library = self._libraries[path]
                library = self.getLibrary(path)
            else:
                _logger.warning("Unit %s is defined in %d places", name, len(paths))
                library = Identifier("work", False)
                assert False
        return library, name

    def getDependenciesUnits(self, path):
        # type: (Path) -> Set[Tuple[Identifier, Identifier]]
        """
        Returns design units that should be compiled before compiling the given
        path but only within the project file set. If a design unit can't be
        found in any source, it will be silently ignored.
        """
        #  _logger.debug("Getting dependencies' units %s", path)
        units = set()  # type: Set[Tuple[Identifier, Identifier]]

        search_paths = set((path,))
        own_units = {
            (self.getLibrary(path), x.name) for x in self.getDesignUnitsByPath(path)
        }

        while search_paths:
            list(self.getLibrary(search_path) for search_path in search_paths)
            # Get the dependencies of the search paths and which design units
            # they define and remove the ones we've already seen
            new_deps = {
                (x.library, x.name)
                for search_path in search_paths
                for x in self._dependencies[search_path]
            } - units

            _logger.debug("New dependencies: %s", new_deps)

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

                search_paths |= new_paths

            _logger.debug("Search paths: %s", search_paths)

        # Remove units defined by the path passed as argument
        units -= own_units
        return {self._resolveLibraryIfNeeded(library, name) for library, name in units}

    def getBuildSequence(self, path):
        # type: (Path) -> Generator[Tuple[t.LibraryName, Path], None, None]
        """
        Gets the build sequence that satisfies the preconditions to compile the
        given path
        """
        units_compiled = set()  # type: Set[Tuple[Identifier, Identifier]]
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
            paths_to_remove = set()  # type: Set[Path]

            #  _logger.warning(
            #      "### %d units remaining: %s",
            #      len(units_to_build),
            #      list("%s.%s" % (x[0], x[1]) for x in units_to_build),
            #  )

            for current_path in paths_to_build:
                current_path_library = self.getLibrary(current_path)
                own = {
                    (current_path_library, x.name)
                    for x in self.getDesignUnitsByPath(current_path)
                }

                deps = {(x.library, x.name) for x in self._dependencies[current_path]}
                still_needed = deps - units_compiled - own

                if still_needed:
                    if _logger.isEnabledFor(logging.DEBUG):
                        _msg = [
                            (library.name, name.name) for library, name in still_needed
                        ]
                        _logger.debug("%s still needs %s", current_path, _msg)
                else:
                    yield self.getLibrary(current_path).name, current_path
                    paths_to_remove.add(current_path)
                    units_compiled |= own

            paths_to_build -= paths_to_remove
            units_to_build -= units_compiled

            if not paths_to_remove:
                _logger.info("Nothing more to do after %d steps", i)
                return

            _logger.info(
                "Got %d units compiled: %s", len(units_compiled), units_compiled
            )

        _logger.error("Iteration limit of %d reached", iteration_limit)
