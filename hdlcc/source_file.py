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

import re
import os
import logging
import threading

_logger = logging.getLogger(__name__)

_MAX_OPEN_FILES = 100

# Regexes

# Test the names found for a sanity check
_RE_VALID_NAME_CHECK = re.compile(r"^[a-z]\w*$", flags=re.I)

# Design unit scanner
_DESIGN_UNIT_SCANNER = re.compile('|'.join([
    r"^\s*package\s+(?P<package_name>\w+)\s+is\b",
    r"^\s*package\s+body\s+(?P<package_body_name>\w+)\s+is\b",
    r"^\s*entity\s+(?P<entity_name>\w+)\s+is\b",
    r"^\s*library\s+(?P<library_name>[\w,\s]+)\b",
    ]), flags=re.I)

class VhdlSourceFile(object):
    """Parses and stores information about a source file such as
    design units it depends on and design units it provides"""

    # Use a semaphore to avoid opening too many files (Python raises
    # an exception for this)
    _semaphore = threading.BoundedSemaphore(_MAX_OPEN_FILES)

    def __init__(self, filename, library='work'):
        self.filename = os.path.normpath(filename)
        self.library = library
        self.flags = set()
        self._design_units = []
        self._deps = []
        self._mtime = 0

        self.abspath = os.path.abspath(filename)
        self._lock = threading.Lock()
        # XXX: If the file is busy (i.e., the user has recently saved
        # the file, parsing will fail because it won't be able to open
        # or stat the file
        threading.Thread(target=self._parseIfChanged).start()

    def __getstate__(self):
        state = self.__dict__.copy()
        del state['_lock']
        return state

    def __setstate__(self, state):
        self.__dict__.update(state)
        self._lock = threading.Lock()

    def __repr__(self):
        return "VhdlSourceFile('%s', library='%s')" % \
                (self.abspath, self.library)

    def __str__(self):
        return "[%s] %s" % (self.library, self.filename)

    def _parseIfChanged(self):
        "Parses this source file if it has changed"
        if self._lock.locked():
            unlocked_request = False
        else:
            unlocked_request = True
            self._lock.acquire()
        try:
            if self.changed():
                _logger.debug("Parsing %s", str(self))
                self._mtime = self.getmtime()
                self._doParse()
        except OSError: # pragma: no cover
            _logger.warning("Couldn't parse '%s' at this moment", self)
        finally:
            if unlocked_request:
                self._lock.release()

    # XXX: If the file is busy (i.e., the user has recently saved
    # the file, parsing will fail because it won't be able to open
    # or stat the file
    def changed(self):
        """Checks if the file changed based on the modification time provided
        by os.path.getmtime"""
        return self.getmtime() > self._mtime

    def _doParse(self):
        "Parses the source file to find design units and dependencies"

        # Replace everything from comment ('--') until a line break and
        # converts to lowercase
        VhdlSourceFile._semaphore.acquire()
        lines = list([re.sub(r"\s*--.*", "", x).lower() for x in \
                open(self.filename, 'r').read().split("\n")])
        VhdlSourceFile._semaphore.release()

        design_units = []
        libraries = ['work']

        for line in lines:
            scan = _DESIGN_UNIT_SCANNER.scanner(line)
            while True:
                match = scan.match()
                if not match:
                    break

                match_dict = match.groupdict()

                unit = None
                if match_dict['package_name'] is not None:
                    unit = {'name' : match_dict['package_name'],
                            'type' : 'package'}
                elif match_dict['package_body_name'] is not None:
                    unit = {'name' : match_dict['package_body_name'],
                            'type' : 'package body'}
                elif match_dict['entity_name'] is not None:
                    unit = {'name' : match_dict['entity_name'],
                            'type' : 'entity'}
                elif match_dict['library_name'] is not None:
                    libraries += re.split(r"\s*,\s*", match_dict['library_name'])

                if unit:
                    design_units.append(unit)

        lib_deps_regex = re.compile(r'|'.join([ \
                r"%s\.\w+" % x for x in libraries]), flags=re.I)

        dependencies = []
        for line in lines:
            for match in lib_deps_regex.finditer(line):
                dependency = {}
                dependency['library'], dependency['unit'] = match.group().split('.')[:2]
                # Library 'work' means 'this' library, so we replace it
                # by the library name itself
                if dependency['library'] == 'work':
                    dependency['library'] = self.library
                if dependency not in dependencies:
                    dependencies.append(dependency)

        self._design_units = []
        for design_unit in design_units:
            if design_unit['type'] == 'package body':
                dependencies += [{'library' : self.library, 'unit': design_unit['name']}]
            else:
                self._design_units += [design_unit]

        self._deps = dependencies
        _logger.info("Source '%s' depends on: %s", str(self), \
                ", ".join(["%s.%s" % (x['library'], x['unit']) for x in self._deps]))

        self._sanityCheckNames()

    def _sanityCheckNames(self): # pragma: no cover
        """Sanity check on the names we found to catch errors we
        haven't covered"""
        for unit in self._design_units:
            if not _RE_VALID_NAME_CHECK.match(unit['name']):
                raise RuntimeError("Unit name %s is invalid" % unit['name'])

        for dependency in self._deps:
            if not _RE_VALID_NAME_CHECK.match(dependency['library']):
                raise RuntimeError("Dependency library %s is invalid" % \
                        dependency['library'])
            if not len(dependency['library']):
                raise RuntimeError("Dependency library %s is invalid" % \
                        dependency['library'])
            if not _RE_VALID_NAME_CHECK.match(dependency['unit']):
                raise RuntimeError("Dependency unit %s is invalid" % dependency['unit'])
            if not len(dependency['unit']):
                raise RuntimeError("Dependency unit %s is invalid" % dependency['unit'])

    def getDesignUnits(self):
        """Returns a list of dictionaries with the design units defined.
        The dict defines the name (as defined in the source file) and
        the type (package, entity, etc)"""
        with self._lock:
            self._parseIfChanged()
        return self._design_units

    def getDependencies(self):
        """Returns a list of dictionaries with the design units this
        source file depends on. Dict defines library and unit"""
        with self._lock:
            self._parseIfChanged()
        return self._deps

    def getmtime(self):
        """Gets file modification time as defined in os.path.getmtime"""
        try:
            mtime = os.path.getmtime(self.filename)
        except OSError: # pragma: no cover
            mtime = None
        return mtime

def standalone(): # pragma: no cover
    """Standalone run"""
    import sys
    for arg in sys.argv[1:]:
        source = VhdlSourceFile(arg)
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

if __name__ == '__main__':
    standalone()

