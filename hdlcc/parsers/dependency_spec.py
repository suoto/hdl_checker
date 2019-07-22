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
""

from functools import total_ordering

class SourceLocation(object):
    def __init__(self, filename, line_number, column_number=None):
        self.filename = filename
        self.line_number = line_number
        self.column_number = column_number

    def __repr__(self):
        return '{}.{}(filename={}, line_number={}, column_number={})'.format(
            __name__, self.__class__.__name__, repr(self.filename),
            repr(self.line_number), repr(self.column_number))

@total_ordering
class DependencySpec(object):
    def __init__(self, library, name, location=None):
        self._library = library
        self._name = name
        self._location = location

    def __lt__(self, other):
        return hash(self) < hash(other)

    @property
    def library(self):
        return self._library

    @property
    def name(self):
        return self._name

    @property
    def location(self):
        return self._location

    @property
    def __hash_key__(self):
        return self.library, self.name

    def __repr__(self):
        return '{}.{}(library={}, name={}, location={})'.format(
            __name__, self.__class__.__name__, repr(self.library),
            repr(self.name), repr(self.location))

    def __hash__(self):
        """Overrides the default implementation"""
        return hash(tuple(sorted(self.__hash_key__)))

    def __eq__(self, other):
        """Overrides the default implementation"""
        if isinstance(other, DependencySpec):
            return self.__hash_key__ == other.__hash_key__
        return NotImplemented

    def __ne__(self, other):
        """Overrides the default implementation (unnecessary in Python 3)"""
        result = self.__eq__(other)
        if result is not NotImplemented:
            return not result
        return NotImplemented
