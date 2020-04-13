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
"Project wide database"

# pylint: disable=useless-object-inheritance

import logging
import os.path as p
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

from hdl_checker import DEFAULT_LIBRARY
from hdl_checker.diagnostics import (  # pylint: disable=unused-import
    CheckerDiagnostic,
    DependencyNotUnique,
    PathLibraryIsNotUnique,
    PathNotInProjectFile,
)
from hdl_checker.parser_utils import flattenConfig, getSourceParserFromPath
from hdl_checker.parsers.elements.dependency_spec import (
    BaseDependencySpec,
    IncludedPath,
    RequiredDesignUnit,
)
from hdl_checker.parsers.elements.design_unit import (  # pylint: disable=unused-import,
    tAnyDesignUnit,
)
from hdl_checker.parsers.elements.identifier import Identifier
from hdl_checker.path import Path, TemporaryPath  # pylint: disable=unused-import
from hdl_checker.types import (  # pylint: disable=unused-import
    BuildFlags,
    BuildFlagScope,
    FileType,
)
from hdl_checker.utils import HashableByKey, getMostCommonItem, isFileReadable

try:
    from functools import lru_cache
except ImportError:
    from backports.functools_lru_cache import lru_cache  # type: ignore

_logger = logging.getLogger(__name__)
_LIBRARY_WORK = Identifier("work", case_sensitive=False)

UnresolvedLibrary = Union[Identifier, None]
LibraryUnitTuple = Tuple[UnresolvedLibrary, Identifier]


class Database(HashableByKey):  # pylint: disable=too-many-instance-attributes
    "Stores info on and provides operations for a project file set"

    def __init__(self):  # type: () -> None
        self._lock = RLock()

        self._paths = set()  # type: Set[Path]
        self._parse_timestamp = {}  # type: Dict[Path, float]
        self._library_map = {}  # type: Dict[Path, Identifier]
        self._flags_map = {}  # type: Dict[Path, Dict[BuildFlagScope, BuildFlags]]
        self._dependencies_map = {}  # type: Dict[Path, Set[BaseDependencySpec]]
        self._inferred_libraries = set()  # type: Set[Path]
        self._design_units = set()  # type: Set[tAnyDesignUnit]
        self._diags = {}  # type: Dict[Path, Set[CheckerDiagnostic]]

        # Use this to know which methods should be cache
        self._cached_methods = {
            getattr(self, x)
            for x in dir(self)
            if hasattr(getattr(self, x), "cache_clear")
        }

    @property
    def __hash_key__(self):
        # Just to allow lru_cache
        return 0

    @property
    def design_units(self):  # type: (...) -> FrozenSet[tAnyDesignUnit]
        "Set of design units found"
        return frozenset(self._design_units)

    def refresh(self):
        # type: (...) -> Any
        """
        Clears caches, inferred libraries and parses and checks if any source
        should be parsed
        """
        self._clearLruCaches()

        while self._inferred_libraries:
            try:
                del self._library_map[self._inferred_libraries.pop()]
            except KeyError:  # pragma: no cover
                pass

        for path in self.paths:
            self._parseSourceIfNeeded(path)

    def configure(self, root_config, root_path):
        # type: (Dict[str, Any], str) -> int
        """
        Handles adding sources, libraries and flags from a dict, unrolling and
        flatenning references.

        Returns the number of sources added.
        """
        cnt = 0
        for entry in flattenConfig(root_config, root_path):
            self.addSource(
                path=entry.path,
                library=entry.library,
                source_specific_flags=entry.source_specific_flags,
                single_flags=entry.single_flags,
                dependencies_flags=entry.dependencies_flags,
            )
            cnt += 1

        return cnt

    def addSource(
        self,
        path,  # type: Path
        library,  # type: Optional[str]
        source_specific_flags=None,  # type: Optional[BuildFlags]
        single_flags=None,  # type: Optional[BuildFlags]
        dependencies_flags=None,  # type: Optional[BuildFlags]
    ):
        # type: (...) -> None
        """
        Adds a source to the database, triggering its parsing even if the
        source has already been added previously
        """
        _logger.info(
            "Adding %s, library=%s, flags=(source_specific=%s, single=%s, dependencies=%s)",
            path,
            library,
            source_specific_flags,
            single_flags,
            dependencies_flags,
        )
        self._paths.add(path)
        self._flags_map[path] = {
            BuildFlagScope.source_specific: tuple(source_specific_flags or ()),
            BuildFlagScope.single: tuple(single_flags or ()),
            BuildFlagScope.dependencies: tuple(dependencies_flags or ()),
        }
        if library is not None:
            self._library_map[path] = Identifier(
                library, case_sensitive=FileType.fromPath(path) != FileType.vhdl
            )

        # TODO: Parse on a process pool
        self._parseSource(path)

    def removeSource(self, path):
        # type: (Path) -> None
        """
        Removes a path from the database. No error is raised if the path wasn't
        added previously. In this case, avoid clearning LRU caches
        """
        _logger.debug("Removing %s from database", path)
        clear_lru_caches = False

        with self._lock:
            units = frozenset(self._getDesignUnitsByPath(path))
            self._design_units -= units

            if units:
                clear_lru_caches = True

            try:
                self._paths.remove(path)
                clear_lru_caches = True
            except KeyError:
                pass

            try:
                del self._parse_timestamp[path]
                clear_lru_caches = True
            except KeyError:
                pass

            try:
                del self._library_map[path]
                clear_lru_caches = True
            except KeyError:
                pass

            try:
                del self._flags_map[path]
                clear_lru_caches = True
            except KeyError:
                pass

            try:
                del self._dependencies_map[path]
                clear_lru_caches = True
            except KeyError:
                pass

            try:
                del self._diags[path]
                clear_lru_caches = True
            except KeyError:
                pass

            if clear_lru_caches:
                self._clearLruCaches()

    def _addDiagnostic(self, diagnostic):
        # type: (CheckerDiagnostic) -> None
        """
        Adds a diagnostic to the diagnostic map. Diagnostics can then be read
        to report processing internals and might make it to the user interface
        """
        _logger.debug("Adding diagnostic %s", diagnostic)
        assert diagnostic.filename is not None

        if diagnostic.filename not in self._diags:
            self._diags[diagnostic.filename] = set()
        self._diags[diagnostic.filename].add(diagnostic)

    def getDiagnosticsForPath(self, path):
        # type: (Path) -> Iterable[CheckerDiagnostic]
        """
        Returns diagnostics generated a path. It does not trigger any
        processing or analysis though
        """
        return self._diags.get(path, ())

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = {"sources": []}

        for path in self._paths:
            source_info = {
                "path": path,
                "mtime": self._parse_timestamp[path],
                "flags": {
                    BuildFlagScope.source_specific.value: self._flags_map[path].get(
                        BuildFlagScope.source_specific, ()
                    ),
                    BuildFlagScope.single.value: self._flags_map[path].get(
                        BuildFlagScope.single, ()
                    ),
                    BuildFlagScope.dependencies.value: self._flags_map[path].get(
                        BuildFlagScope.dependencies, ()
                    ),
                },
                "dependencies": tuple(self._dependencies_map.get(path, ())),
                "diags": tuple(),
            }

            library = self._library_map.get(path, None)
            if library is not None:
                source_info["library"] = library

            state["sources"].append(source_info)

        state["inferred_libraries"] = tuple(self._inferred_libraries)
        state["design_units"] = tuple(self._design_units)

        return state

    @classmethod
    def __jsonDecode__(cls, state):
        # pylint: disable=protected-access
        obj = cls()
        obj._design_units = set(state.pop("design_units"))
        obj._inferred_libraries = set(state.pop("inferred_libraries"))
        for info in state.pop("sources"):
            path = info.pop("path")
            obj._paths.add(path)
            obj._parse_timestamp[path] = float(info.pop("mtime"))

            if "library" in info:
                obj._library_map[path] = info.pop("library")

            obj._flags_map[path] = {}
            obj._flags_map[path][BuildFlagScope.source_specific] = tuple(
                info.get("flags", {}).pop(BuildFlagScope.source_specific.value, ())
            )
            obj._flags_map[path][BuildFlagScope.single] = tuple(
                info.get("flags", {}).pop(BuildFlagScope.single.value, ())
            )
            obj._flags_map[path][BuildFlagScope.dependencies] = tuple(
                info.pop("flags", {}).pop(BuildFlagScope.dependencies.value, ())
            )
            obj._dependencies_map[path] = set(info.pop("dependencies"))
            obj._diags[path] = set(info.pop("diags"))
        # pylint: enable=protected-access

        return obj

    def getFlags(self, path, scope=None):
        # type: (Path, Optional[BuildFlagScope]) -> BuildFlags
        """
        Return a list of flags for the given path or an empty tuple if the path
        is not found in the database.
        """
        scope_flags = self._flags_map.get(path, {}).get(
            scope or BuildFlagScope.single, ()
        )

        source_specific_flags = self._flags_map.get(path, {}).get(
            BuildFlagScope.source_specific, ()
        )

        return scope_flags + source_specific_flags

    @property
    def paths(self):
        # type: () -> Iterable[Path]
        "Returns a list of paths currently in the database"
        return frozenset(self._paths)

    def _updatePathLibrary(self, path, library):
        # type: (Path, Identifier) -> None
        """
        Updates dependencies of the given path so they reflect the change in
        their owner's path
        """

        if path not in self._library_map:
            _logger.info("Setting library for '%s' to '%s'", path, library)
        else:
            current_library = self._library_map.get(path)
            # No change, avoid manipulating the database
            if current_library == library:
                return

            _logger.info(
                "Replacing old library '%s' for '%s' with '%s'",
                current_library,
                path,
                library,
            )

        self._library_map[path] = library

        # Nothing to resolve if the dependency entry is empty
        if not self._dependencies_map.get(path, None):
            return

        # Extract the unresolved dependencies that will be replaced
        unresolved_dependencies = {
            x for x in self._dependencies_map[path] if x.library is None
        }

        # RequiredDesignUnit is not mutable, so we actually need to replace the
        # objects
        for dependency in unresolved_dependencies:
            self._dependencies_map[path].add(
                RequiredDesignUnit(
                    owner=dependency.owner,
                    name=dependency.name,
                    library=library,
                    locations=dependency.locations,
                )
            )

        # Safe to remove the unresolved ones
        self._dependencies_map[path] -= unresolved_dependencies

    @lru_cache()
    def getLibrary(self, path):
        # type: (Path) -> UnresolvedLibrary
        """
        Gets the library the path is in, inferring and updating it if needed.
        Any unit that can be used from VHDL code can be bound to a library,
        even if Verilog and SystemVerilog don't have this concept.
        """
        self._parseSourceIfNeeded(path)

        if path not in self.paths:
            # Add the path to the project but put it on a different library
            self._parseSourceIfNeeded(path)
            self._updatePathLibrary(path, Identifier("not_in_project", True))
            # Report paths that are valid (that is, not temporary) when they
            # can't be found in the project file
            if not isinstance(path, TemporaryPath):
                self._addDiagnostic(PathNotInProjectFile(path))

        elif path not in self._library_map:
            # Library is not defined, try to infer
            _logger.debug("Library for '%s' not set, inferring it", path)
            library = self._inferLibraryForPath(path)
            if library is not None:
                self._updatePathLibrary(path, library)

        return self._library_map.get(path, None)

    def _parseSourceIfNeeded(self, path):
        # type: (Path) -> None
        """
        Parses a given path if needed, removing info from the database prior to that
        """
        if not isFileReadable(path.name):
            _logger.warning("Won't parse file that's not readable %s", repr(path))
            self.removeSource(path)
            return

        # Sources will get parsed on demand
        mtime = p.getmtime(path.name)

        if mtime == self._parse_timestamp.get(path, 0):
            return

        self._parseSource(path)

    def _parseSource(self, path):
        # type: (Path) -> None
        """
        Extracts info from a source, taking care of removing previously defined
        items before
        """
        _logger.debug("Parsing %s", path)

        src_parser = getSourceParserFromPath(path)
        design_units = src_parser.getDesignUnits()
        dependencies = src_parser.getDependencies()

        with self._lock:
            # Update the timestamp
            self._parse_timestamp[path] = p.getmtime(str(path))

            # Remove all design units that referred to this path before adding
            # new ones, but use the non API method for that to avoid recursing
            self._design_units -= frozenset(self._getDesignUnitsByPath(path))

            self._design_units |= design_units
            self._dependencies_map[path] = dependencies
            self._clearLruCaches()

    def _clearLruCaches(self):
        "Clear caches from lru_caches"
        for meth in self._cached_methods:
            meth.cache_clear()

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
        # type: (Path) -> FrozenSet[BaseDependencySpec]
        """
        Returns parsed dependencies for the given path
        """
        self._parseSourceIfNeeded(path)
        return frozenset(self._dependencies_map.get(path, ()))

    def getPathsByDesignUnit(self, unit):
        # type: (tAnyDesignUnit) -> Iterator[Path]
        """
        Return the source (or sources) that define the given design
        unit
        """
        return (
            design_unit.owner
            for design_unit in self.design_units
            if (unit.name, unit.type_) == (design_unit.name, design_unit.type_)
        )

    def _inferLibraryForPath(self, path):
        # type: (Path) -> UnresolvedLibrary
        """
        Tries to infer which library the given path should be compiled on by
        looking at where and how the design units it defines are used
        """
        # Find all units this path defines
        units = set(self.getDesignUnitsByPath(path))
        _logger.debug("Units defined here in %s: %s", path, list(map(str, units)))
        # Store all cases to use in case there are multiple libraries that
        # could be used. If that happens, we'll use the most common one
        all_libraries = [
            library
            for library in chain.from_iterable(
                self.getLibrariesReferredByUnit(name=unit.name) for unit in units
            )
            if library != _LIBRARY_WORK
        ]

        libraries = set(all_libraries)

        if not libraries:
            _logger.info("Couldn't work out a library for path %s", path)
            library = None
        elif len(libraries) == 1:
            library = libraries.pop()
        else:
            library = getMostCommonItem(all_libraries)

            # For now we'll report this as an issue on the dependecy. In the
            # future, we should probably store this diagnostic on a different
            # dict where the dependency is the key and put it all together when
            # the self.getDiagnosticsForPath is called (aka, cross reference on
            # demand)
            self._addDiagnostic(
                PathLibraryIsNotUnique(
                    filename=path, actual=library, choices=all_libraries
                )
            )

        self._inferred_libraries.add(path)
        return library

    @lru_cache()
    def getLibrariesReferredByUnit(self, name):
        # type: (Identifier) -> List[Identifier]
        """
        Gets libraries that the (library, name) pair is used throughout the
        project
        """
        _logger.debug("Searching for uses of %s", repr(name))

        result = []  # List[Identifier]
        for path, dependencies in self._dependencies_map.items():
            for dependency in dependencies:
                if name != dependency.name:
                    continue

                # If the dependency's library refers to 'work', it's actually
                # referring to the library its owner is in
                if dependency.library is not None:
                    result.append(dependency.library)
                else:
                    result.append(self._library_map.get(path, _LIBRARY_WORK))

        return result

    @lru_cache()
    def getPathsDefining(self, name, library=None):
        # type: (Identifier, UnresolvedLibrary) -> Iterable[Path]
        """
        Search for paths that define a given name optionally inside a library.
        """
        units = {unit for unit in self.design_units if unit.name == name}

        if not units:
            _logger.debug(
                "Could not find any source defining name=%s, library=%s", name, library
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

        # These include paths and temporary paths, which is what this method
        # should return but useless when reporting dependencies not unique.
        paths = {unit.owner for unit in units}

        _logger.debug(
            "There's %d path(s) defining %s.%s: %s", len(paths), library, name, paths
        )

        if len(paths) > 1:
            self._reportDependencyNotUnique(library=library, name=name, choices=paths)

        return paths

    def _reportDependencyNotUnique(self, library, name, choices):
        # type: (Optional[Identifier], Identifier, Iterable[Path]) -> None
        """
        Reports a dependency failed to be resolved due to multiple files
        defining the required design unit
        """
        # Filter out of choices paths that are temporary. If that reduces the
        # choices to 1 element, there's no need to report anything
        choices = {x for x in choices if not isinstance(x, TemporaryPath)}
        if len(choices) < 2:
            return

        # Reverse dependency search. Need to evaluate how this performs, but
        # we'll try to avoid creating a set to store BaseDependencySpec objects
        # for now

        for dependency in (
            dependency
            for dependency in chain.from_iterable(self._dependencies_map.values())
            if (library, name) == (dependency.library, dependency.name)
        ):

            # Fill in a report for every occurence found
            for location in dependency.locations:
                self._addDiagnostic(
                    DependencyNotUnique(
                        filename=dependency.owner,
                        line_number=location.line,
                        column_number=location.column,
                        dependency=dependency,
                        choices=choices,
                    )
                )

    def resolveIncludedPath(self, included_path):
        # type: (IncludedPath) -> Optional[Path]
        """
        Tries to resolve an include by searching for paths that end with the
        same set of strings as the included path
        """
        paths = {path for path in self.paths if path.endswith(str(included_path.name))}

        if not paths:
            _logger.warning("No path matched %s", repr(included_path))
            return None

        if len(paths) > 1:
            for location in included_path.locations:
                self._addDiagnostic(
                    DependencyNotUnique(
                        filename=included_path.owner,
                        line_number=location.line,
                        column_number=location.column,
                        dependency=included_path,
                        choices=paths,
                    )
                )

        return paths.pop()

    def getDependenciesUnits(self, path):
        # type: (Path) -> Set[LibraryUnitTuple]
        """
        Returns design units that should be compiled before compiling the given
        path but only within the project file set. If a design unit can't be
        found in any source, it will be silently ignored.
        """
        self._parseSourceIfNeeded(path)

        units = set()  # type: Set[LibraryUnitTuple]

        search_paths = set((path,))
        own_units = {
            (self.getLibrary(path), x.name) for x in self.getDesignUnitsByPath(path)
        }

        while search_paths:
            dependencies = {
                dependency
                for search_path in search_paths
                for dependency in self._dependencies_map[search_path]
                if isinstance(dependency, RequiredDesignUnit)
            }
            # Get the dependencies of the search paths and which design units
            # they define and remove the ones we've already seen
            new_deps = {
                (
                    dependency.library or self.getLibrary(dependency.owner),
                    dependency.name,
                )
                for dependency in dependencies
            } - units

            _logger.debug(
                "Searching %s resulted in dependencies: %s", search_paths, new_deps
            )

            # Add the new ones to the set tracking the dependencies seen since
            # the search started
            units |= new_deps

            # Resolve included paths to a real, searchable path
            resolved_includes = (
                self.resolveIncludedPath(dependency)
                for search_path in search_paths
                for dependency in self._dependencies_map[search_path]
                if isinstance(dependency, IncludedPath)
            )

            # Paths to be searched on the next iteration are the paths of the
            # dependencies we have not seen before, plus any included paths
            search_paths = {x for x in resolved_includes if x}

            for library, name in new_deps:
                new_paths = set(self.getPathsDefining(name=name, library=library))
                search_paths |= new_paths

            _logger.debug("Search paths: %s", search_paths)

        # Remove units defined by the path passed as argument
        units -= own_units
        return units

    @lru_cache()
    def getBuildSequence(self, path, builtin_libraries=None):
        # type: (Path, Optional[Tuple[Identifier]]) -> Iterable[Tuple[Identifier, Path]]
        """
        Gets the build sequence that satisfies the preconditions to compile the
        given path. This is the cached version of self._getBuildSequence(),
        which can't be cached because it returns an iterator.
        """
        return tuple(
            self._getBuildSequence(
                path=path, builtin_libraries=frozenset(builtin_libraries or [])
            )
        )

    def _getBuildSequence(self, path, builtin_libraries):
        # type: (Path, FrozenSet[Identifier]) -> Iterable[Tuple[Identifier, Path]]
        """
        Gets the build sequence that satisfies the preconditions to compile the
        given path
        """
        self._diags[path] = set()
        units_compiled = set()  # type: Set[LibraryUnitTuple]

        units_to_build = self.getDependenciesUnits(path)
        paths_to_build = set(
            chain.from_iterable(
                self.getPathsDefining(name=name, library=library)
                for library, name in units_to_build
                if library not in builtin_libraries
            )
        )

        # Limit the number of iterations to the worst case of every pass
        # compiling only a single source and all of them having a chain of
        # dependencies on the previous one
        iteration_limit = len(paths_to_build) + 1

        path_needs_map = (
            {}
        )  # type: Dict[Path, Set[Tuple[UnresolvedLibrary, Identifier]]]

        for i in range(iteration_limit):
            paths_built = set()  # type: Set[Path]

            for current_path in paths_to_build:
                own = {
                    (self.getLibrary(current_path), x.name)
                    for x in self.getDesignUnitsByPath(current_path)
                }

                # Filter out dependencies that are either
                # - provided by the builder
                # - on the 'use foo.all' format because this only indicates
                #   that a source needs a given library to
                #   exist (which is handled by the builder)
                # - not a required design unit (e.g, included paths)
                deps = {
                    (
                        dependency.library or self.getLibrary(dependency.owner),
                        dependency.name,
                    )
                    for dependency in self._dependencies_map[current_path]
                    if dependency.name.name != "all"
                    and isinstance(dependency, RequiredDesignUnit)
                    and dependency.library not in builtin_libraries
                }

                # Units still needed are the ones we haven't seen before
                path_needs = deps - units_compiled - own
                new_units = own - units_compiled

                path_needs_map[current_path] = path_needs

                if new_units and not path_needs:
                    _logger.debug(
                        "Compiling %s adds %d new units: %s",
                        current_path,
                        len(new_units),
                        new_units,
                    )
                    yield self.getLibrary(current_path) or DEFAULT_LIBRARY, current_path
                    paths_built.add(current_path)
                    units_compiled |= own
                elif not new_units:
                    # If the current path only defines units that have been
                    # already compiled, skip it
                    _logger.debug("Path %s has nothing to add, skipping", current_path)
                    paths_built.add(current_path)
                elif path_needs and _logger.isEnabledFor(
                    logging.DEBUG
                ):  # pragma: no cover
                    _logger.debug(
                        "%s still needs %s",
                        current_path,
                        [(library, name.name) for library, name in path_needs],
                    )

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
                    _logger.debug("Nothing more to do after %d steps", i)
                return

            _logger.debug(
                "Got %d units compiled: %s", len(units_compiled), units_compiled
            )

        _logger.error("Iteration limit of %d reached", iteration_limit)

    def getReferencesToDesignUnit(self, unit):
        # type: (Union[tAnyDesignUnit, BaseDependencySpec]) -> Iterable[BaseDependencySpec]
        """
        Returns an iterable of BaseDependencySpec objects from all paths in the
        database that refer to the given design unit. Search is done by
        matching library and name.
        """
        library = self.getLibrary(unit.owner)

        return (
            dependency
            for dependency in chain.from_iterable(self._dependencies_map.values())
            if dependency.name == unit.name and dependency.library in (library, None)
        )
