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
"Path helper class to speed up comparing different paths"

# pylint: disable=useless-object-inheritance

import logging
import os.path as p
from os import stat
from typing import AnyStr

_logger = logging.getLogger(__name__)


class Path(object):
    "Path helper class to speed up comparing different paths"

    def __init__(self, name):
        # type: (str) -> None
        assert isinstance(name, (str, unicode)), "Invalid type for path: {} ({})".format(
            name, type(name)
        )
        self._name = name
        self._stat = None

    @property
    def mtime(self):
        # type: () -> float
        return p.getmtime(self.name)

    @property
    def abspath(self):
        # type: () -> str
        return p.abspath(self.name)

    @property
    def basename(self):
        # type: () -> str
        return p.basename(self.name)

    @property
    def dirname(self):
        # type: () -> str
        return p.dirname(self.name)

    @property
    def name(self):
        return self._name

    def __str__(self):
        return self.name

    def __repr__(self):
        return "Path({})".format(repr(self.name))

    @property
    def stat(self):
        if self._stat is None:
            self._stat = stat(self.name)
        return self._stat

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        """Overrides the default implementation"""
        try:
            if p.exists(self.name):
                return p.samestat(self.stat, other.stat)
            return self.abspath == other.abspath
        except AttributeError:
            return False

        return NotImplemented  # pragma: no cover

    def __ne__(self, other):  # pragma: no cover
        """Overrides the default implementation (unnecessary in Python 3)"""
        result = self.__eq__(other)

        if result is NotImplemented:
            return NotImplemented

        return not result

    def __jsonEncode__(self):
        """
        Gets a dict that describes the current state of this object
        """
        return {"name": self.name}

    @classmethod
    def __jsonDecode__(cls, state):
        """Returns an object of cls based on a given state"""

        obj = super(Path, cls).__new__(cls)
        obj._name = state["name"]
        obj._stat = None

        return obj
