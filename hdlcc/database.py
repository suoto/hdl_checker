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
import pprint
from tempfile import mkdtemp
from threading import RLock
from typing import Any, Dict, FrozenSet, Iterable, List, Set, Tuple

#  from hdlcc import exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import BuilderName, getBuilderByName
from hdlcc.design_unit import DesignUnit
from hdlcc.parsers import (ConfigParser, DependencySpec, SourceFile,
                           getSourceFileObjects, getSourceParserFromPath)
from hdlcc.utils import removeDirIfExists

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
        self._design_units = {} # type: Dict[t.Path, Set[DesignUnit]]
        self._dependencies = {} # type: Dict[t.Path, Set[DependencySpec]]
        self._sources = {} # type: Dict[t.Path, SourceFile]

        self._addVunitIfFound()

    @property
    def builder_name(self): # type: (...) -> BuilderName
        return self._builder_name

    def _clean(self):
        self._paths = {}
        self._libraries = {}
        self._flags = {}
        self._design_units = {}
        self._dependencies = {}
        self._sources = {}
        #  self._design_units[path] = set(source.getDesignUnits())
        #  self._dependencies[path] = set(source.getDependencies())

        # Re-add VUnit files back again
        self._addVunitIfFound()

    def accept(self, parser):  # type: (ConfigParser) -> None
        # Clear up previous definitions
        self._clean()

        config = parser.parse()
        _logger.debug("Updating from\n%s", pprint.pformat(config))

        self._builder_name = config.get('builder_name', self._builder_name)

        for source in config.get('sources', []):
            _logger.debug('Adding %s', source)
            path = source.path
            # Default when updating is set the modification time to zero
            # because we're cleaning up the parsed info too
            self._paths[path] = 0
            self._libraries[path] = source.library
            self._flags[path] = source.flags


        #  for path in parser.getPaths():
        #      _logger.debug("Adding %s", path)
        #      self._paths.add(path)
        #      source = parser.getSourceByPath(path)
        #      self._sources[path] = source
        #      self._libraries[path] = source.library
        #      self._flags[path] = list(source.flags)

        #      self._design_units[path] = set(source.getDesignUnits())
        #      self._dependencies[path] = set(source.getDependencies())

        self._addVunitIfFound()

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = {}
        for path in self._paths:
            state[path] = {
                'library': self._libraries[path],
                'flags': self._flags[path],
                'design_units': self._design_units[path],
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

    def _parsePathIfNeeded(self, path):
        # Sources will get parsed on demand
        if p.getmtime(path) <= self._paths.get(path, 0):
            return

        _logger.debug("Parsing '%s'", path)
        source = getSourceParserFromPath(path)
        self._design_units[path] = set(source.getDesignUnits())
        self._dependencies[path] = set(source.getDependencies())

    def getDesignUnits(self, path):
        self._parsePathIfNeeded(path)
        return self._design_units.get(path, set())

    def getKnownDesignUnits(self):
        pass


    def findSourcesByDesignUnit(self, unit, library='work',
                                case_sensitive=False):
        # type: (t.UnitName, t.LibraryName, bool) -> List[SourceFile]
        """
        Return the source (or sources) that define the given design
        unit. Case sensitive mode should be used when tracking
        dependencies on Verilog files. VHDL should use VHDL
        """

        # Default to lower case if we're not handling case sensitive. VHDL
        # source files are all converted to lower case when parsed, so the
        # units they define are in lower case already
        library_name = library if case_sensitive else library.lower()
        unit_name = unit if case_sensitive else unit.lower()

        sources = [] # type: List[SourceFile]

        for source in self._sources.values():
            source_library = source.library
            design_unit_names = map(lambda x: x['name'],
                                    source.getDesignUnits())
            if not case_sensitive:
                source_library = source_library.lower()
                design_unit_names = map(lambda x: x.lower(), design_unit_names)

            #  if source_library == library_name and unit_name in design_unit_names:
            if unit_name in design_unit_names:
                sources += [source]

        if not sources:
            _logger.warning("No source file defining '%s.%s'",
                            library, unit)
        return sources

    def discoverSourceDependencies(self, unit, library, case_sensitive):
        # type: (t.UnitName, t.LibraryName, bool) -> List[Tuple[SourceFile, t.LibraryName]]
        """
        Searches for sources that implement the given design unit. If
        more than one file implements an entity or package with the same
        name, there is no guarantee that the right one is selected
        """

        # Default to lower case if we're not handling case sensitive. VHDL
        # source files are all converted to lower case when parsed, so the
        # units they define are in lower case already
        library_name = library if case_sensitive else library.lower()
        unit_name = unit if case_sensitive else unit.lower()

        sources = [] # type: List[Tuple[SourceFile, t.LibraryName]]

        for source in self._sources.values():
            source_library = source.library
            design_unit_names = map(lambda x: x['name'],
                                    source.getDesignUnits())
            if not case_sensitive:
                source_library = source_library.lower()
                design_unit_names = map(lambda x: x.lower(), design_unit_names)

            #  if source_library == library_name and unit_name in design_unit_names:
            if unit_name in design_unit_names:
                sources += [(source, library_name)]

        if not sources:
            _logger.warning("No source file defining '%s.%s'",
                            library, unit)
        return sources

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
            from vunit.verilog import VUnit    # type: ignore pylint: disable=import-error
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
