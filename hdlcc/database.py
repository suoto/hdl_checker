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
from itertools import chain
from tempfile import mkdtemp
from threading import RLock
from typing import (  # List,
    Any,
    Dict,
    FrozenSet,
    Generator,
    Iterable,
    Iterator,
    Optional,
    Set,
    Tuple,
)

#  from hdlcc import exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import BuilderName, getBuilderByName
from hdlcc.parsers import (  # DesignUnitType,
    ConfigParser,
    DependencySpec,
    Identifier,
    getSourceParserFromPath,
    tAnyDesignUnit,
)
from hdlcc.utils import getFileType, removeDirIfExists, samefile

_logger = logging.getLogger(__name__)

_VUNIT_FLAGS = {
    BuilderName.msim: {"93": ["-93"], "2002": ["-2002"], "2008": ["-2008"]},
    BuilderName.ghdl: {"93": ["--std=93c"], "2002": ["--std=02"], "2008": ["--std=08"]},
}


def foundVunit():  # type: () -> bool
    """
    Checks if our env has VUnit installed
    """
    try:
        import vunit  # type: ignore pylint: disable=unused-import

        return True
    except ImportError:  # pragma: no cover
        pass

    return False


class Database(object):
    __hash__ = None  # type: ignore

    def __init__(self):  # type: () -> None
        self._lock = RLock()

        self._builder_name = BuilderName.fallback
        self._paths = {}  # type: Dict[t.Path, int]
        self._libraries = {}  # type: Dict[t.Path, Identifier]
        self._flags = {}  # type: Dict[t.Path, t.BuildFlags]
        self._design_units = set()  # type: Set[tAnyDesignUnit]
        self._dependencies = {}  # type: Dict[t.Path, Set[DependencySpec]]

        self._addVunitIfFound()

    @property
    def builder_name(self):  # type: (...) -> BuilderName
        "Builder name"
        return self._builder_name

    @property
    def design_units(self):  # type: (...) -> FrozenSet[tAnyDesignUnit]
        "Set of design units found"
        return frozenset(self._design_units)

    def reset(self):
        self._builder_name = BuilderName.fallback
        self._paths = {}  # type: Dict[t.Path, int]
        self._libraries = {}  # type: Dict[t.Path, t.LibraryName]
        self._flags = {}  # type: Dict[t.Path, t.BuildFlags]
        self._design_units = set()  # type: Set[tAnyDesignUnit]
        self._dependencies = {}  # type: Dict[t.Path, Set[DependencySpec]]

        # Re-add VUnit files back again
        self._addVunitIfFound()

    def accept(self, parser):  # type: (ConfigParser) -> None
        "Updates the database from a configuration parser"
        return self.updateFromDict(parser.parse())

    def updateFromDict(self, config):  # type: (Any) -> None
        "Updates the database from a dictionary"

        self._builder_name = config.get("builder_name", self._builder_name)

        for library, path, flags in config.get("sources", []):
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

    def getFlags(self, path):  # type: (t.Path) -> t.BuildFlags
        """
        Return a list of flags for the given path or an empty tuple if the path
        is not found in the database.
        """

        return self._flags.get(path, ())

    @property
    def paths(self):  # type: () -> Iterable[t.Path]
        "Returns a list of paths currently in the database"

        return self._paths.keys()

    def getLibrary(self, path):
        # type: (t.Path) -> Optional[str]
        if path not in self._paths:
            return None
        if path not in self._libraries:
            self._libraries[path] = Identifier("work", True)
        return self._libraries[path].name

    def _parseSourceIfNeeded(self, path):
        # Sources will get parsed on demand
        mtime = p.getmtime(path)

        if mtime == self._paths.get(path, 0):
            return

        #  _logger.debug("Parsing %s (%s)", path, mtime)

        # Update the timestamp
        self._paths[path] = mtime
        # Remove all design units that referred to this path before adding new
        # ones, but use the non API method for that to avoid recursing

        if path in self._paths:
            before = len(self._design_units)
            self._design_units -= frozenset(self._getDesignUnitsByPath(path))

            if before != len(self._design_units):
                _logger.debug(
                    "Reparsing source removes %d design units",
                    before - len(self._design_units),
                )

        src_parser = getSourceParserFromPath(path)
        self._design_units |= set(src_parser.getDesignUnits())
        self._dependencies[path] = set(src_parser.getDependencies())

    def _addVunitIfFound(self):  # type: () -> None
        """
        Tries to import files to support VUnit right out of the box
        """

        if not foundVunit() or self._builder_name == BuilderName.fallback:
            return

        import vunit  # pylint: disable=import-error

        logging.getLogger("vunit").setLevel(logging.ERROR)

        _logger.info("VUnit installation found")

        builder_class = getBuilderByName(self.builder_name)

        if "systemverilog" in builder_class.file_types:
            from vunit.verilog import (  # type: ignore # pylint: disable=import-error
                VUnit,
            )

            _logger.debug("Builder supports Verilog, using vunit.verilog.VUnit")
            builder_class.addExternalLibrary("verilog", "vunit_lib")
            builder_class.addIncludePath(
                "verilog", p.join(p.dirname(vunit.__file__), "verilog", "include")
            )
        else:
            from vunit import VUnit  # pylint: disable=import-error

        output_path = t.Path(mkdtemp())
        try:
            self._importVunitFiles(VUnit, output_path)
        finally:
            removeDirIfExists(output_path)

    def _importVunitFiles(self, vunit_module, output_path):
        # type: (Any, t.Path) -> None
        """
        Runs VUnit entry point to determine which files it has and adds them to
        the project
        """

        # I'm not sure how this would work because VUnit specifies a
        # single VHDL revision for a whole project, so there can be
        # incompatibilities as this is really used
        vunit_project = vunit_module.from_argv(["--output-path", output_path])

        # OSVVM is always avilable
        vunit_project.add_osvvm()

        # Communication library and array utility library are only
        # available on VHDL 2008

        if vunit_project.vhdl_standard == "2008":
            vunit_project.add_com()
            vunit_project.add_array_util()

        # Get extra flags for building VUnit sources
        try:
            vunit_flags = _VUNIT_FLAGS[self.builder_name][vunit_project.vhdl_standard]
        except KeyError:
            vunit_flags = []

        _source_file_args = []

        for vunit_source_obj in vunit_project.get_compile_order():
            path = p.abspath(vunit_source_obj.name)
            library = vunit_source_obj.library.name

            _source_file_args.append(
                {
                    "filename": path,
                    "library": library,
                    "flags": vunit_flags if path.endswith(".vhd") else [],
                }
            )

    def getDesignUnitsByPath(self, path):  # type: (t.Path) -> Iterator[tAnyDesignUnit]
        "Gets the design units for the given path if any"
        self._parseSourceIfNeeded(path)
        return self._getDesignUnitsByPath(path)

    def _getDesignUnitsByPath(self, path):  # type: (t.Path) -> Iterator[tAnyDesignUnit]
        """
        Non public version of getDesignUnitsByPath, with the difference that
        this does not check if the path has changed or not
        """
        return (x for x in self.design_units if samefile(x.owner, path))

    def findPathsByDesignUnit(self, unit):
        # type: (tAnyDesignUnit) -> Iterator[t.Path]
        """
        Return the source (or sources) that define the given design
        unit
        """
        for design_unit in self.design_units:
            if (unit.name, unit.type_) == (design_unit.name, design_unit.type_):
                yield design_unit.owner

    def findPathsDefining(self, name, library=None):
        # type: (Identifier, Optional[Identifier]) -> Iterable[t.Path]
        """
        Search for paths that define a given name optionally inside a library.
        """
        assert isinstance(name, Identifier), "Invalid argument of type {}".format(
            type(name)
        )
        assert (
            isinstance(library, Identifier) or library is None
        ), "Invalid argument of type {}".format(type(library))

        _logger.debug("Finding paths defining %s.%s", library, name)

        units = {unit for unit in self.design_units if unit.name == name}

        _logger.debug("Units step 1: %s", units)

        if library is not None:
            units_matching_library = {
                unit for unit in units if (self._libraries.get(unit.owner) == library)
            }
            _logger.debug("Units step 2: %s", units_matching_library)

            # If no units match when using the library, it means the database
            # is incomplete and we should try to infer the library from the
            # usage of this unit
            # TODO: Actually do that....!!
            if units_matching_library:
                units = units_matching_library

        _logger.debug("Units step 3: %s", units)

        return (unit.owner for unit in units)

    def _resolveLibraryIfNeeded(self, library, name):
        # type: (Identifier, Identifier) -> Tuple[Identifier, Identifier]
        """
        Tries to resolve undefined libraries by checking usages of 'name'
        """
        if library is None:
            paths = tuple(self.findPathsDefining(name=name, library=None))
            if not paths:
                _logger.warning("Couldn't find a path definint unit %s", name)
                library = Identifier("work", False)
                assert False
            elif len(paths) == 1:
                path = paths[0]
                library = self._libraries[path]
            else:
                _logger.warning("Unit %s is defined in %d places", name, len(paths))
                library = Identifier("work", False)
                assert False
        return library, name

    def getDependenciesUnits(self, path):
        # type: (t.Path) -> Set[Tuple[Identifier, Identifier]]
        #  """
        #  Returns paths that when built will satisfy the dependencies needed by a
        #  given path. The list is not sorted by build sequence and libraries are
        #  not taken into consideration (design units defined in multiple files
        #  will appear multiple times)

        #  Dependencies not found within the project's list of files will generate
        #  a warning but will otherwise be silently ignored. IEEE and STD
        #  libraries will always be ignored
        #  """
        #  _logger.debug("Getting dependencies' units %s", path)
        units = set()  # type: Set[Tuple[Identifier, Identifier]]

        search_paths = set((path,))
        own_units = {
            (self._libraries.get(path, "work"), x.name)
            for x in self.getDesignUnitsByPath(path)
        }

        while search_paths:
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
                new_paths = set(self.findPathsDefining(name=name, library=library))
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
        # type: (t.Path) -> Generator[Tuple[t.LibraryName, t.Path], None, None]
        """
        Gets the build sequence that satisfies the preconditions to compile the
        given path
        """
        _logger.debug(
            "Getting build sequence for %s (library=%s)",
            path,
            self._libraries.get(path, "<???>"),
        )
        compiled = set()  # type: Set[str]

        units = set(self.getDependenciesUnits(path))

        _logger.debug("Units to build: %d", len(units))
        for _lib, _name in units:
            _logger.debug("- %s, %s", repr(_lib), repr(_name))

        paths = set(
            chain.from_iterable(
                self.findPathsDefining(name=name, library=library)
                for library, name in units
            )
        )

        _logger.debug("Paths to build: %d", len(paths))
        for _path in paths:
            _logger.debug("- %s", _path)

        iteration_limit = len(paths)
        # Limit the number of iterations to the worst case
        for i in range(iteration_limit):
            to_remove = set()  # type: Set[t.Path]
            for _path in paths:
                own = {x.name for x in self._getDesignUnitsByPath(_path)}
                deps = {x.name for x in self._dependencies[_path]}
                #  _logger.info("%s has %d dependencies: %s", _path, len(deps), deps)
                still_needed = deps - compiled - own
                if still_needed:
                    _logger.debug("%s still needs %s", _path, still_needed)
                else:
                    _logger.info("Can compile %s", _path)
                    yield self.getLibrary(path) or "work", _path
                    to_remove.add(_path)
                    compiled |= {x.name for x in self._getDesignUnitsByPath(_path)}

            paths -= to_remove

            _logger.debug("%d paths remaining: %s", len(units), units)

            if not to_remove:
                _logger.info("Nothing more to do after %d steps", i)
                return

            _logger.info("Got %d units compiled: %s", len(compiled), compiled)

        _logger.error("Iteration limit of %d reached", iteration_limit)
