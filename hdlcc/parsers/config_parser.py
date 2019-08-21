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
"Configuration file parser"

# pylint: disable=useless-object-inheritance

import logging
import os.path as p
import re
from glob import glob
from threading import RLock
from typing import Dict, Iterator, Optional, Set

from hdlcc import exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import BuilderName
from hdlcc.utils import HashableByKey

# pylint: disable=invalid-name
_splitAtWhitespaces = re.compile(r"\s+").split
_replaceCfgComments = re.compile(r"(\s*#.*|\n)").sub
_configFileScan = re.compile("|".join([
    r"^\s*(?P<parameter>\w+)\s*(\[(?P<parm_lang>vhdl|verilog|systemverilog)\]|\s)*=\s*(?P<value>.+)\s*$",
    r"^\s*(?P<lang>(vhdl|verilog|systemverilog))\s+"  \
        r"(?P<library>\w+)\s+"                        \
        r"(?P<path>[^\s]+)\s*(?P<flags>.*)\s*",
    ]), flags=re.I).finditer
# pylint: enable=invalid-name

BuildFlagsMap = Dict[str, t.BuildFlags]

def _extractSet(entry): # type: (str) -> t.BuildFlags
    """
    Extract a list by splitting a string at whitespaces, removing
    empty values caused by leading/trailing/multiple whitespaces
    """
    string = str(entry).strip()
    # Return an empty list if the string is empty
    if not string:
        return ()
    return tuple(_splitAtWhitespaces(string))

class ProjectSourceSpec(HashableByKey):
    """Holder class to specify the interface with config parsers"""
    def __init__(self, path, library=None, flags=None):
        # type: (t.Path, Optional[t.LibraryName], Optional[t.BuildFlags]) -> None
        self._path = p.normpath(p.abspath(path))
        self._library = library
        self._flags = tuple(flags or [])

    @property
    def path(self):
        "Returns the absolute and normalized path"
        return self._path

    @property
    def library(self): # type: () -> Optional[t.LibraryName]
        "Returns parsed library name (may be None)"
        return self._library

    @property
    def flags(self): # type: () -> t.BuildFlags
        "Parsed flags or an empty list if no flags were found"
        return self._flags

    @property
    def __hash_key__(self):
        return (self.path, self.library, self.flags)

    def __repr__(self):
        return '{}(path="{}", library="{}", flags={})'.format(
            self.__class__.__name__, self.path, self.library, self.flags)

class ConfigParser(object):
    """
    Configuration info provider
    """
    _list_parms = ('single_build_flags', 'global_build_flags',)

    _single_value_parms = ('builder', )
    _deprecated_parameters = ('target_dir', )

    _logger = logging.getLogger(__name__ + ".ConfigParser")

    def __init__(self, filename): # type: (t.Path) -> None
        self._logger.debug("Creating config parser for filename '%s'", filename)

        self._parms = {'builder' : BuilderName.fallback}

        self._flags = {
            'single_build_flags' : {
                'vhdl'          : (),
                'verilog'       : (),
                'systemverilog' : (), },
            'global_build_flags' : {
                'vhdl'          : (),
                'verilog'       : (),
                'systemverilog' : (), }} # type: Dict[str, BuildFlagsMap]

        self._sources = set() # type: Set[ProjectSourceSpec]

        self.filename = t.Path(p.abspath(filename))

        self._timestamp = 0.0
        self._parse_lock = RLock()

    def _shouldParse(self): # type: () -> bool
        """
        Checks if we should parse the configuration file
        """
        return p.getmtime(self.filename) > self._timestamp

    def _updateTimestamp(self):
        """
        Updates our timestamp with the configuration file
        """
        self._timestamp = p.getmtime(self.filename)

    def isParsing(self): # type: () -> bool
        "Checks if parsing is ongoing in another thread"
        locked = not self._parse_lock.acquire(False)
        if not locked:
            self._parse_lock.release()
        return locked

    def _parseIfNeeded(self):
        """
        Locks accesses to parsed attributes and parses the configuration file
        """
        with self._parse_lock:
            if self._shouldParse():
                self._parse()

    def _parse(self): # type: () -> None
        """
        Parse the configuration file without any previous checking
        """
        self._logger.info("Parsing '%s'", self.filename)
        self._updateTimestamp()
        self._sources = set()
        for _line in open(self.filename, mode='rb').readlines():
            line = _replaceCfgComments("", _line.decode(errors='ignore'))
            self._parseLine(line)

    def _parseLine(self, line): # type: (str) -> None
        """
        Parses a line a calls the appropriate extraction methods
        """
        for match in _configFileScan(line):
            groupdict = match.groupdict()
            self._logger.debug("match: '%s'", groupdict)
            if groupdict['parameter'] is not None:
                self._handleParsedParameter(groupdict['parameter'],
                                            groupdict['parm_lang'], groupdict['value'])
            else:
                for source_path in self._getSourcePaths(groupdict['path']):
                    self._sources.add((source_path,
                                       groupdict['library'],
                                       _extractSet(groupdict['flags'])))

    def _handleParsedParameter(self, parameter, lang, value): # type: (str, str, str) -> None
        """
        Handles a parsed line that sets a parameter
        """
        self._logger.debug("Found parameter '%s' for '%s' with value '%s'",
                           parameter, lang, value)
        if parameter in self._deprecated_parameters:
            self._logger.debug("Ignoring deprecated parameter '%s'", parameter)
        elif parameter in self._single_value_parms:
            self._logger.debug("Handling '%s' as a single value", parameter)
            self._parms[parameter] = BuilderName.fromString(value)
        elif parameter in self._list_parms:
            self._logger.debug("Handling '%s' as a list of values", parameter)
            self._flags[parameter][lang] = _extractSet(value)
        else:
            raise exceptions.UnknownParameterError(parameter)

    def _getSourcePaths(self, path): # type: (t.Path) -> Iterator[t.Path]
        """
        Normalizes and handles absolute/relative paths
        """
        source_path = p.normpath(p.expanduser(path))
        # If the path to the source file was not absolute, we assume
        # it was relative to the config file base path
        if not p.isabs(source_path):
            fname_base_dir = p.dirname(p.abspath(self.filename))
            source_path = p.join(fname_base_dir, source_path)

        # Convert paths found to t.Path
        return map(t.Path, glob(source_path) or [source_path, ])

    def parse(self):
        """
        Parses the file if it hasn't been parsed before or if the config file
        has been changed
        """
        self._parseIfNeeded()
        data = self._flags.copy()
        data.update({
            'builder_name': self._parms['builder'],
            'sources': set(self._sources)})

        return data
