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
"Configuration file parser"

import os.path as p
import re
import logging

import hdlcc.exceptions
from hdlcc.source_file import VhdlSourceFile

_RE_LEADING_AND_TRAILING_WHITESPACES = re.compile(r"^\s*|\s*$")
_RE_MULTIPLE_WHITESPACES = re.compile(r"\s+")

def _extractSet(entry):
    '''Extract a set by splitting a string at whitespaces, removing
    empty values caused by leading/trailing/multiple whitespaces'''
    _entry = _RE_LEADING_AND_TRAILING_WHITESPACES.sub("", entry)
    if _entry:
        return set(_RE_MULTIPLE_WHITESPACES.split(_entry))
    else:
        return set()

_COMMENTS = re.compile(r"(\s*#.*|\n)")
_SCANNER = re.compile("|".join([
    r"^\s*(?P<parameter>\w+)\s*=\s*(?P<value>.+)\s*$",
    r"^\s*(?P<lang>(vhdl|verilog))\s+"          \
        r"(?P<library>\w+)\s+"                  \
        r"(?P<path>[^\s]+)\s*(?P<flags>.*)\s*",
    ]), flags=re.I)

class ConfigParser(object):
    "Configuration info provider"

    _list_parms = ('batch_build_flags', 'single_build_flags',
                   'global_build_flags',)

    _single_value_parms = ('builder', 'target_dir')

    _logger = logging.getLogger(__name__ + ".ConfigParser")

    def __init__(self, filename=None):
        self._parms = {
            'batch_build_flags' : set(),
            'single_build_flags' : set(),
            'global_build_flags' : set()}

        if filename is not None:
            self.filename = p.abspath(filename)
            self._logger.info("Creating config parser for filename '%s'",
                              self.filename)
        else:
            self.filename = None
            self._parms['builder'] = 'fallback'
            self._parms['target_dir'] = '.fallback'

            self._logger.warning("No configuration file given, using dummy")


        self._sources = {}
        self._timestamp = 0

        self._parseIfNeeded()

    def __repr__(self):
        _repr = ["ConfigParser('%s'):" % self.filename]

        _repr += ["- Parameters"]
        for parameter, value in self._parms.items():
            _repr += ["    - %s = %s" % (str(parameter), str(value))]

        if self._sources:
            _repr += ["- Sources"]
            for source, attrs in self._sources.items():
                _repr += ["    - %s = %s" % (str(source), str(attrs))]

        return "\n".join(_repr)

    def _shouldParse(self):
        "Checks if we should parse the configuration file"
        if self.filename is None:
            return False
        return p.getmtime(self.filename) > self._timestamp

    def _updateTimestamp(self):
        "Updates our timestamp with the configuration file"
        self._timestamp = p.getmtime(self.filename)

    def _parseIfNeeded(self):
        "Parses the configuration file"
        if self._shouldParse():
            self._logger.debug("Parsing is required")
            self._updateTimestamp()
            for _line in open(self.filename, 'r').readlines():
                line = _COMMENTS.sub("", _line)
                self._parseLine(line)

            # If after parsing we haven't found the configured target
            # dir, we'll use the builder name
            if 'target_dir' not in self._parms.keys():
                self._parms['target_dir'] = "." + self._parms['builder']

            # If the configured target dir is not absolute, we assume it
            # should be relative to the folder where the configuration
            # file resides
            if not p.isabs(self._parms['target_dir']):
                self._parms['target_dir'] = p.join(p.dirname(self.filename),
                                                   self._parms['target_dir'])

            self._parms['target_dir'] = p.abspath(self._parms['target_dir'])

    def _parseLine(self, line):
        "Parses a line a calls the appropriate extraction methods"
        for match in [x.groupdict() for x in _SCANNER.finditer(line)]:
            if match['parameter'] is not None:
                self._handleParsedParameter(match['parameter'],
                                            match['value'])
            else:
                self._handleParsedSource(match['lang'], match['library'],
                                         match['path'], match['flags'])

    def _handleParsedParameter(self, parameter, value):
        "Handles a parsed line that sets a parameter"
        self._logger.debug("Found parameter '%s' with value '%s'",
                           parameter, value)
        if parameter in self._single_value_parms:
            self._parms[parameter] = value
        elif parameter in self._list_parms:
            self._parms[parameter] = _extractSet(value)
        else:
            raise hdlcc.exceptions.UnknownParameterError(parameter)

    # TODO: Handle sources added or removed from the configuration file
    # without deleting and recreating the objects
    def _handleParsedSource(self, language, library, path, flags):
        "Handles a parsed line that adds a source"

        self._logger.debug("Found source with path '%s', "
                           "library: '%s', language: '%s', flags: '%s'",
                           path, library, language, flags)

        if str.lower(language) != 'vhdl':
            self._logger.warning("Unsupported language: %s", language)
            return

        source_path = p.normpath(path)

        # If the path to the source file was not absolute, we assume
        # it was relative to the config file base path
        if not p.isabs(source_path):
            fname_base_dir = p.dirname(p.abspath(self.filename))
            source_path = p.join(fname_base_dir, source_path)

        flags_set = _extractSet(flags)

        self._sources[source_path] = \
                VhdlSourceFile(source_path, library, flags_set)

    def getBuilder(self):
        "Returns the builder name"
        self._parseIfNeeded()
        return self._parms['builder']

    def getTargetDir(self):
        "Returns the target folder that should be used by the builder"
        self._parseIfNeeded()
        return self._parms['target_dir']

    def getSingleBuildFlagsByPath(self, path):
        "Return a set of flags configured to build a single source"
        self._parseIfNeeded()
        if self.filename is None:
            return set()
        return self._sources[p.abspath(path)].flags | \
               self._parms['single_build_flags']  | \
               self._parms['global_build_flags']

    def getBatchBuildFlagsByPath(self, path):
        "Return a set of flags configured to build a single source"
        self._parseIfNeeded()
        if self.filename is None:
            return set()
        return self._sources[p.abspath(path)].flags | \
               self._parms['batch_build_flags']   | \
               self._parms['global_build_flags']

    def getSources(self):
        "Returns a list of VhdlSourceFile objects parsed"
        self._parseIfNeeded()
        return self._sources.values()

    def getSourcesPaths(self):
        "Returns a list of absolute paths to the sources found"
        self._parseIfNeeded()
        return self._sources.keys()

    def getSourceByPath(self, path):
        ""
        self._parseIfNeeded()
        return self._sources[p.abspath(path)]

    def hasSource(self, path):
        self._parseIfNeeded()
        if self.filename is None:
            return True
        return p.abspath(path) in self._sources.keys()



