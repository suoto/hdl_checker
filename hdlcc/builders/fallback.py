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
"Fallback builder for cases where no builder is found"

from hdlcc.builders.base_builder import BaseBuilder

class Fallback(BaseBuilder):
    "Dummy fallback builder"

    # Implementation of abstract class properties
    builder_name = 'fallback'
    file_types = ['vhdl', 'verilog', 'systemverilog']

    def __init__(self, target_folder):
        self._version = '<undefined>'
        super(Fallback, self).__init__(target_folder)

    # Since Fallback._buildSource returns nothing,
    # Fallback._makeRecords is never called
    def _makeRecords(self, _): # pragma: no cover
        return []

    def _shouldIgnoreLine(self, line): # pragma: no cover
        return True

    def checkEnvironment(self):
        return True

    def _buildSource(self, source, flags=None): # pragma: no cover
        return [], []

    def _createLibrary(self, source): # pragma: no cover
        pass

    def getBuiltinLibraries(self): # pragma: no cover
        return []

