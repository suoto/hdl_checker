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
"Fallback compiler for cases where no compiler is found"

from hdlcc.compilers import BaseCompiler

class Fallback(BaseCompiler):
    "Dummy fallback compiler"

    # Implementation of abstract class properties
    __builder_name__ = 'fallback'

    def __init__(self, target_folder):
        self._version = '<undefined>'
        super(Fallback, self).__init__(target_folder)

    def _makeMessageRecords(self, line):
        return []

    def _shouldIgnoreLine(self, line):
        return True

    def checkEnvironment(self):
        return True

    def _buildSource(self, source, flags=None):
        return [], []

    def _createLibrary(self, source):
        pass

