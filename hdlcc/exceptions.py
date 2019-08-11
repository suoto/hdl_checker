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
'Exceptions raised by hdlcc'

class HdlccBaseException(Exception):
    """
    Base class for exceptions raise by hdlcc
    """

class SanityCheckError(HdlccBaseException):
    """
    Exception raised when a builder fails to execute its sanity check
    """

    def __init__(self, builder, msg):
        self._msg = msg
        self.builder = builder
        super(SanityCheckError, self).__init__()

    def __str__(self): # pragma: no cover
        return "Failed to create builder '%s' with message '%s'" % \
                (self.builder, self._msg)

class UnknownParameterError(HdlccBaseException):
    """
    Exception raised when an unknown parameter is found in a
    configuration file
    """

    def __init__(self, parameter):
        self._parameter = parameter
        super(UnknownParameterError, self).__init__()

    def __str__(self): # pragma: no cover
        return "Unknown parameter '%s'" % self._parameter

