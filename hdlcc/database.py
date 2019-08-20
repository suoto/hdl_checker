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
from tempfile import mkdtemp
from threading import RLock
from typing import Any, Dict, FrozenSet, Iterable, Iterator, Set

#  from hdlcc import exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import BuilderName, getBuilderByName
from hdlcc.design_unit import DesignUnit
from hdlcc.parsers import (ConfigParser, DependencySpec, SourceFile,
                           getSourceFileObjects, getSourceParserFromPath)
from hdlcc.utils import removeDirIfExists, samefile

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
        # Clear up previous definitions
        #  self.reset()

        config = parser.parse()
        #  _logger.debug("Updating from\n%s", pprint.pformat(config))

        self._builder_name = config.get('builder_name', self._builder_name)

        self._addVunitIfFound()

        for source in config.get('sources', []):
            #  _logger.debug('Adding %s', source)
            path = source.path
            # Default when updating is set the modification time to zero
            # because we're cleaning up the parsed info too
            self._paths[path] = 0
            self._libraries[path] = source.library
            self._flags[path] = source.flags
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

        _logger.debug("Parsing %s (%s)", path, mtime)

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
        self._design_units = self._design_units.union(src_parser.getDesignUnits())
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
        Returns a list of paths that satisfy all the dependencies of the given
        path.
        """
        _logger.warning("Searching inside %s", path)
        deps = set() # type: Set[DependencySpec]
        all_paths = set() # type: Set[t.Path]

        search_paths = set((path, ))

        while search_paths:
            deps_found = set() # type: Set[DependencySpec]

            # Get the dependencies of the search paths and which design units
            # they define

            for search_path in search_paths:
                _logger.debug("Searching %s", search_path)
                deps_found = deps_found.union(self._dependencies[search_path])

            # Remove the ones we've already seen and add the new ones to the
            # set tracking the dependencies seen since the search started
            deps_found -= deps
            deps = deps.union(deps_found)

            # Paths to be searched on the next iteration are the paths of the
            # dependencies we have not seen before
            search_paths = set()

            for dependency in deps_found:
                search_paths = search_paths.union(
                    self.findPathsByDesignUnit(dependency.name,
                                               dependency.case_sensitive))

            all_paths = all_paths.union(search_paths)

        # Return what we've found excluding the initial path
        return all_paths - {path}


def main(): # type: ignore #
    import sys
    from hdlcc.utils import setupLogging
    setupLogging(sys.stdout, logging.INFO, True)
    _logger = logging.getLogger(__name__)
    import time
    database = Database()
    start = time.time()
    database.accept(ConfigParser('/home/souto/dev/grlib/vimhdl.prj'))
    end = time.time()
    setup = end - start

    start = time.time()
    deps = database.getDependenciesPaths('/home/souto/dev/grlib/designs/leon3-xilinx-kc705/leon3mp.vhd')
    end = time.time()

    dep_search = end - start

    _logger.info("Got %d deps", len(deps))
    lines = 0

    for dep in sorted(deps):
        _logger.info("- %s", dep)
        lines += open(dep, 'r').read().count('\n')

    print("Took %.2fs and %.2fs" % (setup, dep_search))
    print("Processed %d lines" % lines)

if __name__ == '__main__':
    main()
