# This file is part of HDL Code Checker.
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

import logging
import os
import os.path as p
import abc
import subprocess as subp
from threading import Lock

import hdlcc.options as options

class BaseBuilder(object): # pylint: disable=abstract-class-not-used
    "Class that implements the base builder flow"

    __metaclass__ = abc.ABCMeta

    # Set an empty container for the default flags
    default_flags = {
        'batch_build_flags' : {
            'vhdl' : [],
            'verilog' : [],
            'systemverilog' : []},
        'single_build_flags' : {
            'vhdl' : [],
            'verilog' : [],
            'systemverilog' : []},
        'global_build_flags' : {
            'vhdl' : [],
            'verilog' : [],
            'systemverilog' : []}
        }

    _external_libraries = {
        'vhdl' : [],
        'verilog' : []}

    _include_paths = {
        'vhdl' : [],
        'verilog' : []}

    @classmethod
    def addExternalLibrary(cls, lang, library_name):
        assert lang in cls._external_libraries, "Uknown language '%s'" & lang
        if library_name not in cls._external_libraries[lang]:
            cls._external_libraries[lang].append(library_name)

    @classmethod
    def addIncludePath(cls, lang, path):
        if path not in cls._include_paths[lang]:
            cls._include_paths[lang].append(path)

    @abc.abstractproperty
    def builder_name(self):
        "Defines the builder identification"

    @abc.abstractproperty
    def file_types(self):
        "Returns the file types supported by the builder"

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
            if self._builtin_libraries: # pragma: no cover
                self._logger.debug("Builtin libraries")
                for lib in self._builtin_libraries:
                    self._logger.debug("-> %s", lib)
            else: # pragma: no cover
                self._logger.info("No builtin libraries found")
        except NotImplementedError:
            pass

    @classmethod
    def recoverFromState(cls, state):
        "Returns an object of cls based on a given state"
        # pylint: disable=protected-access
        obj = super(BaseBuilder, cls).__new__(cls)
        obj._logger = logging.getLogger(state['_logger'])
        del state['_logger']
        obj._lock = Lock()
        obj.__dict__.update(state)
        # pylint: enable=protected-access

        return obj

    def getState(self):
        "Gets a dict that describes the current state of this object"
        state = self.__dict__.copy()
        state['_logger'] = self._logger.name
        del state['_lock']
        return state


    @abc.abstractmethod
    def _shouldIgnoreLine(self, line):
        """Method called for each stdout output and should return True
        if the given line should not be parsed using _makeMessageRecords
        and _getUnitsToRebuild"""

    @abc.abstractmethod
    def _makeMessageRecords(self, message):
        """Static method that converts a string into a dict that has
        elements identifying its fields"""

    def _getUnitsToRebuild(self, line):
        "Finds units that the builders is telling us to rebuild"
        raise NotImplementedError

    def _parseBuiltinLibraries(self):
        "Discovers libraries that exist regardless before we do anything"
        raise NotImplementedError

    @abc.abstractmethod
    def getBuiltinLibraries(self):
        "Return a list with the libraries this compiler currently knows"

    def _subprocessRunner(self, cmd_with_args, shell=False, env=None):
        "Runs a shell command and handles stdout catching"
        if env is not None:
            subp_env = env
        else:
            subp_env = os.environ

        self._logger.debug(" ".join(cmd_with_args))

        exc = None
        try:
            stdout = list(subp.check_output(cmd_with_args, \
                    stderr=subp.STDOUT, shell=shell, env=subp_env).splitlines())
        except subp.CalledProcessError as exc:
            stdout = list(exc.output.splitlines())
            self._logger.debug("Command '%s' failed with error code %d",
                               cmd_with_args, exc.returncode)

        # If we had an exception, print a warning to make easier to skim
        # logs for errors
        if exc is None:
            log = self._logger.debug
        else:
            log = self._logger.warning

        for line in stdout:
            if line == '' or line.isspace():
                continue
            log("> " + repr(line))

        return stdout

    @abc.abstractmethod
    def checkEnvironment(self):
        """Sanity environment check that should be implemented by child
        classes. Nothing is done with the return, the child class should
        raise an exception by itself"""

    @abc.abstractmethod
    def _buildSource(self, source, flags=None):
        """Callback called to actually build the source"""

    def _buildAndParse(self, source, flags=None):
        """Runs _buildSource method and parses the output to find message
        records and units that should be rebuilt"""
        records = []
        rebuilds = []
        exc_lines = []
        for line in self._buildSource(source, flags):
            if self._shouldIgnoreLine(line):
                continue
            for record in self._makeMessageRecords(line):
                if record['error_type'] not in ('W', 'E'): # pragma: no cover
                    exc_lines += [line]

                if record not in records:
                    records += [record]

            try:
                for rebuild in self._getUnitsToRebuild(line):
                    if rebuild not in rebuilds:
                        rebuilds += [rebuild]

            except NotImplementedError:
                pass

        if exc_lines: # pragma: no cover
            for exc_line in exc_lines:
                self._logger.error(exc_line)

        self._logBuildResults(records, rebuilds)

        return records, rebuilds

    def _logBuildResults(self, records, rebuilds): # pragma: no cover
        "Logs records and rebuilds only for debugging purposes"
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
    def _createLibrary(self, library):
        """Callback called to create a library"""

    def _isFileTypeSupported(self, source):
        "Checks if a given path is supported by this builder"
        return source.filetype in self.file_types

    def build(self, source, forced=False, flags=None):
        """Method that interfaces with parents and implements the
        building chain"""

        if not self._isFileTypeSupported(source):
            self._logger.fatal("Source '%s' with file type '%s' is not "
                               "supported", source.filename,
                               source.filetype)
            return [], []

        if source.abspath not in self._build_info_cache.keys():
            self._build_info_cache[source.abspath] = {
                'compile_time' : 0,
                'records' : [],
                'rebuilds' : [],
                }

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
                self._createLibrary(source)
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

