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
"Configuration file parser"

import os.path as p
import shutil
import re
import logging
from threading import Lock

import hdlcc.exceptions
from hdlcc.parsers import (getSourceFileObjects,
                           VhdlParser,
                           VerilogParser)
from hdlcc.builders import getBuilderByName, AVAILABLE_BUILDERS

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

def _extractSet(entry):
    """
    Extract a list by splitting a string at whitespaces, removing
    empty values caused by leading/trailing/multiple whitespaces
    """
    entry = str(entry).strip()
    if not entry:
        return []

    return [value for value in _splitAtWhitespaces(entry)]

def foundVunit():
    """
    Checks if our env has VUnit installed
    """
    try:
        import vunit  # pylint: disable=unused-variable
        result = True
    except ImportError: # pragma: no cover
        result = False
    return result

_VUNIT_FLAGS = {
    'msim' : {
        '93'   : ['-93'],
        '2002' : ['-2002'],
        '2008' : ['-2008']},
    'ghdl' : {
        '93'   : ['--std=93c'],
        '2002' : ['--std=02'],
        '2008' : ['--std=08']}
    }

class ConfigParser(object):
    """
    Configuration info provider
    """

    _list_parms = ('batch_build_flags', 'single_build_flags',
                   'global_build_flags',)

    _single_value_parms = ('builder', 'target_dir')

    _logger = logging.getLogger(__name__ + ".ConfigParser")

    def __init__(self, filename=None):
        self._parms = {
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
                'systemverilog' : [], }}

        if filename is not None:
            self.filename = p.abspath(filename)
            self._logger.debug("Creating config parser for filename '%s'",
                               self.filename)
        else:
            self.filename = None
            self._parms['builder'] = 'fallback'
            self._parms['target_dir'] = '.fallback'

            self._logger.info("No configuration file given, using dummy")

        self._sources = {}
        self._timestamp = 0
        self._lock = Lock()

    def __eq__(self, other): # pragma: no cover
        if not isinstance(other, type(self)):
            return False

        for attr in ('_parms', '_list_parms', '_single_value_parms',
                     '_sources', 'filename'):
            if not hasattr(other, attr):
                return False
            if getattr(self, attr) != getattr(other, attr):
                return False

        return True

    def __ne__(self, other): # pragma: no cover
        return not self.__eq__(other)

    def _addVunitIfFound(self):
        """
        Tries to import files to support VUnit right out of the box
        """
        if not foundVunit() or self._parms['builder'] == 'fallback':
            return

        import vunit

        self._logger.info("VUnit installation found")
        #  logging.getLogger('vunit').setLevel(logging.ERROR)

        builder_class = getBuilderByName(self.getBuilder())

        if 'systemverilog' in builder_class.file_types:
            from vunit.verilog import VUnit
            self._logger.debug("Builder supports Verilog, "
                               "using vunit.verilog.VUnit")
            builder_class.addExternalLibrary('verilog', 'vunit_lib')
            builder_class.addIncludePath(
                'verilog', p.join(p.dirname(vunit.__file__), 'verilog',
                                  'include'))
            self._importVunitFiles(VUnit)

        from vunit import VUnit
        self._importVunitFiles(VUnit)

    def _importVunitFiles(self, vunit_module):
        """
        Imports VUnit sources from a VUnit module
        """

        # I'm not sure how this would work because VUnit specifies a
        # single VHDL revision for a whole project, so there can be
        # incompatibilities as this is really used
        vunit_project = vunit_module.from_argv(
            ['--output-path', p.join(self._parms['target_dir'], 'vunit')])

        # OSVVM is always avilable
        vunit_project.add_osvvm()

        # Communication library and array utility library are only
        # available on VHDL 2008
        if vunit_project.vhdl_standard == '2008':
            for func in (vunit_project.add_com,
                         vunit_project.add_array_util):
                try:
                    func()
                except: # pragma: no cover pylint:disable=bare-except
                    self._logger.exception("Error running '%s'", str(func))
                    raise

        # Get extra flags for building VUnit sources
        if self.getBuilder() in _VUNIT_FLAGS:
            vunit_flags = _VUNIT_FLAGS[self.getBuilder()][vunit_project.vhdl_standard]
        else:
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

    def getState(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = {}
        state['filename'] = self.filename
        state['_timestamp'] = self._timestamp

        state['_parms'] = self._parms.copy()

        for context in ('batch_build_flags', 'single_build_flags',
                        'global_build_flags'):
            for lang in ('vhdl', 'verilog', 'systemverilog'):
                state['_parms'][context][lang] = list(self._parms[context][lang])

        state['_sources'] = {}
        for path, source in self._sources.items():
            state['_sources'][path] = source.getState()

        return state

    @classmethod
    def recoverFromState(cls, state):
        """
        Returns an object of cls based on a given state
        """
        obj = super(ConfigParser, cls).__new__(cls)

        # pylint: disable=protected-access
        sources = state.pop('_sources')
        obj.filename = state.pop('filename', None)
        obj._timestamp = state.pop('_timestamp')
        obj._lock = Lock()

        obj._parms = state['_parms']
        obj._parms['batch_build_flags'] = state['_parms']['batch_build_flags']
        obj._parms['single_build_flags'] = state['_parms']['single_build_flags']
        obj._parms['global_build_flags'] = state['_parms']['global_build_flags']

        obj._sources = {}
        for path, src_state in sources.items():
            if src_state['filetype'] == 'vhdl':
                obj._sources[path] = VhdlParser.recoverFromState(src_state)
            else:
                obj._sources[path] = VerilogParser.recoverFromState(src_state)

        # pylint: enable=protected-access

        return obj

    def _shouldParse(self):
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
        self._timestamp = p.getmtime(self.filename)

    def _parseIfNeeded(self):
        """
        Parses the configuration file
        """
        if self._shouldParse():
            with self._lock:
                self._doParseConfigFile()
                self._addVunitIfFound()

    def _doParseConfigFile(self):
        """
        Parse the configuration file without any previous checking
        """
        self._logger.info("Parsing '%s'", self.filename)
        self._updateTimestamp()
        source_path_list = []
        source_build_list = []
        for _line in open(self.filename, mode='rb').readlines():
            line = _replaceCfgComments("", _line.decode(errors='ignore'))
            line_source_list, line_build_list = self._parseLine(line)
            source_path_list += line_source_list
            source_build_list += line_build_list

        # At this point we have a list of sources parsed from the config
        # file and the info we need to build each one. We'll use a pool
        # to speed up parsing (important especially for libraries with
        # many files. The multiprocessing.Pool class used to hang, so
        # watch out if this behaves well enough to be used
        for source in getSourceFileObjects(source_build_list):
            self._logger.debug("Adding source %s", source)
            self._sources[source.filename] = source

        self._cleanUpSourcesList(source_path_list)

        # If no builder was configured, try to discover
        if 'builder' not in self._parms.keys():
            self._discoverBuilder()

        # Set default flags if the user hasn't specified any
        self._setDefaultBuildFlagsIfNeeded()

        # If after parsing we haven't found the configured target
        # dir, we'll use '.hdlcc' as default
        if 'target_dir' not in self._parms.keys():
            self._parms['target_dir'] = ".hdlcc"

        # If the configured target folder is not absolute, we assume it
        # should be relative to the folder where the configuration file
        # resides
        if not p.isabs(self._parms['target_dir']):
            self._parms['target_dir'] = p.join(p.dirname(self.filename),
                                               self._parms['target_dir'])

        self._parms['target_dir'] = p.abspath(self._parms['target_dir'])

    def _discoverBuilder(self):
        """
        If no builder was specified, try to find one that works using
        a dummy target dir
        """
        target_dir = '.dummy'
        builder_class = None
        self._logger.debug("Searching for builder among %s",
                           AVAILABLE_BUILDERS)
        for builder_class in AVAILABLE_BUILDERS:
            if builder_class.builder_name == 'fallback':
                continue
            try:
                builder_class(target_dir)
                break
            except hdlcc.exceptions.SanityCheckError:
                self._logger.debug("Builder '%s' failed",
                                   builder_class.builder_name)
                continue
            finally:
                if p.exists(target_dir): # pragma: no cover
                    shutil.rmtree(target_dir)

        if builder_class is not None:
            self._logger.info("Builder '%s' has worked",
                              builder_class.builder_name)
            self._parms['builder'] = builder_class.builder_name
        else: # pragma: no cover
            # Fallback is tested in the list above, so we shouldn't
            # reach this
            self._logger.info("Couldn't find any builder, using fallback")
            self._parms['builder'] = 'fallback'

    # TODO: Add a test for this
    def _setDefaultBuildFlagsIfNeeded(self):
        """
        Tries to get a default set of flags if none were specified
        """
        if self.getBuilder() == 'fallback':
            return

        builder_class = getBuilderByName(self.getBuilder())

        # If the global/batch/single flags list is not set, overwrite
        # with the values given by the builder class
        for context in builder_class.default_flags:
            for lang in builder_class.default_flags[context]:
                if not self._parms[context][lang]:
                    self._logger.debug(
                        "Flag '%s' for '%s' wasn't set, using the default "
                        "value from '%s' class: '%s'", context, lang,
                        builder_class.builder_name,
                        builder_class.default_flags[context][lang])
                    self._parms[context][lang] = builder_class.default_flags[context][lang]
                else:
                    self._logger.debug(
                        "Flag '%s' for '%s' was already set with value '%s'",
                        context, lang, self._parms[context][lang])

    def _cleanUpSourcesList(self, sources):
        """
        Removes sources we had found earlier and leave only the ones
        whose path are found in the 'sources' argument
        """

        rm_list = []
        for path in self._sources:
            if path not in sources:
                self._logger.warning("Removing '%s' because it has been removed "
                                     "from the config file", path)
                rm_list += [path]

        for rm_path in rm_list:
            del self._sources[rm_path]

    def _parseLine(self, line):
        """
        Parses a line a calls the appropriate extraction methods
        """
        source_path_list = []
        source_build_list = []

        for match in [x.groupdict() for x in _configFileScan(line)]:
            if match['parameter'] is not None:
                self._logger.info("match: '%s'", match)
                self._handleParsedParameter(match['parameter'],
                                            match['parm_lang'], match['value'])
            else:
                source_path = self._getSourcePath(match['path'])
                source_path_list += [source_path]
                # Try to get the build info for this source. If we get nothing
                # we just skip it
                build_info = self._handleParsedSource(
                    match['library'], source_path, match['flags'])
                if build_info:
                    source_build_list.append(build_info)

        return source_path_list, source_build_list

    def _handleParsedParameter(self, parameter, lang, value):
        """
        Handles a parsed line that sets a parameter
        """
        self._logger.debug("Found parameter '%s' for '%s' with value '%s'",
                           parameter, lang, value)
        if parameter in self._single_value_parms:
            self._logger.debug("Handling parameter '%s' as a single value",
                               parameter)
            self._parms[parameter] = value
        elif parameter in self._list_parms:
            self._logger.debug("Handling parameter '%s' as a list of values",
                               parameter)
            self._parms[parameter][lang] = _extractSet(value)
        else:
            raise hdlcc.exceptions.UnknownParameterError(parameter)

    def _getSourcePath(self, path):
        """
        Normalizes and handles absolute/relative paths
        """
        source_path = p.normpath(p.expanduser(path))
        # If the path to the source file was not absolute, we assume
        # it was relative to the config file base path
        if not p.isabs(source_path):
            fname_base_dir = p.dirname(p.abspath(self.filename))
            source_path = p.join(fname_base_dir, source_path)

        return source_path

    def _handleParsedSource(self, library, path, flags):
        """
        Handles a parsed line that adds a source
        """
        flags_set = _extractSet(flags)

        # If the source should be built, return the build info for it
        if self._shouldAddSource(path, library, flags_set):
            self._logger.debug("Adding source: lib '%s', '%s'", library, path)
            return {'filename' : path, 'library' : library, 'flags' : flags_set}

    def _shouldAddSource(self, source_path, library, flags):
        """
        Checks if the source with the given parameters should be
        created/updated
        """
        # If the path can't be found, just add it
        if source_path not in self._sources:
            return  True

        source = self._sources[source_path]

        # If the path already exists, check that other parameters are
        # the same. Should there be any difference, we'll need to update
        # the object
        if source.library != library or source.flags != flags:
            return True
        return False

    def getBuilder(self):
        """
        Returns the builder name
        """
        self._parseIfNeeded()
        return self._parms['builder']

    @staticmethod
    def simpleParse(filename):
        """
        """
        assert p.exists(filename), "Filename '%s' doesn't exists" % filename
        target_dir = None
        builder_name = None
        for _line in open(filename, mode='rb').readlines():
            line = _replaceCfgComments("", _line.decode(errors='ignore'))
            for match in re.finditer(
                    r"^\s*target_dir\s*=\s*(?P<target_dir>.+)\s*$"
                    r"|"
                    r"^\s*builder\s*=\s*(?P<builder>.+)\s*$",
                    line):
                match_dict = match.groupdict()
                if match_dict['target_dir'] is not None:
                    target_dir = match_dict['target_dir']
                if match_dict['builder'] is not None:
                    builder_name = match_dict['builder']

        if target_dir:
            target_dir = p.abspath(p.join(p.dirname(filename), target_dir))
        else:
            target_dir = '.hdlcc'

        if not p.isabs(target_dir):
            target_dir = p.join(p.dirname(filename), target_dir)

        ConfigParser._logger.info("Simple parse found target_dir = %s and "
                                  "builder = %s", repr(target_dir),
                                  repr(builder_name))
        return target_dir, builder_name

    def getTargetDir(self):
        """
        Returns the target folder that should be used by the builder
        """
        self._parseIfNeeded()
        return self._parms['target_dir']

    def getBuildFlags(self, path, batch_mode):
        """
        Return a list of flags configured to build a source in batch or
        single mode
        """
        self._parseIfNeeded()
        if self.filename is None:
            return []
        lang = self.getSourceByPath(path).filetype
        flags = list(self._parms['global_build_flags'][lang])

        if batch_mode:
            flags += self._parms['batch_build_flags'][lang]
        else:
            flags += self._parms['single_build_flags'][lang]

        if not self.hasSource(path):
            return flags

        return flags + self._sources[p.abspath(path)].flags

    def getSources(self):
        """
        Returns a list of VhdlParser/VerilogParser objects parsed
        """
        self._parseIfNeeded()
        return list(self._sources.values())

    def getSourceByPath(self, path):
        """
        Returns a source object given its path
        """
        self._parseIfNeeded()
        return self._sources[p.abspath(path)]

    def hasSource(self, path):
        """
        Checks if a given path exists in the configuration file
        """
        self._parseIfNeeded()
        if self.filename is None:
            return True
        return p.abspath(path) in self._sources.keys()

    def findSourcesByDesignUnit(self, unit, library='work'):
        sources = []
        for source in self._sources.values():
            if source.library == library and unit in [x['name'] for x in
                                                      source.getDesignUnits()]:
                sources += [source]
        if not sources:
            self._logger.warning("No source file defining '%s.%s'",
                                 library, unit)
        return sources

    def discoverSourceDependencies(self, unit, library):
        """
        Searches for sources that implement the given design unit. If
        more than one file implements an entity or package with the same
        name, there is no guarantee that the right one was picked
        """
        return self.findSourcesByDesignUnit(unit, library)

