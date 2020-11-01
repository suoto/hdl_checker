# This file is part of HDL Checker.
#
# Copyright (c) 2015 - 2019 suoto (Andre Souto)
#
# HDL Checker is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# HDL Checker is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with HDL Checker.  If not, see <http://www.gnu.org/licenses/>.
"Path helper class to speed up comparing different paths"

# pylint: disable=useless-object-inheritance

import logging
from os import path as p
from os import stat
from typing import Union

import six

_logger = logging.getLogger(__name__)


class Path(object):
    "Path helper class to speed up comparing different paths"

    def __init__(self, name, base_path=None):
        # type: (Union[Path, str], Union[Path, str, None]) -> None
        assert isinstance(
            name, (Path, six.string_types)
        ), "Invalid type for path: {} ({})".format(name, type(name))

        if p.isabs(str(name)) or base_path is None:
            _name = name
        else:
            _name = p.join(str(base_path), str(name))
        self._name = p.normpath(str(_name))

    @property
    def mtime(self):
        # type: () -> float
        """
        Equivalent to os.path.getmtime(self.name)
        """
        return p.getmtime(self.name)

    @property
    def abspath(self):
        # type: () -> str
        """
        Equivalent to os.path.abspath(self.name)
        """
        return p.abspath(self.name)

    @property
    def basename(self):
        # type: () -> str
        """
        Equivalent to os.path.basename(self.name)
        """
        return p.basename(self.name)

    @property
    def dirname(self):
        # type: () -> str
        """
        Equivalent to os.path.dirname(self.name)
        """
        return p.dirname(self.name)

    @property
    def name(self):
        """
        Absolute path, either the path passed to the constructor or the path
        prepended with base_path. In the second case, it's up to the caller to
        ensure an absolute path can be constructed; no exception or warning is
        thrown.
        """
        return self._name

    def __str__(self):
        return self.name

    def __repr__(self):
        # type: () -> str
        return "{}({})".format(self.__class__.__name__, repr(self.name))

    @property
    def stat(self):
        """
        Equivalent to os.path.stat(self.name)
        """
        return stat(self.name)

    def __hash__(self):
        return hash(self.name)

    def __eq__(self, other):
        """Overrides the default implementation"""
        try:
            # Same absolute paths mean the point to the same file. Prefer this
            # to avoid calling os.stat all the time
            if self.abspath == other.abspath:
                return True
            return p.samestat(self.stat, other.stat)
        except (AttributeError, FileNotFoundError):
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
        obj._name = state["name"]  # pylint: disable=protected-access

        return obj

    def endswith(self, other):
        # type: (str) -> bool
        """
        Checks if the paths end with the same suffix
        """
        # Split the path at the path separator to compare the appropriate
        # part
        ref = p.normpath(other).split(p.sep)
        return self.name.split(p.sep)[-len(ref) :] == ref


class TemporaryPath(Path):
    """
    Class made just to differentiate a path from a temporary path created to
    dump a source's content
    """
