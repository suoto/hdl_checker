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
"ModelSim builder implementation"

import os
import os.path as p
import re
from shutil import copyfile
from .base_builder import BaseBuilder
from hdlcc.utils import getFileType

class MSim(BaseBuilder):
    '''Builder implementation of the ModelSim compiler'''

    # Implementation of abstract class properties
    builder_name = 'msim'
    file_types = ('vhdl', 'verilog', 'systemverilog')

    # MSim specific class properties
    _stdout_message_scanner = re.compile(
        r"^\*\*\s*(?P<error_type>[WE])\w+\s*" \
            r"(:\s*|\(suppressible\):\s*)"
        r"(" \
            r"(?P<filename>.*(?=\(\d+\)))"
            r"\((?P<line_number>\d+)\):\s*"
        r"|" \
            r"\(vcom-\d+\)\s*"
        r")"
        r"(?P<error_message>.*)\s*").finditer

    _should_ignore = re.compile('|'.join([
        r"^\s*$",
        r"^(?!\*\*\s(Error|Warning)\b).*",
        r".*VHDL Compiler exiting\s*$"])).match

    _iter_rebuild_units = re.compile(
        r"(" \
            r"Recompile\s*(?P<lib_name_0>\w+)\.(?P<unit_name_0>\w+)\s+because" \
            r"\s+[^\s]+\s+has changed"
        r"|" \
            r"^\*\* Warning:.*\(vcom-1127\)\s*Entity\s(?P<lib_name_1>\w+)\." \
            r"(?P<unit_name_1>\w+).*"
        r")").finditer

    _BuilderLibraryScanner = re.compile(
        r"^\"(?P<library_name>\w+)\""
        r"\s+maps to directory\s*"
        r"(?P<library_path>.*)\.$", re.I)

    # Default build flags
    default_flags = {
        'batch_build_flags' : {
            'vhdl' : ['-defercheck', '-nocheck', '-permissive'],
            'verilog' : ['-permissive', ],
            'systemverilog' : ['-permissive', ]},

        'single_build_flags' : {
            'vhdl' : ['-check_synthesis', '-lint', '-rangecheck',
                      '-pedanticerrors'],
            'verilog' : ['-lint', '-hazards', '-pedanticerrors'],
            'systemverilog' : ['-lint', '-hazards', '-pedanticerrors']},

        'global_build_flags' : {
            'vhdl' : ['-explicit',],
            'verilog' : [],
            'systemverilog' : []}}

    def _shouldIgnoreLine(self, line):
        return self._should_ignore(line)

    def __init__(self, target_folder):
        self._version = ''
        super(MSim, self).__init__(target_folder)
        self._modelsim_ini = p.join(self._target_folder, 'modelsim.ini')

        # Use vlib with '-type directory' switch to get a more consistent
        # folder organization. The vlib command has 3 variants:
        # - version <= 6.2: "Old" library organization
        # - 6.3 <= version <= 10.2: Has the switch but defaults to directory
        # version >= 10.2+: Has the switch and the default is not directory
        if self._version >= '10.2':  # pragma: no cover
            self._vlib_args = ['-type', 'directory']
        else:  # pragma: no cover
            self._vlib_args = []
        self._logger.debug("vlib arguments: '%s'", str(self._vlib_args))

    def _makeRecords(self, line):
        records = []

        for match in self._stdout_message_scanner(line):
            info = {
                'checker'        : self.builder_name,
                'line_number'    : None,
                'column'         : None,
                'filename'       : None,
                'error_number'   : None,
                'error_type'     : None,
                'error_message'  : None}
            for key, content in match.groupdict().items():
                info[key] = content

            if ('vcom-' in line) or ('vlog' in line):
                info['error_number'] = re.findall(r"(?<=vcom-|vlog-)\d+", line)[0]

            info['error_message'] = re.sub(r"\s*\((vcom|vlog)-\d+\)\s*", " ",
                                           info['error_message']).strip()
            records += [info]

        return records

    def _checkEnvironment(self):
        stdout = self._subprocessRunner(['vcom', '-version'])
        self._version = \
                re.findall(r"(?<=vcom)\s+([\w\.]+)\s+(?=Compiler)", \
                stdout[0])[0]
        self._logger.debug("vcom version string: '%s'. " + \
                "Version number is '%s'", \
                stdout, self._version)

    @staticmethod
    def isAvailable():
        return ((not os.system('vcom -version')) and
                (not os.system('vlog -version')))

    def _parseBuiltinLibraries(self):
        "Discovers libraries that exist regardless before we do anything"
        if not self._iniFileExists():
            self._createIniFile()
        for line in self._subprocessRunner(['vmap', ]):
            for match in self._BuilderLibraryScanner.finditer(line):
                self._builtin_libraries.append(match.groupdict()['library_name'])

    def getBuiltinLibraries(self):
        return self._builtin_libraries

    def _searchForRebuilds(self, line):
        rebuilds = []
        for match in self._iter_rebuild_units(line):
            mdict = match.groupdict()
            library_name = mdict['lib_name_0'] or mdict['lib_name_1']
            unit_name = mdict['unit_name_0'] or mdict['unit_name_1']
            if None not in (library_name, unit_name):
                rebuilds.append({'library_name' : library_name,
                                 'unit_name' : unit_name})
            else: # pragma: no cover
                _msg = "Something wrong while parsing '%s'. " \
                        "Match is '%s'" % (line, mdict)
                self._logger.error(_msg)
                assert 0, _msg

        return rebuilds

    def _buildSource(self, path, library, flags=None):
        filetype = getFileType(path)
        if filetype == 'vhdl':
            return self._buildVhdl(path, library, flags)
        elif filetype in ('verilog', 'systemverilog'):
            return self._buildVerilog(path, library, flags)
        else:  # pragma: no cover
            self._logger.error("Unknown file type %s for path '%s'",
                               filetype, path)

    def _getExtraFlags(self, lang):
        libs = []
        for library in self._added_libraries + self._external_libraries[lang]:
            libs = ['-L', library]
        for path in self._include_paths[lang]:
            libs += ['+incdir+' + str(path)]
        return libs

    def _buildVhdl(self, path, library, flags=None):
        "Builds a VHDL file"
        cmd = ['vcom', '-modelsimini', self._modelsim_ini, '-quiet',
               '-work', p.join(self._target_folder, library)]
        if flags:  # pragma: no cover
            cmd += flags
        cmd += [path]

        return self._subprocessRunner(cmd)

    def _buildVerilog(self, path, library, flags=None):
        "Builds a Verilog/SystemVerilog file"
        cmd = ['vlog', '-modelsimini', self._modelsim_ini, '-quiet',
               '-work', p.join(self._target_folder, library)]
        if getFileType(path) == 'systemverilog':
            cmd += ['-sv']
        if flags:  # pragma: no cover
            cmd += flags

        cmd += self._getExtraFlags('verilog')
        cmd += [path]

        return self._subprocessRunner(cmd)

    def _createLibrary(self, library):
        library = library.lower()
        if library in self._builtin_libraries:
            return

        if not self._iniFileExists() and library in self._added_libraries:
            return
        self._added_libraries.append(library)
        try:
            if p.exists(p.join(self._target_folder, library)):
                return
            self._mapLibrary(library)
        except: # pragma: no cover
            self._logger.debug("Current dir when exception was raised: %s",
                               p.abspath(os.curdir))
            raise

    def _iniFileExists(self):
        _modelsim_ini = p.join(self._target_folder, 'modelsim.ini')

        return p.exists(_modelsim_ini)

    def _createIniFile(self):
        """
        Adds a library to a non-existent ModelSim init file
        """
        _modelsim_ini = p.join(self._target_folder, 'modelsim.ini')

        if not p.exists(self._target_folder):  # pragma: no cover
            os.mkdir(self._target_folder)

        self._logger.info("modelsim.ini not found at '%s', creating",
                          p.abspath(_modelsim_ini))

        modelsim_env = os.environ.get('MODELSIM')
        if modelsim_env is not None:
            self._logger.info("MODELSIM environment variable set to %s, using "
                              "this path as default modelsim.ini",
                              modelsim_env)
            # Copy the modelsim.ini as indicated by the MODELSIM environment
            # variable
            copyfile(modelsim_env, _modelsim_ini)
        else:
            cwd = p.abspath(os.curdir)
            self._logger.debug("Current dir is %s, changing to %s",
                               cwd, self._target_folder)
            os.chdir(self._target_folder)
            if cwd == os.curdir: # pragma: no cover
                self._logger.fatal("cwd: %s, curdir: %s, error!", cwd, os.curdir)
                assert 0

            self._subprocessRunner(['vmap', '-c'])

            self._logger.debug("After vmap at '%s'", p.abspath(os.curdir))
            for _dir in os.listdir(p.abspath(os.curdir)):
                self._logger.debug("- '%s'", _dir)

            self._logger.debug("Current dir is %s, changing to %s",
                               p.abspath(os.curdir), cwd)
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
        """
        Adds a library to an existing ModelSim init file
        """
        self._subprocessRunner(['vlib', ] + self._vlib_args +
                               [p.join(self._target_folder, library)])

        self._subprocessRunner(['vmap', '-modelsimini', self._modelsim_ini,
                                library, p.join(self._target_folder, library)])


