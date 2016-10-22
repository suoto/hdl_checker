# This file is part of HDL Code Checker.
#
# Copyright (c) 2016 Andre Souto
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
import subprocess as subp
from threading import Lock

import hdlcc.options as options
from hdlcc.exceptions import SanityCheckError

class BaseBuilder(object):
    """
    Class that implements the base builder flow
    """

    __metaclass__ = abc.ABCMeta

    # Set an empty container for the default flags
    default_flags = {
        'batch_build_flags' : {},
        'single_build_flags' : {},
        'global_build_flags' : {}}

    _external_libraries = {
        'vhdl' : [],
        'verilog' : []}

    _include_paths = {
        'vhdl' : [],
        'verilog' : []}

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
        self._builtin_libraries = []
        self._added_libraries = []

        # Skip creating a folder for the fallback builder
        if self.builder_name != 'fallback':
            if not p.exists(self._target_folder):
                self._logger.info("Target folder '%s' was created", self._target_folder)
                os.mkdir(self._target_folder)
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
    def recoverFromState(cls, state):
        """
        Returns an object of cls based on a given state
        """
        # pylint: disable=protected-access
        obj = super(BaseBuilder, cls).__new__(cls)
        obj._logger = logging.getLogger(state['_logger'])
        del state['_logger']
        obj._lock = Lock()
        obj.__dict__.update(state)
        # pylint: enable=protected-access

        return obj

    def getState(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = self.__dict__.copy()
        state['_logger'] = self._logger.name
        del state['_lock']
        return state

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
    def _makeRecords(self, message):
        """
        Static method that converts a string into a dict that has
        elements identifying its fields
        """

    def _getRebuilds(self, source, line):
        """
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
                    if dependency['unit'] == rebuild['unit_name']:
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

    def _subprocessRunner(self, cmd_with_args, shell=False, env=None):
        """
        Runs a shell command and handles stdout catching
        """
        if env is not None: # pragma: no cover
            subp_env = env
        else:
            subp_env = os.environ

        self._logger.debug(" ".join(cmd_with_args))

        exc = None
        try:
            stdout = list(
                subp.check_output(cmd_with_args, stderr=subp.STDOUT,
                                  shell=shell, env=subp_env).splitlines())
        except subp.CalledProcessError as exc:
            stdout = list(exc.output.splitlines())
            self._logger.debug("Command '%s' failed with error code %d",
                               cmd_with_args, exc.returncode)

        return [x.decode() for x in stdout]

    @abc.abstractmethod
    def _checkEnvironment(self):
        """
        Sanity environment check that should be implemented by child
        classes. Nothing is done with the return, the child class should
        raise an exception by itself
        """

    @abc.abstractmethod
    def _buildSource(self, source, flags=None):
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

        records = []
        rebuilds = []
        for line in self._buildSource(source, flags):
            if self._shouldIgnoreLine(line):
                continue

            records += [x for x in self._makeRecords(line) if x not in records]
            rebuilds += [x for x in self._getRebuilds(source, line) if x not in
                         rebuilds]

        self._logBuildResults(records, rebuilds)

        return records, rebuilds

    def _logBuildResults(self, records, rebuilds): # pragma: no cover
        """
        Logs records and rebuilds only for debugging purposes
        """
        if not self._logger.isEnabledFor(logging.DEBUG):
            return

        if records:
            self._logger.debug("Records found")
            for record in records:
                self._logger.debug(record)

        if rebuilds:
            self._logger.debug("Rebuilds found")
            for rebuild in rebuilds:
                self._logger.debug(rebuild)

    @abc.abstractmethod
    def _createLibrary(self, source):
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

        if source.abspath not in self._build_info_cache.keys():
            self._build_info_cache[source.abspath] = {
                'compile_time' : 0,
                'records' : [],
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
                records, rebuilds = \
                        self._buildAndParse(source, flags=tuple(build_flags))

            for rebuild in rebuilds:
                if 'library_name' in rebuild:
                    if rebuild['library_name'] == 'work':
                        rebuild['library_name'] = source.library

            cached_info['records'] = records
            cached_info['rebuilds'] = rebuilds
            cached_info['compile_time'] = source.getmtime()

            if not options.cache_error_messages and \
                    'E' in [x['error_type'] for x in records]:
                cached_info['compile_time'] = 0

        else:
            self._logger.debug("Nothing to do for %s", source)
            records = cached_info['records']
            rebuilds = cached_info['rebuilds']

        return records, rebuilds

