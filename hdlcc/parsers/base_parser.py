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
import os.path as p
import logging
import re
import time
from contextlib import contextmanager

from hdlcc.utils import getFileType, removeDuplicates

_logger = logging.getLogger(__name__)

class BaseSourceFile(object):  # pylint:disable=too-many-instance-attributes
    """
    Parses and stores information about a source file such as design
    units it depends on and design units it provides
    """

    __metaclass__ = abc.ABCMeta

    @abc.abstractproperty
    def _comment(self):
        """
        Should return a regex object that matches a comment (or comments)
        used by the language
        """

    def __init__(self, filename, library='work', flags=None):
        self.filename = p.normpath(filename)
        self.library = library
        self.flags = flags if flags is not None else []
        self._cache = {}
        self._content = None
        self._mtime = 0
        self.filetype = getFileType(self.filename)
        self._prev = None
        self.abspath = p.abspath(filename)

    def getState(self):
        """
        Gets a dict that describes the current state of this object
        """
        state = {
            'filename' : self.filename,
            'abspath' : self.abspath,
            'library' : self.library,
            'flags' : self.flags,
            '_cache' : self._cache,
            '_mtime' : self._mtime,
            'filetype' : self.filetype}
        if 'raw_content' in state['_cache']:
            del state['_cache']['raw_content']
        return state

    @classmethod
    def recoverFromState(cls, state):
        """
        Returns an object of cls based on a given state"""
        # pylint: disable=protected-access
        obj = super(BaseSourceFile, cls).__new__(cls)
        obj.filename = state['filename']
        obj.abspath = state['abspath']
        obj.library = state['library']
        obj.flags = state['flags']
        obj._cache = state['_cache']
        obj._content = None
        obj._prev = None
        obj._mtime = state['_mtime']
        obj.filetype = state['filetype']
        # pylint: enable=protected-access

        return obj

    # We'll use Python data model to make easier to check if a recovered object
    # matches its original counterpart
    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False

        for attr in ('filename', 'library', 'flags', 'filetype', 'abspath'):
            if not hasattr(other, attr):  # pragma: no cover
                return False
            if getattr(self, attr) != getattr(other, attr):
                return False

        return True

    def __ne__(self, other):
        return not self.__eq__(other)

    def __repr__(self):
        return "BaseSourceFile('%s', library='%s', flags=%s)" % \
                (self.abspath, self.library, self.flags)

    def __str__(self):
        return "[%s] %s" % (self.library, self.filename)

    def __hash__(self):
        return hash(repr(self))

    def _changed(self):
        """
        Checks if the file changed based on the modification time
        provided by p.getmtime
        """
        if self.getmtime() > self._mtime:
            _logger.debug("File '%s' has changed", self.filename)
            return True
        return False

    def _clearCachesIfChanged(self):
        """
        Clears all the caches if the file has changed to force updating
        every parsed info
        """
        if self._changed():
            # Since the content was set by the caller, we can't really clear
            # this unless we're handling with a proper file
            if not self.hasBufferContent():  # pragma: no cover
                self._content = None
            self._cache = {}

    def getmtime(self):
        """
        Gets file modification time as defined in p.getmtime
        """
        if self.hasBufferContent():
            return 0
        if not p.exists(self.filename):
            return None
        return p.getmtime(self.filename)

    @contextmanager
    def havingBufferContent(self, content):
        """
        Context manager for handling a source file with a custom content
        that is different from the file it points to. This is intended to
        allow as-you-type checking
        """
        self._setBufferContent(content)
        yield
        self._clearBufferContent()

    def getDumpPath(self):
        """
        Returns the dump path in use while inside the havingBufferContent
        context
        """
        return p.join(p.dirname(self.filename), '.dump_' +
                      p.basename(self.filename))

    def hasBufferContent(self):
        """
        Returns true whenever the source is inside the havingBufferContent
        context
        """
        return self._prev is not None

    def _setBufferContent(self, content):
        """
        Setup portion of the havingBufferContent context
        """
        _logger.debug("Setting source content")
        self._prev = (self._mtime, self._content)
        self._content = content
        self._mtime = time.time()

        buffer_dump_path = self.getDumpPath()
        _logger.debug("Dumping buffer content to '%s'", buffer_dump_path)
        open(buffer_dump_path, 'w').write(self._content)

    def _clearBufferContent(self):
        """
        Tear down portion of the havingBufferContent context
        """
        _logger.debug("Clearing buffer content")
        buffer_dump_path = self.getDumpPath()
        if p.exists(buffer_dump_path):
            os.remove(buffer_dump_path)

        self._mtime, self._content = self._prev
        self._prev = None

    def getSourceContent(self):
        """
        Cached version of the _getSourceContent method
        """
        self._clearCachesIfChanged()

        if self._content is None:
            self._content = self._getSourceContent()
            self._mtime = self.getmtime()

        return self._content

    def getRawSourceContent(self):
        """
        Gets the whole source content, without removing comments or
        other preprocessing
        """
        self._clearCachesIfChanged()

        if self.hasBufferContent():
            return self._content

        if 'raw_content' not in self._cache or self._changed():
            self._cache['raw_content'] = \
                open(self.filename, mode='rb').read().decode(errors='ignore')

        return self._cache['raw_content']

    def getDesignUnits(self):
        """
        Cached version of the _getDesignUnits method
        """
        if not p.exists(self.filename):
            return []
        self._clearCachesIfChanged()
        if 'design_units' not in self._cache:
            self._cache['design_units'] = self._getDesignUnits()

        return self._cache['design_units']

    def getDependencies(self):
        """
        Cached version of the _getDependencies method
        """
        if not p.exists(self.filename):
            return []

        self._clearCachesIfChanged()
        if 'dependencies' not in self._cache:
            self._cache['dependencies'] = self._getDependencies()

        return self._cache['dependencies']

    def getLibraries(self):
        """
        Cached version of the _getLibraries method
        """
        if not p.exists(self.filename):
            return []

        self._clearCachesIfChanged()
        if 'libraries' not in self._cache:
            self._cache['libraries'] = removeDuplicates(self._getLibraries())

        return self._cache['libraries']

    def getMatchingLibrary(self, unit_type, unit_name):
        """
        Cached version of the _getMatchingLibrary method
        """
        key = ','.join(['getMatchingLibrary', unit_name, unit_type])
        self._clearCachesIfChanged()
        if key not in self._cache:
            self._cache[key] = self._getMatchingLibrary(
                unit_type, unit_name)
        return self._cache[key]

    def getDesignUnitsDotted(self):
        """
        Returns the design units using the <library>.<design_unit>
        representation
        """
        return set(["%s.%s" % (self.library, x['name']) \
                    for x in self.getDesignUnits()])

    @abc.abstractmethod
    def _getSourceContent(self):
        """
        Method that should implement pre parsing of the source file.
        This includes removing comments and unnecessary or unimportant
        chunks of text to make the life of the real parsing easier.
        Should return a string and NOT a list of lines
        """

    @abc.abstractmethod
    def _getDesignUnits(self):
        """
        Method that should implement the real parsing of the source file
        to find design units defined. Use the output of the getSourceContent
        method to avoid unnecessary I/O
        """

    @abc.abstractmethod
    def _getLibraries(self):
        """
        Parses the source file to find libraries required by the file
        """

    @abc.abstractmethod
    def _getDependencies(self):
        """
        Parses the source and returns a list of dictionaries that
        describe its dependencies
        """

    def _getMatchingLibrary(self, unit_type, unit_name):
        if unit_type == 'package':
            match = re.search(r"use\s+(?P<library_name>\w+)\." + unit_name,
                              self.getSourceContent(), flags=re.S)
            if match.groupdict()['library_name'] == 'work':
                return self.library
            else:
                return match.groupdict()['library_name']
        assert False, "%s, %s" % (unit_type, unit_name)

