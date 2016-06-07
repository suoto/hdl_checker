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
"VHDL source file parser"

import re
import os
import logging
from multiprocessing import Pool

_logger = logging.getLogger(__name__)

# Design unit scanner
_DESIGN_UNIT_SCANNER = re.compile('|'.join([
    r"^\s*package\s+(?P<package_name>\w+)\s+is\b",
    r"^\s*package\s+body\s+(?P<package_body_name>\w+)\s+is\b",
    r"^\s*entity\s+(?P<entity_name>\w+)\s+is\b",
    r"^\s*library\s+(?P<library_name>[\w,\s]+)\b",
    r"^\s*context\s+(?P<context_name>\w+)\s+is\b",
    ]), flags=re.I)

class VhdlSourceFile(object):
    """Parses and stores information about a source file such as
    design units it depends on and design units it provides"""

    def __init__(self, filename, library='work', flags=None):
        _logger.info("[start] '%s'", filename)
        self.filename = os.path.normpath(filename)
        self.library = library
        if flags is None:
            self.flags = []
        else:
            self.flags = flags
        self._design_units = []
        self._deps = []
        self._mtime = 0

        self.abspath = os.path.abspath(filename)
        self._parseIfChanged()

        _logger.info("[done]  '%s'", filename)

    def getState(self):
        "Gets a dict that describes the current state of this object"
        state = {
            'filename' : self.filename,
            'abspath' : self.abspath,
            'library' : self.library,
            'flags' : self.flags,
            '_design_units' : self._design_units,
            '_deps' : self._deps,
            '_mtime' : self._mtime,
            }
        return state

    @classmethod
    def recoverFromState(cls, state):
        "Returns an object of cls based on a given state"
        # pylint: disable=protected-access
        obj = super(VhdlSourceFile, cls).__new__(cls)
        obj.filename = state['filename']
        obj.abspath = state['abspath']
        obj.library = state['library']
        obj.flags = state['flags']
        obj._design_units = state['_design_units']
        obj._deps = state['_deps']
        obj._mtime = state['_mtime']
        # pylint: enable=protected-access

        return obj

    def __repr__(self):
        return "VhdlSourceFile('%s', library='%s', flags=%s)" % \
                (self.abspath, self.library, self.flags)

    def __str__(self):
        return "[%s] %s" % (self.library, self.filename)

    def _parseIfChanged(self):
        "Parses this source file if it has changed"
        try:
            if self._changed():
                _logger.debug("Parsing %s", str(self))
                self._mtime = self.getmtime()
                self._doParse()
        except OSError: # pragma: no cover
            _logger.warning("Couldn't parse '%s' at this moment", self)

    def _changed(self):
        """Checks if the file changed based on the modification time provided
        by os.path.getmtime"""
        return self.getmtime() > self._mtime

    def _getSourceContent(self):
        """Replace everything from comment ('--') until a line break
        and converts to lowercase"""
        lines = list([re.sub(r"\s*--.*", "", x).lower() for x in \
                open(self.filename, 'r').read().split("\n")])
        return lines

    def _iterDesignUnitMatches(self):
        """Iterates over the matches of _DESIGN_UNIT_SCANNER against
        source's lines"""
        for line in self._getSourceContent():
            for match in _DESIGN_UNIT_SCANNER.finditer(line):
                yield match.groupdict()

    def _getDependencies(self, libraries):
        """Parses the source and returns a list of dictionaries that
        describe its dependencies"""
        lib_deps_regex = re.compile(r'|'.join([ \
                r"%s\.\w+" % x for x in libraries]), flags=re.I)
        dependencies = []
        for line in self._getSourceContent():
            for match in lib_deps_regex.finditer(line):
                dependency = {}
                dependency['library'], dependency['unit'] = match.group().split('.')[:2]
                # Library 'work' means 'this' library, so we replace it
                # by the library name itself
                if dependency['library'] == 'work':
                    dependency['library'] = self.library
                if dependency not in dependencies:
                    dependencies.append(dependency)

        return dependencies

    def _getParseInfo(self):
        "Parses the source file to find design units and dependencies"
        design_units = []
        libraries = ['work']

        for match in self._iterDesignUnitMatches():
            unit = None
            if match['package_name'] is not None:
                unit = {'name' : match['package_name'],
                        'type' : 'package'}
            elif match['package_body_name'] is not None:
                unit = {'name' : match['package_body_name'],
                        'type' : 'package body'}
            elif match['entity_name'] is not None:
                unit = {'name' : match['entity_name'],
                        'type' : 'entity'}
            elif match['context_name'] is not None:
                unit = {'name' : match['context_name'],
                        'type' : 'context'}
            if match['library_name'] is not None:
                libraries += re.split(r"\s*,\s*", match['library_name'])

            if unit:
                design_units.append(unit)

        return design_units, self._getDependencies(libraries)

    def _doParse(self):
        """Finds design units and dependencies then translate some design
        units into information useful in the conext of the project"""
        design_units, dependencies = self._getParseInfo()

        self._design_units = []
        for design_unit in design_units:
            if design_unit['type'] == 'package body':
                dependencies += [{'library' : self.library, 'unit': design_unit['name']}]
            else:
                self._design_units += [design_unit]

        self._deps = dependencies
        _logger.info("Source '%s' depends on: %s", str(self), \
                ", ".join(["%s.%s" % (x['library'], x['unit']) for x in self._deps]))

    def getDesignUnits(self):
        """Returns a list of dictionaries with the design units defined.
        The dict defines the name (as defined in the source file) and
        the type (package, entity, etc)"""
        self._parseIfChanged()
        return self._design_units

    def getDesignUnitsDotted(self):
        """Returns a list of dictionaries with the design units defined.
        The dict defines the name (as defined in the source file) and
        the type (package, entity, etc)"""
        return set(["%s.%s" % (self.library, x['name']) \
                    for x in self.getDesignUnits()])

    def getDependencies(self):
        """Returns a list of dictionaries with the design units this
        source file depends on. Dict defines library and unit"""
        self._parseIfChanged()
        return self._deps

    def getmtime(self):
        """Gets file modification time as defined in os.path.getmtime"""
        try:
            mtime = os.path.getmtime(self.filename)
        except OSError: # pragma: no cover
            mtime = None
        return mtime

def getSourceFileObjects(kwargs, workers=1):
    "Reads files from <fnames> list using up to <workers> threads"

    pool = Pool(workers)

    try:
        if len(kwargs) == 1:
            return [VhdlSourceFile(**kwargs[0])]
        else:
            results = [
                pool.apply_async(VhdlSourceFile, kwds=_kwargs) \
                    for _kwargs in kwargs]
            return [res.get() for res in results]
    finally:
        pool.close()
        pool.terminate()

def parseArguments(): # pragma: no cover
    "Argument parser for standalone usage"
    import argparse

    parser = argparse.ArgumentParser()

    # Options
    parser.add_argument('--verbose', '-v', action='append_const', const=1,
                        help="""Increases verbose level. Use multiple times to
                                increase more""")

    parser.add_argument('--processes', '-p', type=int, default=3,
                        help="""Maximum number of processes to be used when
                                parsing source files""")

    # Mandatory arguments
    parser.add_argument('sources', action='append', nargs='+',
                        help="List of sources to parse")

    args = parser.parse_args()

    args.log_level = logging.FATAL
    if args.verbose:
        if len(args.verbose) == 1:
            args.log_level = logging.WARNING
        elif len(args.verbose) == 2:
            args.log_level = logging.INFO
        else:
            args.log_level = logging.DEBUG

    # Planify source list if supplied
    args.sources = [source for sublist in args.sources for source in sublist]

    if args.processes:
        args.processes = min(args.processes, len(args.sources))

    return args

def standalone(): # pragma: no cover
    """Standalone run"""
    import sys
    import time
    from hdlcc.utils import setupLogging
    args = parseArguments()
    setupLogging(sys.stdout, args.log_level, color=True)

    start = time.time()
    sources = list(getSourceFileObjects(
        [{'filename' : source, 'library' : 'work'} for source in args.sources],
        workers=args.processes))
    diff = time.time() - start

    for source in sources:
        print "Source: %s" % source
        design_units = source.getDesignUnits()
        if design_units:
            print " - Design_units:"
            for unit in design_units:
                print " -- %s" % str(unit)
        dependencies = source.getDependencies()
        if dependencies:
            print " - Dependencies:"
            for dependency in dependencies:
                print " -- %s.%s" % (dependency['library'], dependency['unit'])

    _logger.info("Parsing took %.4fs", diff)

if __name__ == '__main__':
    standalone()

