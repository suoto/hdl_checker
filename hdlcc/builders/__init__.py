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
import abc
import time
import subprocess
from threading import Lock

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
        self._target_folder = os.path.abspath(os.path.expanduser(target_folder))

        self.builtin_libraries = []
        self._build_info_cache = {}

        try:
            os.mkdir(self._target_folder)
        except OSError: # pragma: no cover
            self._logger.info("%s already exists", self._target_folder)

        self.checkEnvironment()

    def __getstate__(self):
        state = self.__dict__.copy()
        state['_logger'] = self._logger.name
        del state['_lock']
        return state

    def __setstate__(self, state):
        self._logger = logging.getLogger(state['_logger'])
        del state['_logger']
        self._lock = Lock()
        self.__dict__.update(state)

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

    def _subprocessRunner(self, cmd_with_args):
        "Runs a shell command and handles stdout catching"
        self._logger.debug(" ".join(cmd_with_args))

        try:
            stdout = list(subprocess.check_output(cmd_with_args, \
                    stderr=subprocess.STDOUT).split("\n"))
        except subprocess.CalledProcessError as exc:
            stdout = list(exc.output.split("\n"))

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

                records += [record]

            try:
                rebuilds += self._getUnitsToRebuild(line)
            except NotImplementedError:
                pass
        if exc_lines: # pragma: no cover
            for exc_line in exc_lines:
                self._logger.critical(exc_line)
            assert 0
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
                if rebuild[0] == 'work':
                    rebuild[0] = source.library

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

from hdlcc.builders.msim import MSim
from hdlcc.builders.xvhdl import XVHDL
from hdlcc.builders.fallback import Fallback
from hdlcc.builders.ghdl import GHDL

__all__ = ['MSim', 'XVHDL', 'Fallback', 'GHDL']

AVAILABLE_BUILDERS = MSim, XVHDL, Fallback, GHDL

