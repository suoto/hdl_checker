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

import logging
import os.path as p
import re
from glob import glob
from threading import RLock
from typing import Any, Dict, Generator, KeysView, List, Set

from hdlcc import exceptions
from hdlcc import types as t  # pylint: disable=unused-import
from hdlcc.builders import AVAILABLE_BUILDERS, Fallback, getBuilderByName
from hdlcc.parsers import getSourceFileObjects

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

def _extractSet(entry): # type: (str) -> List[str]
    """
    Extract a list by splitting a string at whitespaces, removing
    empty values caused by leading/trailing/multiple whitespaces
    """
    entry = str(entry).strip()
    if not entry:
        return []

    return [value for value in _splitAtWhitespaces(entry)]

BuildFlagsMap = Dict[str, List[str]]

class ConfigParser(object):  # pylint: disable=useless-object-inheritance
    """
    Configuration info provider
    """
    __hash__ = None # type: ignore

    _list_parms = ('batch_build_flags', 'single_build_flags',
                   'global_build_flags',)

    _single_value_parms = ('builder', )
    _deprecated_parameters = ('target_dir', )

    _logger = logging.getLogger(__name__ + ".ConfigParser")

    def __init__(self, filename=None): # type: (t.OptionalPath) -> None
        self._parms = {'builder' : 'fallback'}

        self._flags = {
            'batch_build_flags' : {
                'vhdl'          : [],
                'verilog'       : [],
                'systemverilog' : [], },
            'single_build_flags' : {
                'vhdl'          : [],
                'verilog'       : [],
                'systemverilog' : [], },
            'global_build_flags' : {
                'vhdl'          : [],
                'verilog'       : [],
                'systemverilog' : [], }} # type: Dict[str, BuildFlagsMap]

        self.filename = filename

        if filename is not None:
            self.filename = p.abspath(filename)
            self._logger.debug("Creating config parser for filename '%s'",
                               self.filename)
        else:
            self._logger.info("No configuration file given, using fallback")

        self._sources = {} # type: Dict[t.Path, t.SourceFile]
        self._timestamp = 0.0
        self._parse_lock = RLock()

    def __eq__(self, other): # pragma: no cover
        if not isinstance(other, type(self)):
            return False

        for attr in ('_parms', '_flags', '_list_parms', '_single_value_parms',
                     '_sources', 'filename'):
            if not hasattr(other, attr):
                return False
            if getattr(self, attr) != getattr(other, attr):
                return False

        return True

    def __ne__(self, other): # pragma: no cover
        return not self.__eq__(other)

    def __repr__(self):
        _repr = ["ConfigParser('%s'):" % self.filename]

        _repr += ["- Parameters"]
        for parameter, value in self._parms.items():
            _repr += ["    - %s = %s" % (str(parameter), str(value))]

        _repr += ["- Flags"]
        for parameter, value in self._flags.items():
            _repr += ["    - %s = %s" % (str(parameter), str(value))]

        if self._sources:
            _repr += ["- Sources"]
            for source, attrs in self._sources.items():
                _repr += ["    - %s = %s" % (str(source), str(attrs))]

        return "\n".join(_repr)

    def __jsonEncode__(self): # type: () -> t.ObjectState
        """
        Gets a dict that describes the current state of this object
        """
        self._parseIfNeeded()

        return {
            'filename': self.filename,
            '_timestamp': self._timestamp,
            '_sources': self._sources.copy(),
            '_parms': {
                'builder': self._parms['builder'],
            },
            '_flags': {
                'batch_build_flags' : {
                    'vhdl'          : list(self._flags['batch_build_flags']['vhdl']),
                    'verilog'       : list(self._flags['batch_build_flags']['verilog']),
                    'systemverilog' : list(self._flags['batch_build_flags']['systemverilog'])},
                'single_build_flags' : {
                    'vhdl'          : list(self._flags['single_build_flags']['vhdl']),
                    'verilog'       : list(self._flags['single_build_flags']['verilog']),
                    'systemverilog' : list(self._flags['single_build_flags']['systemverilog'])},
                'global_build_flags' : {
                    'vhdl'          : list(self._flags['global_build_flags']['vhdl']),
                    'verilog'       : list(self._flags['global_build_flags']['verilog']),
                    'systemverilog' : list(self._flags['global_build_flags']['systemverilog'])
                }
            }
        }

    @classmethod
    def __jsonDecode__(cls, state): # type: (t.ObjectState) -> None
        """
        Returns an object of cls based on a given state
        """
        obj = super(ConfigParser, cls).__new__(cls)

        # pylint: disable=protected-access
        sources = state.pop('_sources')
        obj.filename = state.pop('filename', None)
        obj._timestamp = state.pop('_timestamp')
        obj._parse_lock = RLock()

        obj._flags = state['_flags']
        obj._flags['batch_build_flags'] = state['_flags']['batch_build_flags']
        obj._flags['single_build_flags'] = state['_flags']['single_build_flags']
        obj._flags['global_build_flags'] = state['_flags']['global_build_flags']

        obj._parms = state['_parms']
        obj._sources = sources

        # pylint: enable=protected-access

        return obj

    def _shouldParse(self): # type: () -> bool
        """
        Checks if we should parse the configuration file
        """
        if self.filename is None:
            return False
        return p.getmtime(self.filename) > self._timestamp

    def _updateTimestamp(self):
        """
        Updates our timestamp with the configuration file
        """
        if self.filename is not None:
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
                self._doParseConfigFile()

    def _doParseConfigFile(self): # type: () -> None
        """
        Parse the configuration file without any previous checking
        """
        self._logger.info("Parsing '%s'", self.filename)
        self._updateTimestamp()
        parsed_info = [] # type: List[t.BuildInfo]
        if self.filename is not None:
            for _line in open(self.filename, mode='rb').readlines():
                line = _replaceCfgComments("", _line.decode(errors='ignore'))
                parsed_info += list(self._parseLine(line))

        self._cleanUpSourcesList([x['filename'] for x in parsed_info if self._shouldAddSource(x)])

        # At this point we have a list of sources parsed from the config
        # file and the info we need to build each one.
        self._logger.info("Adding %d sources", len(parsed_info))
        for source in getSourceFileObjects(parsed_info):
            self._sources[source.filename] = source

        # If no builder was configured, try to discover one that works
        if self._parms['builder'] == 'fallback':
            self._discoverBuilder()

        # Set default flags if the user hasn't specified any
        self._setDefaultBuildFlagsIfNeeded()

    def _discoverBuilder(self):
        """
        If no builder was specified, try to find one that works using
        a dummy target dir
        """
        builder_class = None
        self._logger.debug("Searching for builder among %s",
                           AVAILABLE_BUILDERS)
        for builder_class in AVAILABLE_BUILDERS:
            if builder_class is Fallback:
                continue
            if builder_class.isAvailable():
                self._logger.info("Builder '%s' has worked",
                                  builder_class.builder_name)
                self._parms['builder'] = builder_class.builder_name
                return

        self._parms['builder'] = Fallback.builder_name

    # TODO: Add a test for this
    def _setDefaultBuildFlagsIfNeeded(self):
        """
        Tries to get a default set of flags if none were specified
        """
        if self.getBuilderName() == 'fallback':
            return

        builder_class = getBuilderByName(self.getBuilderName())

        # If the global/batch/single flags list is not set, overwrite
        # with the values given by the builder class
        for context in builder_class.default_flags:
            for lang in builder_class.default_flags[context]:
                if not self._flags[context][lang]:
                    self._logger.debug(
                        "Flag '%s' for '%s' wasn't set, using the default "
                        "value from '%s' class: '%s'", context, lang,
                        builder_class.builder_name,
                        builder_class.default_flags[context][lang])
                    self._flags[context][lang] = builder_class.default_flags[context][lang]
                else:
                    self._logger.debug(
                        "Flag '%s' for '%s' was already set with value '%s'",
                        context, lang, self._flags[context][lang])

    def _cleanUpSourcesList(self, sources): # type: (List[t.Path]) -> None
        """
        Removes sources we had found earlier and leave only the ones
        whose path are found in the 'sources' argument
        """
        files_to_remove = set() # type: Set[t.Path]
        for path in self._sources:
            if path not in sources:
                self._logger.warning("Removing '%s' because it has been removed "
                                     "from the config file", path)
                files_to_remove.add(path)

        for rm_path in files_to_remove:
            del self._sources[rm_path]

    def _parseLine(self, line): # type: (str) -> Generator[t.BuildInfo, None, None]
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

                    yield {'filename' : source_path,
                           'library' : groupdict['library'],
                           'flags' : _extractSet(groupdict['flags'])}

    def _handleParsedParameter(self, parameter, lang, value): # type: (str, str, str) -> None
        """
        Handles a parsed line that sets a parameter
        """
        self._logger.debug("Found parameter '%s' for '%s' with value '%s'",
                           parameter, lang, value)
        if parameter in self._deprecated_parameters:
            self._logger.debug("Ignoring deprecated parameter '%s'", parameter)
        elif parameter in self._single_value_parms:
            self._logger.debug("Handling parameter '%s' as a single value",
                               parameter)
            self._parms[parameter] = value
        elif parameter in self._list_parms:
            self._logger.debug("Handling parameter '%s' as a list of values",
                               parameter)
            self._flags[parameter][lang] = _extractSet(value)
        else:
            raise exceptions.UnknownParameterError(parameter)

    def _getSourcePaths(self, path): # type: (t.Path) -> List[t.Path]
        """
        Normalizes and handles absolute/relative paths
        """
        source_path = p.normpath(p.expanduser(path))
        # If the path to the source file was not absolute, we assume
        # it was relative to the config file base path
        if not p.isabs(source_path) and self.filename is not None:
            fname_base_dir = p.dirname(p.abspath(self.filename))
            source_path = p.join(fname_base_dir, source_path)

        return [t.Path(x) for x in glob(source_path)] or [t.Path(source_path)]

    def _shouldAddSource(self, build_info): # type: (t.BuildInfo) -> bool
        """
        Checks if the source with the given parameters should be
        created/updated
        """
        source_path = build_info['filename']
        library = build_info['library']
        flags = build_info['flags']
        # If the path can't be found, just add it
        if build_info['filename'] not in self._sources:
            return True

        source = self._sources[source_path]

        # If the path already exists, check that other parameters are
        # the same. Should there be any difference, we'll need to update
        # the object
        if source.library != library or source.flags != flags:
            return True

        return False

    def getBuilderName(self): # type: () -> str
        """
        Returns the builder name
        """
        self._parseIfNeeded()
        return self._parms['builder']

    def getPaths(self): # type: () -> KeysView[t.Path]
        return self._sources.keys()

    def getSources(self): # type: () -> List[t.SourceFile]
        """
        Returns a list of VhdlParser/VerilogParser objects parsed
        """
        self._parseIfNeeded()
        return list(self._sources.values())

    def getSourceByPath(self, path): # type: (t.Path) -> t.SourceFile
        """
        Returns a source object given its path
        """
        self._parseIfNeeded()
        return self._sources[t.Path(p.abspath(path))]
