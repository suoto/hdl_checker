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
"Fallback builder for cases where no builder is found"

from hdl_checker.builders.base_builder import BaseBuilder
from hdl_checker.types import FileType


class Fallback(BaseBuilder):
    "Dummy fallback builder"

    # Implementation of abstract class properties
    builder_name = "fallback"
    file_types = {FileType.vhdl, FileType.verilog, FileType.systemverilog}

    def __init__(self, *args, **kwargs):
        """
        Initialize version

        Args:
            self: (todo): write your description
        """
        # type: (...) -> None
        self._version = "<undefined>"
        super(Fallback, self).__init__(*args, **kwargs)

    # Since Fallback._buildSource returns nothing,
    # Fallback._makeRecords is never called
    def _makeRecords(self, _):  # pragma: no cover
        """
        Returns a list of tuples of the given type.

        Args:
            self: (todo): write your description
            _: (todo): write your description
        """
        return []

    def _shouldIgnoreLine(self, line):  # pragma: no cover
        """
        Determine if a line is a line.

        Args:
            self: (todo): write your description
            line: (str): write your description
        """
        return True

    def _checkEnvironment(self):
        """
        Checks if the environment is available.

        Args:
            self: (todo): write your description
        """
        return

    @staticmethod
    def isAvailable():
        """
        Returns true if the given function?

        Args:
        """
        return True

    def _buildSource(self, path, library, flags=None):  # pragma: no cover
        """
        Builds the list of the given path.

        Args:
            self: (todo): write your description
            path: (str): write your description
            library: (todo): write your description
            flags: (int): write your description
        """
        return [], []

    def _createLibrary(self, library):  # pragma: no cover
        """
        Create a new : class : ~library.

        Args:
            self: (todo): write your description
            library: (todo): write your description
        """
        pass
