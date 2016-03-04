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
"ModelSim builder implementation"

import os
import re
from hdlcc.builders import BaseBuilder
from hdlcc.utils import shell
from hdlcc import exceptions

class MSim(BaseBuilder):
    '''Builder implementation of the ModelSim compiler'''

    # Implementation of abstract class properties
    __builder_name__ = 'msim'

    # MSim specific class properties
    _BuilderStdoutMessageScanner = re.compile('|'.join([
        r"^\*\*\s*([WE])\w+:\s*",
        r"\((\d+)\):",
        r"[\[\(]([\w-]+)[\]\)]\s*",
        r"(.*\.(vhd|sv|svh)\b)",
        r"\s*\(([\w-]+)\)",
        r"\s*(.+)",
        ]), re.I)

    _BuilderStdoutIgnoreLines = re.compile('|'.join([
        r"^\s*$",
        r"^(?!\*\*\s(Error|Warning):).*",
        r".*VHDL Compiler exiting\s*$"]))

    _BuilderRebuildUnitsScanner = re.compile(
        r"Recompile\s*([^\s]+)\s+because\s+[^\s]+\s+has changed")

    def _shouldIgnoreLine(self, line):
        return self._BuilderStdoutIgnoreLines.match(line)

    def __init__(self, target_folder):
        self._version = ''
        super(MSim, self).__init__(target_folder)
        self._modelsim_ini = os.path.join(self._target_folder, 'modelsim.ini')

        # FIXME: Built-in libraries should not be statically defined
        # like this. Review this at some point
        self.builtin_libraries = ['ieee', 'std', 'unisim', 'xilinxcorelib', \
                'synplify', 'synopsis', 'maxii', 'family_support']

        # Use vlib with '-type directory' switch to get a more consistent
        # folder organization. The vlib command has 3 variants:
        # - version <= 6.2: "Old" library organization
        # - 6.3 <= version <= 10.2: Has the switch but defaults to directory
        # version >= 10.2+: Has the switch and the default is not directory
        if self._version >= '10.2':
            self._vlib_args = ['-type', 'directory']
        else:
            self._vlib_args = []
        self._logger.debug("vlib arguments: '%s'", str(self._vlib_args))

    def _makeMessageRecords(self, line):
        line_number = None
        column = None
        filename = None
        error_number = None
        error_type = None
        error_message = None

        scan = self._BuilderStdoutMessageScanner.scanner(line)

        while True:
            match = scan.match()
            if not match:
                break

            if match.lastindex == 1:
                error_type = match.group(match.lastindex)
            if match.lastindex == 2:
                line_number = match.group(match.lastindex)
            if match.lastindex in (3, 6):
                try:
                    error_number = \
                            re.findall(r"\d+", match.group(match.lastindex))[0]
                except IndexError:
                    error_number = 0
            if match.lastindex == 4:
                filename = match.group(match.lastindex)
            if match.lastindex == 7:
                error_message = match.group(match.lastindex)

        return [{
            'checker'        : self.__builder_name__,
            'line_number'    : line_number,
            'column'         : column,
            'filename'       : filename,
            'error_number'   : error_number,
            'error_type'     : error_type,
            'error_message'  : error_message,
        }]

    def checkEnvironment(self):
        try:
            stdout = self._subprocessRunner(['vcom.exe', '-version'])
            self._version = \
                    re.findall(r"(?<=vcom)\s+([\w\.]+)\s+(?=Compiler)", \
                    stdout[0])[0]
            self._logger.info("vcom version string: '%s'. " + \
                    "Version number is '%s'", \
                    stdout[:-1], self._version)
        except Exception as exc:
            import traceback
            self._logger.warning("Sanity check failed:\n%s", traceback.format_exc())
            self._logger.warning("Path:")
            for path in os.environ['PATH'].split(os.pathsep):
                self._logger.warning(" - %s", path)
            raise exceptions.SanityCheckError(str(exc))

    def _getUnitsToRebuild(self, line):
        rebuilds = []
        if '(vcom-13)' in line:
            for match in self._BuilderRebuildUnitsScanner.finditer(line):
                if not match:
                    continue
                rebuilds.append(match.group(match.lastindex).split('.'))

        return rebuilds

    def _buildSource(self, source, flags=None):
        cmd = ['vcom', '-modelsimini', self._modelsim_ini, '-work', \
                os.path.join(self._target_folder, source.library)]
        if flags:
            cmd += flags
        cmd += [source.filename]

        return self._subprocessRunner(cmd)

    def _createLibrary(self, source):
        if os.path.exists(os.path.join(self._target_folder, source.library)):
            return
        if os.path.exists(self._modelsim_ini):
            self._mapLibrary(source.library)
        else:
            self._addLibraryToIni(source.library)

    def _addLibraryToIni(self, library):
        "Adds a library to a non-existent ModelSim init file"
        self._logger.info("Library %s not found, creating", library)

        self._subprocessRunner(
            ['cd {target_folder} && vlib {vlib_args} {library}'.format(
                target_folder=self._target_folder,
                library=os.path.join(self._target_folder, library),
                vlib_args=" ".join(self._vlib_args))],
            shell=True)

        self._subprocessRunner(
            ['cd {target_folder} && vmap {library} {library_path}'.format(
                target_folder=self._target_folder,
                library=library,
                library_path=os.path.join(self._target_folder, library)),],
            shell=True)

    def deleteLibrary(self, library):
        "Deletes a library from ModelSim init file"
        if not os.path.exists(os.path.join(self._target_folder, library)):
            self._logger.warning("Library %s doesn't exists", library)
            return
        shell('vdel -modelsimini {modelsimini} -lib {library} -all'.format(
            modelsimini=self._modelsim_ini, library=library))

    def _mapLibrary(self, library):
        "Adds a library to an existing ModelSim init file"
        self._logger.info("modelsim.ini found, adding %s", library)

        shell('vlib {vlib_args} {library}'.format(
            vlib_args=" ".join(self._vlib_args),
            library=os.path.join(self._target_folder, library)))
        shell('vmap -modelsimini {modelsimini} {library} {library_path}'.format(
            modelsimini=self._modelsim_ini,
            library=library,
            library_path=os.path.join(self._target_folder, library)))

