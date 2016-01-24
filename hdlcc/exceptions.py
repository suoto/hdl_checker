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

class VimHdlBaseException(Exception):
    pass

class SanityCheckError(VimHdlBaseException):
    def __init__(self, s):
        self._s = s

    def __str__(self):
        return "Sanity check failed with message '%s'" % self._s

class UnknownConfigFileExtension(VimHdlBaseException):
    def __init__(self, s):
        self._s = s

    def __str__(self):
        return "Unknown config file extension: %s" % self.s
