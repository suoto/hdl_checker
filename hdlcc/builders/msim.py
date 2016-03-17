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
import os.path as p
import re
from .base_builder import BaseBuilder

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
        #  r"Recompile\s*([^\s]+)\s+because\s+[^\s]+\s+has changed")
        r"Recompile\s*(?P<library_name>\w+)\.(?P<unit_name>\w+)\s+because"
        r"\s+[^\s]+\s+has changed")

    _BuilderLibraryScanner = re.compile(
        r"^\"(?P<library_name>\w+)\""
        r"\s+maps to directory\s*"
        r"(?P<library_path>.*)\.$", re.I)

    def _shouldIgnoreLine(self, line):
        return self._BuilderStdoutIgnoreLines.match(line)

    def __init__(self, target_folder):
        self._version = ''
        super(MSim, self).__init__(target_folder)
        self._modelsim_ini = p.join(self._target_folder, 'modelsim.ini')

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
        self._builtin_libraries = []
        self._parseBuiltinLibraries()

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
        stdout = self._subprocessRunner(['vcom', '-version'])
        self._version = \
                re.findall(r"(?<=vcom)\s+([\w\.]+)\s+(?=Compiler)", \
                stdout[0])[0]
        self._logger.info("vcom version string: '%s'. " + \
                "Version number is '%s'", \
                stdout[:-1], self._version)

    def _parseBuiltinLibraries(self):
        "Discovers libraries that exist regardless before we do anything"
        for line in self._subprocessRunner(['vmap', ]):
            for match in self._BuilderLibraryScanner.finditer(line):
                self._builtin_libraries.append(match.groupdict()['library_name'])

    def getBuiltinLibraries(self):
        return self._builtin_libraries

    def _getUnitsToRebuild(self, line):
        rebuilds = []
        if '(vcom-13)' in line:
            for match in self._BuilderRebuildUnitsScanner.finditer(line):
                if not match:
                    continue
                rebuilds.append(match.groupdict())

        return rebuilds

    def _buildSource(self, source, flags=None):
        cmd = ['vcom', '-modelsimini', self._modelsim_ini, '-quiet',
               '-work', p.join(self._target_folder, source.library)]
        if flags:
            cmd += flags
        cmd += [source.filename]

        return self._subprocessRunner(cmd)

    def _createLibrary(self, source):
        try:
            if p.exists(p.join(self._target_folder, source.library)):
                return
            if p.exists(self._modelsim_ini):
                self._mapLibrary(source.library)
            else:
                self._addLibraryToIni(source.library)
        except:
            self._logger.debug("Current dir when exception was raised: %s",
                               p.abspath(os.curdir))
            raise

    def _addLibraryToIni(self, library):
        "Adds a library to a non-existent ModelSim init file"
        self._logger.info("Library %s not found, creating", library)

        cwd = p.abspath(os.curdir)
        self._logger.info("Current dir is %s, changing to %s",
                          cwd, self._target_folder)
        os.chdir(self._target_folder)
        if cwd == os.curdir:
            self._logger.fatal("cwd: %s, curdir: %s, error!", cwd, os.curdir)
            assert 0

        self._subprocessRunner(['vlib', ] + self._vlib_args +
                               [p.join(self._target_folder, library), ])

        self._subprocessRunner(['vmap', library, ] +
                               [p.join(self._target_folder, library)])

        self._logger.info("Current dir is %s, changing to %s",
                          os.curdir, cwd)
        os.chdir(cwd)


    def deleteLibrary(self, library):
        "Deletes a library from ModelSim init file"
        if not p.exists(p.join(self._target_folder, library)):
            self._logger.warning("Library %s doesn't exists", library)
            return
        return self._subprocessRunner(
            ['vdel', '-modelsimini', self._modelsim_ini, '-lib', library,
             '-all'])

    def _mapLibrary(self, library):
        "Adds a library to an existing ModelSim init file"
        self._logger.info("modelsim.ini found, adding %s", library)

        self._subprocessRunner(['vlib', ] + self._vlib_args +
                               [p.join(self._target_folder, library)])

        self._subprocessRunner(['vmap', '-modelsimini', self._modelsim_ini,
                                library, p.join(self._target_folder, library)])


