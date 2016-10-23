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
"Xilinx xhvdl builder implementation"

import os
import os.path as p
import re
from .base_builder import BaseBuilder

class XVHDL(BaseBuilder):
    '''Builder implementation of the xvhdl compiler'''

    # Implementation of abstract class properties
    builder_name = 'xvhdl'
    # TODO: Add xvlog support
    file_types = ('vhdl', )

    # XVHDL specific class properties
    _stdout_message_scanner = re.compile(
        r"^(?P<error_type>[EW])\w+:\s*"
        r"\[(?P<error_number>[^\]]+)\]\s*"
        r"(?P<error_message>[^\[]+)\s*\["
        r"(?P<filename>[^:]+):"
        r"(?P<line_number>\d+)", flags=re.I)

    _iter_rebuild_units = re.compile(
        r"ERROR:\s*\[[^\]]*\]\s*"
        r".*(?P<library_name>\w+)/(?P<unit_name>\w+)\.vdb\s+needs.*",
        flags=re.I).finditer

    def _shouldIgnoreLine(self, line):
        if 'ignored due to previous errors' in line:
            return True
        return not (line.startswith('ERROR') or
                    line.startswith('WARNING'))

    def __init__(self, target_folder):
        self._version = ''
        super(XVHDL, self).__init__(target_folder)
        self._xvhdlini = '.xvhdl.init'
        self._builtin_libraries = ('ieee', 'std', 'unisim', 'xilinxcorelib',
                                   'synplify', 'synopsis', 'maxii',
                                   'family_support')

    def _makeRecords(self, line):
        line_number = None
        column = None
        filename = None
        error_number = None
        error_type = None
        error_message = None

        scan = self._stdout_message_scanner.scanner(line)

        while True:
            match = scan.match()
            if not match:
                break

            _dict = match.groupdict()

            line_number = _dict['line_number']
            filename = _dict['filename']
            error_number = _dict['error_number']
            error_type = _dict['error_type']
            error_message = _dict['error_message'].strip()

        return [{
            'checker'        : self.builder_name,
            'line_number'    : line_number,
            'column'         : column,
            'filename'       : filename,
            'error_number'   : error_number,
            'error_type'     : error_type,
            'error_message'  : error_message,
        }]

    def _checkEnvironment(self):
        stdout = self._subprocessRunner(['xvhdl', '--nolog', '--version'])
        self._version = \
                re.findall(r"^Vivado Simulator\s+([\d\.]+)", stdout[0])[0]
        self._logger.info("xvhdl version string: '%s'. " + \
                "Version number is '%s'", \
                stdout[:-1], self._version)

    def getBuiltinLibraries(self):
        # FIXME: Built-in libraries should not be statically defined
        # like this. Review this at some point
        return self._builtin_libraries

    def _createLibrary(self, library):
        library = library.lower()
        if library in self._builtin_libraries:
            return

        assert library != 'ieee'

        if not p.exists(self._target_folder):
            os.mkdir(self._target_folder)
            self._added_libraries = []

        if library in self._added_libraries:
            return

        self._added_libraries.append(library)

        with open(self._xvhdlini, mode='w') as fd:
            content = '\n'.join(
                ["%s=%s" % (x, p.join(self._target_folder, x))
                 for x in self._added_libraries])
            fd.write(content)

    def _buildSource(self, path, library, flags=None):
        cmd = ['xvhdl',
               '--nolog',
               '--verbose', '0',
               '--initfile', p.abspath(self._xvhdlini),
               '--work', library]
        cmd += flags
        cmd += [path]
        return self._subprocessRunner(cmd)

    def _searchForRebuilds(self, line):
        rebuilds = []

        for match in self._iter_rebuild_units(line):
            mdict = match.groupdict()
            # When compilers reports units out of date, they do this
            # by either
            #  1. Giving the path to the file that needs to be rebuilt
            #     when sources are from different libraries
            #  2. Reporting which design unit has been affected by a
            #     given change.
            if 'rebuild_path' in mdict and mdict['rebuild_path'] is not None:
                rebuilds.append(mdict)
            else:
                rebuilds.append({'library_name' : 'work',
                                 'unit_name' : mdict['unit_name']})

        return rebuilds
