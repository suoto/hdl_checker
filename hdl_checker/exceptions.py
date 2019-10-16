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
"Exceptions raised by hdl_checker"


class HdlCheckerBaseException(Exception):
    """
    Base class for exceptions raise by hdl_checker
    """


class SanityCheckError(HdlCheckerBaseException):
    """
    Exception raised when a builder fails to execute its sanity check
    """

    def __init__(self, builder, msg):
        self._msg = msg
        self.builder = builder
        super(SanityCheckError, self).__init__()

    def __str__(self):  # pragma: no cover
        return "Failed to create builder '%s' with message '%s'" % (
            self.builder,
            self._msg,
        )


class UnknownParameterError(HdlCheckerBaseException):
    """
    Exception raised when an unknown parameter is found in a
    configuration file
    """

    def __init__(self, parameter):
        self._parameter = parameter
        super(UnknownParameterError, self).__init__()

    def __str__(self):  # pragma: no cover
        return "Unknown parameter '%s'" % self._parameter


class UnknownTypeExtension(HdlCheckerBaseException):
    """
    Exception thrown when trying to get the file type of an unknown extension.
    Known extensions are one of '.vhd', '.vhdl', '.v', '.vh', '.sv', '.svh'
    """

    def __init__(self, path):
        super(UnknownTypeExtension, self).__init__()
        self._path = path

    def __str__(self):
        return "Couldn't determine file type for path '%s'" % self._path
