# This file is part of HDL Code Checker.
#
# Copyright (c) 2015-2019 Andre Souto
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

from hdlcc.diagnostics import BuilderDiag, DiagType

from .base_builder import BaseBuilder


class XVHDL(BaseBuilder):
    '''Builder implementation of the xvhdl compiler'''

    # Implementation of abstract class properties
    builder_name = 'xvhdl'
    # TODO: Add xvlog support
    file_types = ('vhdl', )

    # XVHDL specific class properties
    _stdout_message_scanner = re.compile(
        r"^(?P<severity>[EW])\w+:\s*"
        r"\[(?P<error_code>[^\]]+)\]\s*"
        r"(?P<error_message>[^\[]+)\s*"
        r"("
        r"\[(?P<filename>[^:]+):"
        r"(?P<line_number>\d+)\]"
        r")?", flags=re.I)

    _iter_rebuild_units = re.compile(
        r"ERROR:\s*\[[^\]]*\]\s*"
        r"'?.*/(?P<library_name>\w+)/(?P<unit_name>\w+)\.vdb'?"
        r"\s+needs to be re-saved.*", flags=re.I).finditer

    def _shouldIgnoreLine(self, line):
        if 'ignored due to previous errors' in line:
            return True

        # Ignore messages like
        # ERROR: [VRFC 10-3032] 'library.package' failed to restore
        # This message doesn't come alone, we should be getting other (more
        # usefull) info anyway
        if '[VRFC 10-3032]' in line:
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
        scan = self._stdout_message_scanner.scanner(line)

        match = scan.match()
        if not match:
            return

        info = match.groupdict()

        diag = BuilderDiag(
            builder_name=self.builder_name,
            text=info['error_message'].strip(),
            line_number=info['line_number'],
            filename=info['filename'],
            error_code=info['error_code'])

        if info.get('severity', None) in ('W', 'e'):
            diag.severity = DiagType.WARNING
        elif info.get('severity', None) in ('E', 'e'):
            diag.severity = DiagType.ERROR

        yield diag

    def _parseBuiltinLibraries(self):
        "(Not used by XVHDL)"

    def _checkEnvironment(self):
        stdout = self._subprocessRunner(['xvhdl', '--nolog', '--version'])
        self._version = \
                re.findall(r"^Vivado Simulator\s+([\d\.]+)", stdout[0])[0]
        self._logger.info("xvhdl version string: '%s'. "
                          "Version number is '%s'",
                          stdout[:-1], self._version)

    @staticmethod
    def isAvailable():
        return not os.system('xvhdl --nolog --version')

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
