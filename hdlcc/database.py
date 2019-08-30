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
#  from itertools import chain
from tempfile import mkdtemp
from threading import RLock
from typing import (Any, Dict, FrozenSet, Generator, Iterable, Iterator, List,
                    Set, Tuple)

#  from hdlcc import exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import BuilderName, getBuilderByName
from hdlcc.design_unit import DesignUnit, DesignUnitType
from hdlcc.parsers import (ConfigParser, DependencySpec, SourceFile,
                           getSourceFileObjects, getSourceParserFromPath)
from hdlcc.utils import removeDirIfExists, removeDuplicates, samefile

_logger = logging.getLogger(__name__)

_VUNIT_FLAGS = {
    BuilderName.msim : {
        '93'   : ['-93'],
        '2002' : ['-2002'],
        '2008' : ['-2008']},
    BuilderName.ghdl : {
        '93'   : ['--std=93c'],
        '2002' : ['--std=02'],
        '2008' : ['--std=08']},
    }

def foundVunit(): # type: () -> bool
    """
    Checks if our env has VUnit installed
    """
    try:
        import vunit  # type: ignore pylint: disable=unused-import

        return True
    except ImportError: # pragma: no cover
        pass

    return False


class Database(object):
    __hash__ = None # type: ignore

    def __init__(self): # type: () -> None
        self._lock = RLock()

        self._builder_name = BuilderName.fallback
        self._paths = {} # type: Dict[t.Path, int]
        self._libraries = {} # type: Dict[t.Path, t.LibraryName]
        self._flags = {} # type: Dict[t.Path, t.BuildFlags]
        self._design_units = set() # type: Set[DesignUnit]
        self._dependencies = {} # type: Dict[t.Path, Set[DependencySpec]]
        self._sources = {} # type: Dict[t.Path, SourceFile]

        self._addVunitIfFound()

    @property
    def builder_name(self): # type: (...) -> BuilderName
        "Builder name"
        return self._builder_name

    @property
    def design_units(self): # type: (...) -> FrozenSet[DesignUnit]
        "Set of design units found"
        return frozenset(self._design_units)

    def reset(self):
        self._paths = {}
        self._libraries = {}
        self._flags = {}
        self._design_units = set()
        self._dependencies = {}
        self._sources = {}

        # Re-add VUnit files back again
        self._addVunitIfFound()

    def accept(self, parser):  # type: (ConfigParser) -> None
        "Updates the database from a configuration parser"
        return self.updateFromDict(parser.parse())

    def updateFromDict(self, config):  # type: (Any) -> None
        "Updates the database from a dictionary"

        self._builder_name = config.get('builder_name', self._builder_name)

        for library, path, flags in config.get('sources', []):
            # Default when updating is set the modification time to zero
            # because we're cleaning up the parsed info too
            self._paths[path] = 0
            self._libraries[path] = library
            self._flags[path] = tuple(flags)
            # TODO: Parse on a process pool
            self._parseSourceIfNeeded(path)

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = {}

        for path in self._paths:
            state[path] = {
                'library': self._libraries[path],
                'flags': self._flags[path],
                'design_units': tuple(self._design_units),
                'dependencies': self._dependencies[path]}

        return state

    def getFlags(self, path): # type: (t.Path) -> t.BuildFlags
        """
        Return a list of flags for the given path or an empty tuple if the path
        is not found in the database.
        """

        return self._flags.get(path, ())

    @property
    def paths(self): # type: () -> Iterable[t.Path]
        "Returns a list of paths currently in the database"

        return self._paths.keys()

    def getLibrary(self, path):
        return self._libraries.get(path, None)

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
                _logger.debug("Reparsing source removes %d design units",
                              before - len(self._design_units))

        src_parser = getSourceParserFromPath(path)
        self._design_units |= set(src_parser.getDesignUnits())
        self._dependencies[path] = set(src_parser.getDependencies())

    def _addVunitIfFound(self): # type: () -> None
        """
        Tries to import files to support VUnit right out of the box
        """

        if not foundVunit() or self._builder_name == BuilderName.fallback:
            return

        import vunit  # pylint: disable=import-error
        logging.getLogger('vunit').setLevel(logging.ERROR)

        _logger.info("VUnit installation found")

        builder_class = getBuilderByName(self.builder_name)

        if 'systemverilog' in builder_class.file_types:
            from vunit.verilog import VUnit    # type: ignore # pylint: disable=import-error
            _logger.debug("Builder supports Verilog, using vunit.verilog.VUnit")
            builder_class.addExternalLibrary('verilog', 'vunit_lib')
            builder_class.addIncludePath(
                'verilog', p.join(p.dirname(vunit.__file__), 'verilog',
                                  'include'))
        else:
            from vunit import VUnit  # pylint: disable=import-error

        output_path = t.Path(mkdtemp()) # type: t.Path
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
        vunit_project = vunit_module.from_argv(['--output-path', output_path])

        # OSVVM is always avilable
        vunit_project.add_osvvm()

        # Communication library and array utility library are only
        # available on VHDL 2008

        if vunit_project.vhdl_standard == '2008':
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
                {'filename' : path,
                 'library' : library,
                 'flags' : vunit_flags if path.endswith('.vhd') else []})

        for source in getSourceFileObjects(_source_file_args):
            self._sources[source.filename] = source

    def getDesignUnitsByPath(self, path): # type: (t.Path) -> Iterator[DesignUnit]
        "Gets the design units for the given path if any"
        self._parseSourceIfNeeded(path)

        return self._getDesignUnitsByPath(path)

    def _getDesignUnitsByPath(self, path): # type: (t.Path) -> Iterator[DesignUnit]
        """
        Non public version of getDesignUnitsByPath, with the difference that
        this does not check if the path has changed or not
        """
        return filter(lambda x: samefile(x.owner, path), self._design_units)

    def findPathsByDesignUnit(self, unit, case_sensitive=False):
        # type: (t.UnitName, bool) -> Iterator[t.Path]
        """
        Return the source (or sources) that define the given design
        unit. Case sensitive mode should be used when tracking
        dependencies on Verilog files. VHDL should use VHDL
        """
        cmp_name = unit if case_sensitive else unit.lower()

        if case_sensitive:
            return map(lambda x: x.owner,
                       filter(lambda x: x.name == cmp_name,
                              self.design_units))

        return map(lambda x: x.owner,
                   filter(lambda x: x.name.lower() == cmp_name,
                          self.design_units))


    def getDependenciesPaths(self, path):
        # type: (t.Path) -> Set[t.Path]
        """
        Returns paths that when built will satisfy the dependencies needed by a
        given path. The list is not sorted by build sequence and libraries are
        not taken into consideration (design units defined in multiple files
        will appear multiple times)

        Dependencies not found within the project's list of files will generate
        a warning but will otherwise be silently ignored. IEEE and STD
        libraries will always be ignored
        """
        _logger.warning("Searching inside %s", path)
        all_deps = set() # type: Set[DependencySpec]
        dependencies_paths = set() # type: Set[t.Path]

        search_paths = set((path, ))

        while search_paths:
            deps_found = set() # type: Set[DependencySpec]

            # Get the dependencies of the search paths and which design units
            # they define
            for search_path in search_paths:
                _logger.debug("Path %s dependencies: %s", search_path, deps_found)
                deps_found |= self._dependencies[search_path]

            # Remove the ones we've already seen and add the new ones to the
            # set tracking the dependencies seen since the search started
            deps_found -= all_deps
            all_deps |= deps_found

            # Paths to be searched on the next iteration are the paths of the
            # dependencies we have not seen before
            search_paths = set()

            for dependency in deps_found:
                new_paths = set(self.findPathsByDesignUnit(dependency.name,
                                                           dependency.case_sensitive))
                if not new_paths:
                    _logger.warning("Couldn't find where %s is defined", dependency)

                search_paths |= new_paths

            # Union of both sets
            dependencies_paths |= search_paths

        # List now has a list where the first dependency is at the bottom, so
        # reverse it and make sure we don't return paths more than once. Also
        # remote the request path, since we're supposed to only list
        # dependencies
        return dependencies_paths - {path}

    def getBuildSequence(self, path):
        # type: (t.Path) -> Generator[Tuple[t.LibraryName, t.Path], None, None]
        """
        Gets the build sequence that satisfies the preconditions to compile the
        given path
        """
        units_compiled = set() # type: Set[str]

        deps_paths = list(self.getDependenciesPaths(path))

        resolved_paths = {x for x in deps_paths if self._libraries.get(x, None) is not None}

        deps_paths = list(set(deps_paths) - resolved_paths)
        deps_paths.sort(key=lambda x: len(self._dependencies[x]))

        _logger.info("Got %d resolved paths", len(resolved_paths))
        #  for rp in resolved_paths:
        #      _logger.info("[%s] %s", self._libraries.get(rp), rp)

        for i in range(10):
            to_remove = set() # type: Set[t.Path]
            for dep_path in deps_paths:
                own = {x.name for x in self._getDesignUnitsByPath(dep_path)}
                deps = {x.name for x in self._dependencies[dep_path]}
                #  _logger.info("%s has %d dependencies: %s", dep_path, len(deps), deps)
                still_needed = deps - units_compiled - own
                if still_needed:
                    _logger.debug("%s still needs %s", dep_path, still_needed)
                else:
                    _logger.info("Can compile %s", dep_path)
                    yield 'work', dep_path
                    to_remove.add(dep_path)
                    units_compiled |= {x.name for x in self._getDesignUnitsByPath(dep_path)}

            deps_paths = list(set(deps_paths) - to_remove)
            deps_paths.sort(key=lambda x: len(self._dependencies[x]))

            _logger.debug("%d paths remaining: %s", len(deps_paths), deps_paths)
            _logger.info("Got %d units compiled: %s", len(units_compiled),
                         units_compiled)

            if not to_remove:
                _logger.warning("Nothing more to do after %d steps", i)
                break
