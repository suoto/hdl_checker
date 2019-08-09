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

import os
import os.path as p
import abc
import logging
from threading import Lock

from hdlcc.exceptions import SanityCheckError
from hdlcc.diagnostics import DiagType

class BaseBuilder(object):  # pylint: disable=useless-object-inheritance
    """
    Class that implements the base builder flow
    """

    __metaclass__ = abc.ABCMeta

    # Set an empty container for the default flags
    default_flags = {
        'batch_build_flags' : {},
        'single_build_flags' : {},
        'global_build_flags' : {}} # type: dict

    _external_libraries = {
        'vhdl' : [],
        'verilog' : []}  # type: dict

    _include_paths = {
        'vhdl' : [],
        'verilog' : []}  # type: dict

    @classmethod
    def addExternalLibrary(cls, lang, library_name):
        """
        Adds an external library so it may be referenced by the builder
        directly
        """
        assert lang in cls._external_libraries, "Uknown language '%s'" & lang
        if library_name not in cls._external_libraries[lang]:
            cls._external_libraries[lang].append(library_name)

    @classmethod
    def addIncludePath(cls, lang, path):
        """
        Adds an include path to be used by the builder where applicable
        """
        if path not in cls._include_paths[lang]:
            cls._include_paths[lang].append(path)

    @abc.abstractproperty
    def builder_name(self):
        """
        Defines the builder identification
        """

    @abc.abstractproperty
    def file_types(self):
        """
        Returns the file types supported by the builder
        """

    def __init__(self, target_folder):
        # Shell accesses must be atomic
        self._lock = Lock()

        self._logger = logging.getLogger(__package__ + '.' + self.builder_name)
        self._target_folder = p.abspath(p.expanduser(target_folder))
        self._build_info_cache = {}
        self._builtin_libraries = set()
        self._added_libraries = set()

        # Skip creating a folder for the fallback builder
        if self.builder_name != 'fallback':
            if not p.exists(self._target_folder):
                self._logger.info("Target folder '%s' was created", self._target_folder)
                os.makedirs(self._target_folder)
            else:
                self._logger.info("%s already exists", self._target_folder)

        self.checkEnvironment()

        try:
            self._parseBuiltinLibraries()
            if self._logger.isEnabledFor(logging.DEBUG):  # pragma: no cover
                if self._builtin_libraries: # pragma: no cover
                    self._logger.debug("Builtin libraries: %s",
                                       ', '.join(self._builtin_libraries))
                else: # pragma: no cover
                    self._logger.info("No builtin libraries found")
        except NotImplementedError:
            pass

    @classmethod
    def __jsonDecode__(cls, state):
        """
        Returns an object of cls based on a given state
        """
        # pylint: disable=protected-access
        obj = super(BaseBuilder, cls).__new__(cls)
        obj._logger = logging.getLogger(state.pop('_logger'))
        obj._builtin_libraries = set(state.pop('_builtin_libraries'))
        obj._added_libraries = set(state.pop('_added_libraries'))

        obj._lock = Lock()
        obj._build_info_cache = {}
        obj.__dict__.update(state)
        # pylint: enable=protected-access

        return obj

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = self.__dict__.copy()
        state['_logger'] = self._logger.name
        state['_builtin_libraries'] = list(self._builtin_libraries)
        state['_added_libraries'] = list(self._added_libraries)
        del state['_build_info_cache']
        del state['_lock']
        return state

    @staticmethod
    def isAvailable():  # pragma: no cover
        """
        Method that should be overriden by child classes and return True
        if the given builder is available on the current environment
        """
        raise NotImplementedError

    def checkEnvironment(self):
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

    def _getRebuilds(self, source, line):
        """
        Gets info on what should be rebuilt to satisfy the builder
        """
        try:
            parse_results = self._searchForRebuilds(line)
        except NotImplementedError:  # pragma: no cover
            return []

        rebuilds = []
        for rebuild in parse_results:
            unit_type = rebuild.get('unit_type', None)
            library_name = rebuild.get('library_name', None)
            unit_name = rebuild.get('unit_name', None)
            rebuild_path = rebuild.get('rebuild_path', None)

            rebuild_info = None
            if None not in (unit_type, unit_name):
                for dependency in source.getDependencies():
                    if dependency.name == rebuild['unit_name']:
                        rebuild_info = {'unit_type' : unit_type,
                                        'unit_name' : unit_name}
                        break
            elif None not in (library_name, unit_name):
                rebuild_info = {'library_name' : library_name,
                                'unit_name' : unit_name}
            elif rebuild_path is not None:
                # GHDL sometimes gives the full path of the file that
                # should be recompiled
                rebuild_info = {'rebuild_path' : rebuild_path}
            else:  # pragma: no cover
                self._logger.warning("Don't know what to do with %s",
                                     rebuild)

            if rebuild_info is not None and rebuild_info not in rebuilds:
                rebuilds.append(rebuild_info)

        return rebuilds

    def _searchForRebuilds(self, line): # pragma: no cover
        """
        Finds units that the builders is telling us to rebuild
        """
        raise NotImplementedError

    def _parseBuiltinLibraries(self):
        """
        Discovers libraries that exist regardless before we do anything
        """
        raise NotImplementedError

    @abc.abstractmethod
    def getBuiltinLibraries(self):
        """
        Return a list with the libraries this compiler currently knows
        """

    @abc.abstractmethod
    def _checkEnvironment(self):
        """
        Sanity environment check that should be implemented by child
        classes. Nothing is done with the return, the child class should
        raise an exception by itself
        """

    @abc.abstractmethod
    def _buildSource(self, path, library, flags=None):
        """
        Callback called to actually build the source
        """

    def _buildAndParse(self, source, flags=None):
        """
        Runs _buildSource method and parses the output to find message
        records and units that should be rebuilt
        """
        for lib in source.getLibraries():
            if lib not in self.getBuiltinLibraries():
                self._createLibrary(lib)

        diagnostics = set()
        rebuilds = []

        for line in self._buildSource(source.filename, source.library, flags):
            if self._shouldIgnoreLine(line):
                continue

            # In case we're compiling a temporary dump, replace in the lines
            # all references to the temp name with the original (shadow)
            # filename
            if source.shadow_filename:
                line = line.replace(source.filename, source.shadow_filename)

            diagnostics = diagnostics.union(set(self._makeRecords(line)))
            rebuilds += [x for x in self._getRebuilds(source, line) if x not in
                         rebuilds]

        # If no filename is set, assume it's for the current path
        for diag in diagnostics:
            if diag.filename is None:
                diag.filename = source.filename

        self._logBuildResults(diagnostics, rebuilds)

        return diagnostics, rebuilds

    def _logBuildResults(self, diagnostics, rebuilds): # pragma: no cover
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

    @abc.abstractmethod
    def _createLibrary(self, library):
        """
        Callback called to create a library
        """

    def _isFileTypeSupported(self, source):
        """
        Checks if a given path is supported by this builder
        """
        return source.filetype in self.file_types

    def build(self, source, forced=False, flags=None):
        """
        Method that interfaces with parents and implements the building
        chain
        """

        if not self._isFileTypeSupported(source):
            self._logger.fatal("Source '%s' with file type '%s' is not "
                               "supported", source.filename,
                               source.filetype)
            return [], []

        if source.abspath not in self._build_info_cache:
            self._build_info_cache[source.abspath] = {
                'compile_time' : 0,
                'diagnostics' : [],
                'rebuilds' : []}

        cached_info = self._build_info_cache[source.abspath]

        build = False
        if forced:
            build = True
            self._logger.info("Forcing build of %s", str(source))
        elif source.getmtime() > cached_info['compile_time']:
            build = True
            self._logger.info("Building %s", str(source))

        if build:
            if flags is None:
                flags = []
            # Build a list of flags and pass it as tuple
            build_flags = source.flags + flags
            with self._lock:
                diagnostics, rebuilds = \
                        self._buildAndParse(source, flags=tuple(build_flags))

            for rebuild in rebuilds:
                if 'library_name' in rebuild:
                    if rebuild['library_name'] == 'work':
                        rebuild['library_name'] = source.library

            cached_info['diagnostics'] = diagnostics
            cached_info['rebuilds'] = rebuilds
            cached_info['compile_time'] = source.getmtime()

            if DiagType.ERROR in [x.severity for x in diagnostics]:
                cached_info['compile_time'] = 0

        else:
            self._logger.debug("Nothing to do for %s", source)
            diagnostics = cached_info['diagnostics']
            rebuilds = cached_info['rebuilds']

        return diagnostics, rebuilds
