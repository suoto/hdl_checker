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
import time
import subprocess as subp
from threading import Lock

import hdlcc.exceptions
from hdlcc.config import Config

class BaseBuilder(object):
    "Class that implements the base builder flow"

    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def __builder_name__(self):
        "Defines the builder identification"

    def __init__(self, target_folder):
        # Shell accesses must be atomic
        self._lock = Lock()

        self._logger = logging.getLogger(__name__ + '.' + self.__builder_name__)
        self._target_folder = p.abspath(p.expanduser(target_folder))
        self._build_info_cache = {}
        self._builtin_libraries = []

        if not p.exists(self._target_folder):
            self._logger.info("Target folder '%s' was created", self._target_folder)
            os.mkdir(self._target_folder)
        else:
            self._logger.info("%s already exists", self._target_folder)

        self.checkEnvironment()

        try:
            self._parseBuiltinLibraries()
            if self._builtin_libraries: # pragma: no-cover
                self._logger.info("Builtin libraries")
                for lib in self._builtin_libraries:
                    self._logger.info("-> %s", lib)
            else: # pragma: no-cover
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

        try:
            stdout = list(subp.check_output(cmd_with_args, \
                    stderr=subp.STDOUT, shell=shell, env=subp_env).splitlines())
        except subp.CalledProcessError as exc:
            stdout = list(exc.output.splitlines())
            import traceback
            self._logger.debug("Command '%s' failed with error code %d",
                               cmd_with_args, exc.returncode)

            for line in traceback.format_exc().split('\n'): # pragma: no-cover
                self._logger.debug(line)

            # We'll check if the return code means a command not found.
            # In this case, we'll print the configured PATH for debugging
            # purposes
            if (os.name == 'posix' and exc.returncode == 127) or \
               (os.name == 'nt' and exc.returncode == 9009): # pragma: no-cover
                self._logger.debug("subprocess runner path:")
                for path in subp_env['PATH'].split(os.pathsep):
                    self._logger.debug(" - %s", path)
                self._logger.debug("subprocess runner path:")
                for path in subp_env['PATH'].split(os.pathsep):
                    self._logger.debug(" - %s", path)

        for line in stdout:
            if line == '' or line.isspace():
                continue
            self._logger.debug("> " + repr(line))

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
        return records, rebuilds

    @abc.abstractmethod
    def _createLibrary(self, library):
        """Callback called to create a library"""

    def build(self, source, forced=False, flags=None):
        """Method that interfaces with parents and implements the
        building chain"""

        start = time.time()
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
            self._logger.info("Building %s because it's out of date", \
                    str(source))

        if build:
            if flags is None:
                flags = []
            # Build a set of unique flags and pass it as tuple
            build_flags = set()
            build_flags.update(source.flags)
            build_flags.update(flags)
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

            if not Config.cache_error_messages and \
                    'E' in [x['error_type'] for x in records]:
                cached_info['compile_time'] = 0

            end = time.time()
            self._logger.debug("Compilation took %.2fs", (end - start))
        else:
            self._logger.debug("Nothing to do for %s", source)
            records = cached_info['records']
            rebuilds = cached_info['rebuilds']

        return records, rebuilds

