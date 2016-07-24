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
"Base source file parser"

import abc
import os
import logging

from hdlcc.utils import getFileType

_logger = logging.getLogger(__name__)

class BaseSourceFile(object):
    """Parses and stores information about a source file such as
    design units it depends on and design units it provides"""

    __metaclass__ = abc.ABCMeta

    def __init__(self, filename, library='work', flags=None):
        self.filename = os.path.normpath(filename)
        self.library = library
        self.flags = flags if flags is not None else []
        self._design_units = []
        self._deps = []
        self._mtime = 0
        self.filetype = getFileType(self.filename)

        self.abspath = os.path.abspath(filename)
        self._parseIfChanged()

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
            'filetype' : self.filetype}
        return state

    @classmethod
    def recoverFromState(cls, state):
        "Returns an object of cls based on a given state"
        # pylint: disable=protected-access
        obj = super(BaseSourceFile, cls).__new__(cls)
        obj.filename = state['filename']
        obj.abspath = state['abspath']
        obj.library = state['library']
        obj.flags = state['flags']
        obj._design_units = state['_design_units']
        obj._deps = state['_deps']
        obj._mtime = state['_mtime']
        obj.filetype = state['filetype']
        # pylint: enable=protected-access

        return obj

    def __repr__(self):
        return "BaseSourceFile('%s', library='%s', flags=%s)" % \
                (self.abspath, self.library, self.flags)

    # We'll use Python data model to make easier to check if a recovered object
    # matches its original counterpart
    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False

        for attr in ('filename', 'library', 'flags', 'filetype', 'abspath'):
            if not hasattr(other, attr):
                #  _logger.warning("Other has no %s attribute", attr)
                return False
            if getattr(self, attr) != getattr(other, attr):
                #  _logger.warning("Attribute %s differs", attr)
                return False


        #  _logger.warning("%s matches %s", repr(self), repr(other))
        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __str__(self):
        return "[%s] %s" % (self.library, self.filename)

    def _parseIfChanged(self):
        "Parses this source file if it has changed"
        try:
            if self._changed():
                _logger.debug("Parsing %s", str(self))
                self._mtime = self.getmtime()
                self._doParse()
                if self._deps:
                    _logger.info("Source '%s' depends on: %s", str(self), \
                        ", ".join(["%s.%s" % (x['library'], x['unit']) \
                            for x in self._deps]))
                else:
                    _logger.info("Source '%s' has no dependencies", str(self))
        except OSError: # pragma: no cover
            _logger.warning("Couldn't parse '%s' at this moment", self)

    def _changed(self):
        """Checks if the file changed based on the modification time provided
        by os.path.getmtime"""
        return self.getmtime() > self._mtime

    @abc.abstractmethod
    def _getSourceContent(self):
        """Replace everything from comment ('--') until a line break
        and converts to lowercase"""

    @abc.abstractmethod
    def _getDependencies(self, libraries):
        """Parses the source and returns a list of dictionaries that
        describe its dependencies"""

    @abc.abstractmethod
    def _doParse(self):
        """Finds design units and dependencies then translate some design
        units into information useful in the conext of the project"""

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

